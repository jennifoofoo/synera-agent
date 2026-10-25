"""Trackpad and tilt controls of the twin (twin/src/scene/cameraMouse.ts, wheelInput.ts, ui/Compass.tsx).

A Mac trackpad in Chrome sends wheel events: a two-finger swipe has pixel deltas (often fractional, often sideways),
a pinch has ctrlKey. These tests dispatch such events in Chromium and check the camera: swipe pans, pinch zooms,
Option/Alt + swipe rotates and tilts, Option/Alt + drag tilts, the tilt buttons tilt within the limit, the compass
turns the view back north up.

Needs the built page (`scripts/build_twin.sh`) and Playwright with Chromium; without them the tests skip.
Run: `uv run pytest -m e2e tests/e2e/test_twin_trackpad.py`.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e.conftest import REPO

pytestmark = pytest.mark.e2e

MAX_TILT = 1.0  # CameraRig.tsx

CAMERA = """() => {
  const c = window.__twinControls.current;
  const t = c.getTarget({ x: 0, y: 0, z: 0, set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; } });
  return { target: [t.x, t.y, t.z], azimuth: c.azimuthAngle, polar: c.polarAngle, distance: c.distance, zoom: c.camera.zoom };
}"""

# A stream of wheel events at 60 Hz on the canvas, like a trackpad gesture.
WHEEL = """async ([events, x, y]) => {
  const root = window.__twinControls.current._domElement;
  const host = root.tagName === "CANVAS" ? root : root.querySelector("canvas");
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
def page_in(chromium, base_url):
    if not (REPO / "twin" / "dist" / "index.html").exists():
        pytest.skip("twin/dist is missing (scripts/build_twin.sh)")
    contexts = []

    def _open(mode: str):
        context = chromium.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
        contexts.append(context)
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base_url)
        page.wait_for_function(
            "window.__twinStore && window.__twinStore.getState().model && window.__twinControls && window.__twinControls.current",
            timeout=30000,
        )
        page.evaluate(f"window.__twinStore.getState().setViewMode('{mode}')")
        page.wait_for_timeout(1500)
        page.evaluate("window.__twinStore.getState().requestCamera({ kind: 'home' })")
        page.wait_for_timeout(3000)
        return page, errors

    yield _open
    for context in contexts:
        context.close()


def settle(page, ms: int = 700):
    page.wait_for_timeout(ms)
    return page.evaluate(CAMERA)


@pytest.mark.parametrize("mode", ["3d", "2d"])
def test_trackpad_swipe_pans_and_pinch_zooms(mode, page_in):
    page, errors = page_in(mode)
    before = page.evaluate(CAMERA)
    # Chrome trackpad swipe: fractional deltas on both axes, ramping up and down.
    swipe = [{"deltaX": 0.5 * k + 0.25, "deltaY": 1.5 * k + 0.5} for k in [1, 2, 4, 7, 10, 12, 10, 7, 4, 2, 1]]
    page.evaluate(WHEEL, [swipe, 640, 400])
    after = settle(page)
    moved = math.dist(before["target"], after["target"])
    assert moved > 1.0, (before, after)
    assert abs(after["distance"] - before["distance"]) < 0.05 * before["distance"], "a swipe must not zoom"
    assert abs(after["zoom"] - before["zoom"]) < 0.05 * before["zoom"], "a swipe must not zoom"

    # Chrome pinch: ctrl + wheel, small deltas. Pinch out (negative deltaY) zooms in.
    pinch = [{"deltaY": -3.5, "ctrlKey": True} for _ in range(12)]
    page.evaluate(WHEEL, [pinch, 640, 400])
    zoomed = settle(page)
    if mode == "3d":
        assert zoomed["distance"] < after["distance"] * 0.95, (after, zoomed)
    else:
        assert zoomed["zoom"] > after["zoom"] * 1.05, (after, zoomed)
    assert not errors, errors


def pick_more(page, test_id):
    """North up and tilt sit behind the floor rail's "…" menu (FloorRail.tsx); it closes after each pick."""
    page.get_by_test_id("rail-more").click()
    page.get_by_test_id(test_id).click()


@pytest.mark.parametrize("mode", ["3d", "2d"])
def test_alt_wheel_rotates_and_compass_resets_north(mode, page_in):
    page, errors = page_in(mode)
    before = page.evaluate(CAMERA)
    page.evaluate(WHEEL, [[{"deltaX": 12.5, "altKey": True} for _ in range(10)], 640, 400])
    turned = settle(page)
    assert abs(turned["azimuth"] - before["azimuth"]) > 0.2, (before, turned)
    assert math.dist(before["target"], turned["target"]) < 0.5, "Alt + swipe must not pan"

    pick_more(page, "compass")
    reset = settle(page, 1500)
    assert abs(math.remainder(reset["azimuth"], 2 * math.pi)) < 0.02, reset
    assert reset["polar"] < 0.1, "the compass turns the view straight down"
    assert not errors, errors


def test_alt_drag_and_tilt_buttons_tilt_within_the_limit(page_in):
    page, errors = page_in("3d")
    page.evaluate("window.__twinControls.current.rotateTo(0, 0.4, false)")
    start = settle(page, 300)

    # Option/Alt + click-drag upwards (a trackpad with the click held is the same mouse events).
    page.keyboard.down("Alt")
    page.mouse.move(640, 450)
    page.mouse.down()
    for step in range(1, 16):
        page.mouse.move(640, 450 - step * 8)
        page.wait_for_timeout(16)
    page.mouse.up()
    page.keyboard.up("Alt")
    dragged = settle(page)
    assert dragged["polar"] > start["polar"] + 0.1, (start, dragged)
    assert math.dist(start["target"], dragged["target"]) < 0.5, "Alt + drag must not pan"

    # Option/Alt + vertical swipe tilts too.
    page.evaluate("window.__twinControls.current.rotateTo(0, 0.4, false)")
    settle(page, 300)
    page.evaluate(WHEEL, [[{"deltaY": 10.5, "altKey": True} for _ in range(8)], 640, 400])
    swiped = settle(page)
    assert swiped["polar"] > 0.5, swiped

    # The tilt buttons: steeper goes towards top-down, flatter towards the horizon but never past MAX_TILT.
    pick_more(page, "tilt-steeper")
    steeper = settle(page, 1000)
    assert steeper["polar"] < swiped["polar"] - 0.1, (swiped, steeper)
    for _ in range(12):
        pick_more(page, "tilt-flatter")
        page.wait_for_timeout(60)
    flattest = settle(page, 1200)
    assert flattest["polar"] > steeper["polar"] + 0.2, (steeper, flattest)
    assert flattest["polar"] <= MAX_TILT + 1e-3, flattest

    # Gestures obey the limit too.
    page.evaluate(WHEEL, [[{"deltaY": 40.5, "altKey": True} for _ in range(10)], 640, 400])
    assert settle(page)["polar"] <= MAX_TILT + 1e-3
    assert not errors, errors
