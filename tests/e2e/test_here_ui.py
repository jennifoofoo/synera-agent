"""Tap pin and draggable "You are here" dot of the 3D twin (docs: twin/src/scene/HerePin.tsx).

Flow: tap the floor, see the pin and "Point x, y m" on the card, press "I'm here" (pin becomes the dot), drag the dot
about 100 px and check through the API that the position moved to a point inside a room. The chat turn is faked
(tests/e2e/fake_chat_server.py), so no API key and no cost. Skips without Playwright, a browser, data/dev or twin/dist.

Run: scripts/build_twin.sh && uv run pytest -m e2e tests/e2e/test_here_ui.py
Set HERE_UI_SHOTS=<folder> to also save screenshots (desktop 1100x720, phone 390x844).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e.conftest import REPO, _free_port, _pick_buildings

pytestmark = pytest.mark.e2e

VIEWPORTS = {"desktop": {"width": 1100, "height": 720}, "phone": {"width": 390, "height": 844}}

# Screen position (client px) of a named object in the three.js scene, via the camera that CameraRig exposes.
SCREEN_OF = """(name) => {
  const scene = window.__twinScene, controls = window.__twinControls && window.__twinControls.current;
  if (!scene || !controls) return null;
  const obj = scene.getObjectByName(name);
  if (!obj) return null;
  obj.updateWorldMatrix(true, false);
  const e = obj.matrixWorld.elements;
  const camera = controls.camera;
  camera.updateMatrixWorld();
  const v = new obj.position.constructor(e[12], e[13], e[14]).project(camera);
  const rect = document.querySelector('canvas').getBoundingClientRect();
  return { x: rect.left + (v.x + 1) / 2 * rect.width, y: rect.top + (1 - v.y) / 2 * rect.height, wx: e[12], wy: -e[14] };
}"""


@pytest.fixture()
def server(tmp_path_factory):
    if not (REPO / "twin" / "dist" / "index.html").exists():
        pytest.skip("twin/dist is missing (scripts/build_twin.sh)")
    data = tmp_path_factory.mktemp("here_ui_data")
    _pick_buildings(data)
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if "API_KEY" not in k and not k.startswith("ANTHROPIC")}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.e2e.fake_chat_server",
            "--data",
            str(data),
            "--port",
            str(port),
            "--env-file",
            str(data / "no.env"),
        ],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if proc.poll() is not None:
                pytest.fail("fake chat server exited early")
            try:
                urllib.request.urlopen(url + "/", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("fake chat server did not start")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def get_json(url: str) -> dict:
    return json.loads(urllib.request.urlopen(url, timeout=5).read())


def inside(point, polygon) -> bool:
    x, y = point
    result = False
    for (xi, yi), (xj, yj) in zip(polygon, [polygon[-1], *polygon[:-1]]):
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            result = not result
    return result


@pytest.fixture(params=["desktop", "phone"])
def page(request, server, playwright_instance):
    kind = request.param
    try:
        browser = playwright_instance.chromium.launch()
    except Exception as error:  # noqa: BLE001 - missing browser binary
        pytest.skip(f"chromium not installed: {str(error)[:80]}")
    context = browser.new_context(
        viewport=VIEWPORTS[kind], has_touch=kind == "phone", is_mobile=kind == "phone", device_scale_factor=2
    )
    page = context.new_page()
    page.kind = kind
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(server)
    page.wait_for_function(
        "window.__twinScene && window.__twinControls && window.__twinControls.current", timeout=20000
    )
    page.wait_for_timeout(1500)  # the camera flies home first
    yield page
    context.close()
    browser.close()


def shot(page, name: str) -> None:
    folder = os.environ.get("HERE_UI_SHOTS")
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(folder) / f"{name}-{page.kind}.png"))


def tap(page, x: float, y: float) -> None:
    if page.kind == "phone":
        page.touchscreen.tap(x, y)
    else:
        page.mouse.click(x, y)


def tap_floor(page) -> str:
    """Tap a grid of spots around the middle of the canvas until one lands on a room floor (not a thing)."""
    size = page.viewport_size
    for fy in (0.45, 0.35, 0.55, 0.3, 0.6, 0.4, 0.5):
        for fx in (0.5, 0.4, 0.6, 0.3, 0.7, 0.45, 0.55, 0.35, 0.65):
            tap(page, size["width"] * fx, size["height"] * fy)
            page.wait_for_timeout(150)
            if page.locator("[data-testid=card-point]").count():
                return page.locator("[data-testid=card-point]").inner_text()
    pytest.fail("no tap landed on a floor")


def touch_drag(page, start, end, steps=12):
    """A real touch drag through CDP (Playwright has no touch move)."""
    cdp = page.context.new_cdp_session(page)
    cdp.send(
        "Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": start[0], "y": start[1], "id": 1}]}
    )
    for i in range(1, steps + 1):
        x = start[0] + (end[0] - start[0]) * i / steps
        y = start[1] + (end[1] - start[1]) * i / steps
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y, "id": 1}]})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def mouse_drag(page, start, end, steps=12):
    page.mouse.move(*start)
    page.mouse.down()
    for i in range(1, steps + 1):
        page.mouse.move(start[0] + (end[0] - start[0]) * i / steps, start[1] + (end[1] - start[1]) * i / steps)
    page.mouse.up()


def test_tap_pin_then_here_then_drag(page, server):
    key = page.evaluate("localStorage.getItem('twin.building')")
    building = get_json(f"{server}/api/building?key={key}")
    assert building["state"]["position"] is None
    shot(page, "before-tap")

    # 1. tap: pin at the tapped point, card shows "Point x, y m"
    text = tap_floor(page)
    match = re.fullmatch(r"Point (-?\d+\.\d), (-?\d+\.\d) m", text)
    assert match, text
    pin = page.evaluate(SCREEN_OF, "tap-pin")
    assert pin, "no pin in the scene after the tap"
    assert abs(pin["wx"] - float(match[1])) <= 0.06 and abs(pin["wy"] - float(match[2])) <= 0.06
    assert page.evaluate(SCREEN_OF, "here-dot") is None
    shot(page, "after-tap")

    # 2. "I'm here": the pin becomes the dot, never both
    page.get_by_role("button", name="I'm here").click()
    page.wait_for_function("window.__twinScene.getObjectByName('here-dot')", timeout=10000)
    page.wait_for_function("!window.__twinScene.getObjectByName('tap-pin')", timeout=10000)
    # "I'm here" is set on screen at once (no agent call); the server learns it with the next chat message.
    state = page.evaluate(PAGE_POSITION)
    assert state and state["point"] and state["source"] == "click"
    first = state["point"]
    assert abs(first[0] - float(match[1])) <= 0.06 and abs(first[1] - float(match[2])) <= 0.06
    page.wait_for_timeout(500)
    shot(page, "here-dot")

    # 3. drag the dot about 100 px (try the four directions: the first one that stays inside a room moves it)
    moved = None
    for dx, dy in ((100, 0), (-100, 0), (0, 100), (0, -100), (70, 70), (-70, -70)):
        dot = page.evaluate(SCREEN_OF, "here-dot")
        assert dot
        start, end = (dot["x"], dot["y"]), (dot["x"] + dx, dot["y"] + dy)
        (touch_drag if page.kind == "phone" else mouse_drag)(page, start, end)
        deadline = time.time() + 3
        while time.time() < deadline:
            now = page.evaluate(PAGE_POSITION)
            if now and now["point"] != first:
                moved = now
                break
            page.wait_for_timeout(150)
        if moved:
            break
    assert moved, "dragging the dot did not change the position"
    assert page.evaluate("window.__twinControls.current.enabled") is True, "camera controls stay locked after the drag"
    space = next(s for s in building["spaces"] if s["id"] == moved["space_id"])
    assert inside(moved["point"], space["polygon"]), "the dragged point is not inside its room"
    assert moved["floor_id"] == state["floor_id"]
    page.wait_for_timeout(500)
    shot(page, "after-drag")
    assert not page.errors, page.errors


PAGE_POSITION = "() => window.__twinAudit.store.getState().state.position"


# Screen box (client px) of a marker drawn at a constant size: its centre projected, +- the radius in px.
MARKER_BOX = """([name, radius]) => {
  const scene = window.__twinScene, controls = window.__twinControls && window.__twinControls.current;
  const obj = scene && scene.getObjectByName(name);
  if (!obj || !controls) return null;
  obj.updateWorldMatrix(true, false);
  const e = obj.matrixWorld.elements;
  const v = new obj.position.constructor(e[12], e[13], e[14]).project(controls.camera);
  const rect = document.querySelector('canvas').getBoundingClientRect();
  const x = rect.left + (v.x + 1) / 2 * rect.width, y = rect.top + (1 - v.y) / 2 * rect.height;
  return { left: x - radius, right: x + radius, top: y - radius, bottom: y + radius };
}"""

BOX_OF = """(selector) => {
  const el = document.querySelector(selector);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
}"""


def overlap(a, b) -> bool:
    dx = min(a["right"], b["right"]) - max(a["left"], b["left"])
    dy = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
    return dx > 0.5 and dy > 0.5


def post_json(url: str, body: dict) -> dict:
    request = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(request, timeout=30).read())


def test_labels_clear_of_markers(page, server):
    """Room labels of the here room and of both route ends sit above their markers, never under them."""
    key = page.evaluate("localStorage.getItem('twin.building')")
    building = get_json(f"{server}/api/building?key={key}")
    floors = building["floors"]
    floor = next((f for f in floors if f["level"] == 0), None) or next((f for f in floors if f["level"] > 0), floors[0])
    rooms = sorted(
        (s for s in building["spaces"] if s["floor_id"] == floor["id"] and s["type"] == "room" and s["name"]),
        key=lambda s: -s["area_m2"],
    )
    pair = None
    for start in rooms[:4]:
        for end in rooms[:6]:
            if start["id"] == end["id"]:
                continue
            reply = post_json(f"{server}/api/route", {"building": key, "start": start["id"], "destination": end["id"]})
            if reply["route"]["ok"]:
                pair = (start, end)
                break
        if pair:
            break
    assert pair, "no routable pair of rooms on the ground floor"
    start, end = pair
    here = {"space_id": start["id"], "floor_id": start["floor_id"]}
    post_json(f"{server}/api/chat", {"building": key, "message": "I'm here.", "context": {"here": here}})
    page.reload()
    page.wait_for_function("window.__twinScene && window.__twinScene.getObjectByName('route-end')", timeout=20000)
    page.wait_for_timeout(1500)
    for view in ["3d", "2d"] if page.kind == "desktop" else ["2d"]:
        if view == "2d" and page.kind == "desktop":
            page.get_by_role("button", name="2D").first.click()
            page.wait_for_timeout(1500)
        boxes = {
            "dot": page.evaluate(MARKER_BOX, ["here-dot", 9]),
            "badge": page.evaluate(BOX_OF, ".here-badge"),
            "end": page.evaluate(MARKER_BOX, ["route-end", 9.5]),
            "start": page.evaluate(MARKER_BOX, ["route-start", 7]),
        }
        assert all(boxes.values()), boxes
        for room in (start, end):
            label = page.evaluate(BOX_OF, f'[data-label-space="{room["id"]}"]')
            assert label, f"no label for marked room {room['name']} ({view})"
            for name, box in boxes.items():
                assert not overlap(label, box), f"label {room['name']} overlaps {name} in {view}: {label} {box}"
        shot(page, f"labels-{view}")
    assert not page.errors, page.errors
