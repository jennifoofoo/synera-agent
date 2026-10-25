"""Two-finger swipe up turns the 2D plan into 3D, like Google Maps (docs/specs/swipe-tilt.md).

Phone (Pixel 7, Chromium, touch): real two-finger touches through CDP `Input.dispatchTouchEvent` (Playwright has no
multi-touch move). Checks the acceptance criteria 1 to 5 of the spec: a parallel swipe up switches to 3D and keeps
the spot in the middle and keeps tilting; a pinch (also drifting up) and a sideways two-finger move never switch; a
swipe down to nearly straight down in 3D goes back to the plan at the same spot and scale; the 2D/3D button sets no
handover. Desktop (Chromium, 1280x800): criterion 6, Option/Alt + swipe up on the plan switches and tilts, and
Option/Alt + swipe down to straight down plus a pause goes back. Ambient occlusion is off (see test_here_ui.py).

Needs the built page (`scripts/build_twin.sh`) and Playwright with Chromium; without them the tests skip.
Run: `uv run pytest -m e2e tests/e2e/test_swipe_tilt.py`.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e.conftest import REPO
from tests.e2e.test_here_ui import NO_AO

pytestmark = pytest.mark.e2e

FOV = 38  # Scene.tsx

# Camera state; `scale` is px per metre in the image centre for both cameras (ortho zoom, or from the 3D distance).
CAMERA = f"""() => {{
  const c = window.__twinControls.current;
  const cam = c.camera;
  const t = c.getTarget(new cam.position.constructor());
  const frameH = cam.view && cam.view.enabled ? cam.view.fullHeight : document.querySelector('canvas').getBoundingClientRect().height;
  const flat = !!cam.isOrthographicCamera;
  const scale = flat ? cam.zoom : frameH / (2 * c.distance * Math.tan({FOV} * Math.PI / 360));
  const s = window.__twinStore.getState();
  return {{ mode: s.viewMode, handover: s.viewHandover, flat, target: [t.x, t.y, t.z], polar: c.polarAngle,
           azimuth: c.azimuthAngle, scale }};
}}"""

# Screen position (client px) of a world point through the current scene camera.
PROJECT = """([x, y, z]) => {
  const cam = window.__twinCamera; cam.updateMatrixWorld();
  const v = new cam.position.constructor(x, y, z).project(cam);
  const r = document.querySelector('canvas').getBoundingClientRect();
  return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height];
}"""

WHEEL = """async ([events, x, y]) => {
  const host = document.querySelector('canvas');
  for (const e of events) {
    host.dispatchEvent(new WheelEvent("wheel", { clientX: x, clientY: y, bubbles: true, cancelable: true, deltaMode: 0, ...e }));
    await new Promise((r) => setTimeout(r, 16));
  }
}"""


@pytest.fixture(scope="module")
def chromium(playwright_instance):
    try:
        browser = playwright_instance.chromium.launch()
    except Exception as error:  # noqa: BLE001 - missing browser binaries
        pytest.skip(f"chromium not installed: {str(error)[:80]}")
    yield browser
    browser.close()


@pytest.fixture
def open_twin(chromium, base_url, playwright_instance):
    if not (REPO / "twin" / "dist" / "index.html").exists():
        pytest.skip("twin/dist is missing (scripts/build_twin.sh)")
    contexts = []

    def _open(kind: str):
        if kind == "phone":
            options = dict(playwright_instance.devices["Pixel 7"])
            options.pop("default_browser_type", None)
        else:
            options = {"viewport": {"width": 1280, "height": 800}, "device_scale_factor": 1}
        context = chromium.new_context(**options)
        contexts.append(context)
        context.add_init_script(NO_AO)
        page = context.new_page()
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.goto(base_url)
        page.wait_for_function(
            "window.__twinStore && window.__twinStore.getState().model && window.__twinCamera"
            " && window.__twinControls && window.__twinControls.current",
            timeout=30000,
        )
        page.evaluate("window.__twinStore.getState().setViewMode('2d')")
        page.wait_for_timeout(1500)
        return page

    yield _open
    for context in contexts:
        context.close()


def zoom_on_floor_centre(page) -> dict:
    """Zoom the plan onto the middle of the focused floor (about one room) and return the settled camera."""
    page.evaluate(
        """() => { const s = window.__twinStore.getState(); const f = s.model.floorById.get(s.focusedFloorId);
        s.requestCamera({ kind: 'point', floorId: f.id, point: [f.bounds.cx, f.bounds.cy], radius: 6 }); }"""
    )
    page.wait_for_timeout(2000)
    return page.evaluate(CAMERA)


def two_finger(page, a, b, da, db, steps=16):
    """Two fingers down at a and b, moved by da and db in `steps` moves (about 60 Hz), then lifted."""
    cdp = page.context.new_cdp_session(page)

    def points(k):
        f = k / steps
        return [
            {"x": a[0] + da[0] * f, "y": a[1] + da[1] * f, "id": 1},
            {"x": b[0] + db[0] * f, "y": b[1] + db[1] * f, "id": 2},
        ]

    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": points(0)})
    for k in range(1, steps + 1):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": points(k)})
        page.wait_for_timeout(20)
    page.wait_for_timeout(60)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    cdp.detach()


def centre(page):
    size = page.viewport_size
    return size["width"] / 2, size["height"] * 0.45


def test_swipe_up_switches_to_3d_and_keeps_the_spot(open_twin):
    page = open_twin("phone")
    before = zoom_on_floor_centre(page)
    assert before["mode"] == "2d" and before["flat"], before
    spot_before = page.evaluate(PROJECT, before["target"])
    cx, cy = centre(page)
    two_finger(page, (cx - 60, cy + 80), (cx + 60, cy + 80), (0, -120), (0, -120))
    page.wait_for_timeout(800)
    after = page.evaluate(CAMERA)
    assert after["mode"] == "3d" and not after["flat"], after
    assert after["handover"] is None, "the handover is applied and cleared"
    assert after["polar"] > 0.3, f"the fingers kept tilting after the switch: {after}"
    spot_after = page.evaluate(PROJECT, before["target"])
    width = page.viewport_size["width"]
    assert math.dist(spot_before, spot_after) < 0.1 * width, (spot_before, spot_after)
    assert math.dist(before["target"][::2], after["target"][::2]) < 0.5, (before, after)
    assert not page.errors, page.errors


def test_pinch_and_sideways_never_switch(open_twin):
    page = open_twin("phone")
    before = zoom_on_floor_centre(page)
    cx, cy = centre(page)
    # Pinch out while drifting up a little: zooms like before, stays 2D.
    two_finger(page, (cx - 50, cy), (cx + 50, cy), (-45, -30), (45, -30))
    page.wait_for_timeout(600)
    pinched = page.evaluate(CAMERA)
    assert pinched["mode"] == "2d", pinched
    assert pinched["scale"] > before["scale"] * 1.3, (before, pinched)
    # Pinch in, straight.
    two_finger(page, (cx - 120, cy), (cx + 120, cy), (60, 0), (-60, 0))
    page.wait_for_timeout(600)
    assert page.evaluate(CAMERA)["mode"] == "2d"
    # Two fingers sideways together: pans, stays 2D.
    two_finger(page, (cx - 60, cy), (cx + 60, cy), (110, 0), (110, 0))
    page.wait_for_timeout(600)
    assert page.evaluate(CAMERA)["mode"] == "2d"
    # One finger up, the other still: never a tilt.
    two_finger(page, (cx - 60, cy + 60), (cx + 60, cy + 60), (0, -120), (0, 0))
    page.wait_for_timeout(600)
    assert page.evaluate(CAMERA)["mode"] == "2d"
    assert not page.errors, page.errors


def test_swipe_down_in_3d_goes_back_to_the_plan(open_twin):
    page = open_twin("phone")
    zoom_on_floor_centre(page)
    cx, cy = centre(page)
    two_finger(page, (cx - 60, cy + 80), (cx + 60, cy + 80), (0, -120), (0, -120))
    page.wait_for_timeout(800)
    tilted = page.evaluate(CAMERA)
    assert tilted["mode"] == "3d", tilted
    # Two fingers down (camera-controls tilts the 3D view back to straight down), then lift.
    two_finger(page, (cx - 60, cy - 120), (cx + 60, cy - 120), (0, 220), (0, 220), steps=24)
    page.wait_for_timeout(800)
    back = page.evaluate(CAMERA)
    assert back["mode"] == "2d" and back["flat"], back
    # Same spot and scale as the 3D view right before (the swipe itself may not move the target).
    visible_m = page.viewport_size["width"] / tilted["scale"]
    assert math.dist(tilted["target"][::2], back["target"][::2]) < 0.1 * visible_m, (tilted, back)
    assert abs(back["scale"] - tilted["scale"]) < 0.1 * tilted["scale"], (tilted, back)
    assert not page.errors, page.errors


def test_button_switch_sets_no_handover(open_twin):
    page = open_twin("phone")
    zoom_on_floor_centre(page)
    page.locator(".rail-view").click()
    page.wait_for_timeout(1500)
    three = page.evaluate(CAMERA)
    assert three["mode"] == "3d" and three["handover"] is None, three
    assert three["polar"] > 0.3, f"the button frames as before, not a straight-down handover view: {three}"
    page.locator(".rail-view").click()
    page.wait_for_timeout(1500)
    two = page.evaluate(CAMERA)
    assert two["mode"] == "2d" and two["handover"] is None, two
    assert not page.errors, page.errors


def test_option_swipe_switches_on_the_mac(open_twin):
    page = open_twin("desktop")
    before = page.evaluate(CAMERA)
    assert before["mode"] == "2d", before
    page.evaluate(WHEEL, [[{"deltaY": 10.5, "altKey": True} for _ in range(30)], 640, 400])
    page.wait_for_timeout(600)
    up = page.evaluate(CAMERA)
    assert up["mode"] == "3d", up
    assert up["polar"] > 0.3, f"Option + swipe keeps tilting after the switch: {up}"
    assert math.dist(before["target"][::2], up["target"][::2]) < 0.5, (before, up)
    assert abs(math.remainder(up["azimuth"] - before["azimuth"], 2 * math.pi)) < 0.05, (
        "a swipe up does not turn the plan"
    )
    # Swipe down to straight down, then the pause: back to the plan.
    page.evaluate(WHEEL, [[{"deltaY": -12.5, "altKey": True} for _ in range(40)], 640, 400])
    page.wait_for_timeout(900)
    back = page.evaluate(CAMERA)
    assert back["mode"] == "2d", back
    assert abs(back["scale"] - up["scale"]) < 0.1 * up["scale"], (up, back)
    assert not page.errors, page.errors
