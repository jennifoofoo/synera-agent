"""Camera controls of the 3D twin (twin/src/scene/cameraMouse.ts): a left drag grabs the map like Google Maps.

Needs the built page (`scripts/build_twin.sh`), Playwright and its browsers (`uv sync --group e2e`,
`uv run playwright install chromium webkit`); without them the tests skip. Run: `uv run pytest -m e2e tests/e2e/test_twin_controls.py`.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e.conftest import REPO

pytestmark = pytest.mark.e2e

# The camera target in world space (it stands in the middle of the screen).
TARGET = """() => {
  const c = window.__twinControls.current;
  const t = c.getTarget({ x: 0, y: 0, z: 0, set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; } });
  return [t.x, t.y, t.z];
}"""

# Where a world point is on screen (CSS px), through the real camera matrices.
ON_SCREEN = """(t) => {
  const cam = window.__twinCamera;
  cam.updateMatrixWorld();
  const v = cam.matrixWorldInverse.elements, P = cam.projectionMatrix.elements;
  const p = t;
  const x = v[0] * p[0] + v[4] * p[1] + v[8] * p[2] + v[12], y = v[1] * p[0] + v[5] * p[1] + v[9] * p[2] + v[13], z = v[2] * p[0] + v[6] * p[1] + v[10] * p[2] + v[14];
  const cx = P[0] * x + P[4] * y + P[8] * z + P[12], cy = P[1] * x + P[5] * y + P[9] * z + P[13], cw = P[3] * x + P[7] * y + P[11] * z + P[15];
  return [(cx / cw * 0.5 + 0.5) * innerWidth, (1 - (cy / cw * 0.5 + 0.5)) * innerHeight];
}"""


@pytest.fixture(scope="module")
def browsers(playwright_instance):
    opened = {}
    yield opened
    for browser in opened.values():
        browser.close()


@pytest.mark.parametrize("engine", ["webkit", "chromium"])
@pytest.mark.parametrize("mode", ["3d", "2d"])
def test_left_drag_moves_the_map_with_the_pointer(engine, mode, base_url, playwright_instance, browsers):
    if not (REPO / "twin" / "dist" / "index.html").exists():
        pytest.skip("twin/dist is missing (scripts/build_twin.sh)")
    if engine not in browsers:
        try:
            browsers[engine] = getattr(playwright_instance, engine).launch()
        except Exception as error:  # noqa: BLE001 - missing browser binaries
            pytest.skip(f"{engine} not installed: {str(error)[:80]}")
    context = browsers[engine].new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    try:
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
        page.wait_for_timeout(2500)

        world = page.evaluate(TARGET)
        before = page.evaluate(ON_SCREEN, world)
        # Press on the middle of the map (a room), drag 200 px right and 60 px down, release.
        page.mouse.move(640, 400)
        page.mouse.down()
        for step in range(1, 21):
            page.mouse.move(640 + step * 10, 400 + step * 3)
            page.wait_for_timeout(16)
        page.mouse.up()
        page.wait_for_timeout(300)
        after = page.evaluate(ON_SCREEN, world)  # the same world point after the drag

        assert abs((after[0] - before[0]) - 200) < 20, (before, after)
        assert abs((after[1] - before[1]) - 60) < 20, (before, after)
        assert page.evaluate("window.__twinStore.getState().selection") is None, "a drag must not select a room"
        assert not errors, errors

        # A plain click (no movement) still selects a room.
        page.mouse.click(840, 460)
        page.wait_for_timeout(300)
        assert page.evaluate("window.__twinStore.getState().selection") is not None, "a click should select the room"
    finally:
        context.close()
