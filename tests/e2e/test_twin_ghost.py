"""Regression: no "ghost" copy of the building after the pixel ratio drops (twin/src/scene/Effects.tsx).

The bug: the PerformanceMonitor in Scene.tsx lowers the canvas pixel ratio when frames drop (clicking a room often
does it). @react-three/postprocessing only resizes its EffectComposer when the CSS size changes, so the composer's
buffers (and N8AO's targets) kept the old, larger size. The AO pass then sampled them with the wrong scale: a blurred,
enlarged copy of the building appeared in the upper right of the canvas. Effects.tsx now resizes the composer when
the pixel ratio changes.

The test opens the planner in 3D, forces the highest quality (pixel ratio 2), clicks a room so the card opens, drops
the quality to the lowest (pixel ratio 1, like the PerformanceMonitor does) and checks (1) that the composer's buffers
match the canvas drawing buffer and (2) that the upper-right part of the canvas looks like before the click.

Run: scripts/build_twin.sh && uv run pytest -m e2e tests/e2e/test_twin_ghost.py
Set TWIN_GHOST_SHOTS=<folder> to also save the screenshots.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e.conftest import REPO

pytestmark = pytest.mark.e2e

WIDTH, HEIGHT = 1440, 900

SIZES = """() => {
  const canvas = document.querySelector('canvas');
  const composer = window.__twinComposer;
  if (!composer) return null;
  return { canvas: [canvas.width, canvas.height], input: [composer.inputBuffer.width, composer.inputBuffer.height],
           output: [composer.outputBuffer.width, composer.outputBuffer.height] };
}"""

# Mean absolute RGB difference (0..255) of two PNG screenshots in a region, decoded in the page (no PIL needed).
REGION_DIFF = """async ([a, b, region]) => {
  const load = async (data) => {
    const blob = await (await fetch('data:image/png;base64,' + data)).blob();
    const bitmap = await createImageBitmap(blob);
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width; canvas.height = bitmap.height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(bitmap, 0, 0);
    return ctx.getImageData(region[0], region[1], region[2], region[3]).data;
  };
  const pa = await load(a), pb = await load(b);
  let sum = 0;
  for (let i = 0; i < pa.length; i += 4) sum += Math.abs(pa[i] - pb[i]) + Math.abs(pa[i + 1] - pb[i + 1]) + Math.abs(pa[i + 2] - pb[i + 2]);
  return sum / (pa.length / 4) / 3;
}"""


@pytest.fixture(scope="module")
def browsers(playwright_instance):
    opened = {}
    yield opened
    for browser in opened.values():
        browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_no_ghost_after_pixel_ratio_drop(engine, base_url, playwright_instance, browsers):
    if not (REPO / "twin" / "dist" / "index.html").exists():
        pytest.skip("twin/dist is missing (scripts/build_twin.sh)")
    if engine not in browsers:
        try:
            browsers[engine] = getattr(playwright_instance, engine).launch()
        except Exception as error:  # noqa: BLE001 - missing browser binaries
            pytest.skip(f"{engine} not installed: {str(error)[:80]}")
    context = browsers[engine].new_context(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
    shots = os.environ.get("TWIN_GHOST_SHOTS")
    try:
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base_url)
        page.wait_for_function(
            "window.__twinStore && window.__twinStore.getState().model && window.__twinSetQuality && window.__twinComposer",
            timeout=30000,
        )
        page.evaluate("window.__twinStore.getState().setViewMode('3d')")
        page.evaluate("window.__twinSetQuality(2)")
        page.wait_for_function("document.querySelector('canvas').width === 2 * innerWidth", timeout=10000)
        page.evaluate("window.__twinStore.getState().requestCamera({ kind: 'home' })")
        page.wait_for_timeout(2500)
        page.evaluate("window.__twinSetQuality(2)")  # the PerformanceMonitor may have stepped down meanwhile
        page.wait_for_timeout(800)
        before = page.screenshot()

        # Click the middle of the building (a room): the card opens. Then the pixel ratio drops to 1.
        page.mouse.click(WIDTH // 2, HEIGHT // 2)
        page.wait_for_timeout(600)
        page.evaluate("window.__twinSetQuality(0)")
        page.wait_for_function("document.querySelector('canvas').width === innerWidth", timeout=10000)
        page.wait_for_timeout(1200)
        after = page.screenshot()
        if shots:
            Path(shots).mkdir(parents=True, exist_ok=True)
            Path(shots, f"{engine}_before.png").write_bytes(before)
            Path(shots, f"{engine}_after.png").write_bytes(after)

        sizes = page.evaluate(SIZES)
        assert sizes["input"] == sizes["canvas"], f"composer buffers not resized with the pixel ratio: {sizes}"
        assert sizes["output"] == sizes["canvas"], f"composer buffers not resized with the pixel ratio: {sizes}"

        # Upper right quarter: ground and grid only, before and after. The ghost made it differ by about 10.
        region = [WIDTH // 2, 0, WIDTH // 2, HEIGHT // 3]
        diff = page.evaluate(REGION_DIFF, [base64.b64encode(before).decode(), base64.b64encode(after).decode(), region])
        assert diff < 3.0, f"upper right of the canvas changed after the click (ghost?): mean diff {diff:.2f}"
        assert not errors, errors
    finally:
        context.close()
