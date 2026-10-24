"""Closed lifts and stairs in one language (2D and 3D, desktop and phone): after closing the office staircase and the
office lift of proc-factory-dev-012 the stairs/lift glyph turns into the prohibition glyph, the slab gets the hatched
fill instead of the violet, a "Closed" tag sits beside the glyph from the mid zoom tier on, a route on that floor says
"Avoids closed ...", and the help legend has a "Closed" row. Reopening removes all of it at once.

Needs the built page (`scripts/build_twin.sh`), Playwright and Chromium and data/dev; skips otherwise.
Run: `uv run pytest -m e2e tests/e2e/test_closed_marking.py`.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e.test_semantic_zoom import SHOWN, _open, _zoom, chromium, factory_url  # noqa: F401 - fixtures

pytestmark = pytest.mark.e2e

B = "proc-factory-dev-012"
STAIRS = f"{B}-V01"
LIFT = f"{B}-V02"
STOPS_F0 = {f"{B}-F0-S026": "stairs", f"{B}-F0-S027": "lift"}

MARKS = """() => ({
  glyphs: [...document.querySelectorAll('[data-poi-space] .poi-closed')].map((el) => el.parentElement.dataset.poiSpace),
  tags: document.querySelectorAll('[data-zoom-kind="closed-tag"]').length,
  avoids: (document.querySelector('[data-testid="route-avoids"]') || {}).textContent || '',
  drawn: window.__twinAudit.drawnClosed(),
})"""

TWO_F0_ROOMS = """() => {
  const m = window.__twinStore.getState().model;
  const rooms = m.floors.find((f) => f.level === 0).spaces.filter((s) => s.type === 'room' && s.name);
  return [rooms[0].id, rooms[rooms.length - 1].id];
}"""


def _reset(page):
    """The server is shared by the module: start with both open and no route."""
    page.evaluate("window.__twinStore.getState().clearRoute()")
    _set_closed(page, STAIRS, False)
    _set_closed(page, LIFT, False)


def _set_closed(page, element, closed):
    page.evaluate("([id, c]) => window.__twinStore.getState().setClosed(id, c)", [element, closed])
    page.mouse.wheel(0, 1)  # frames on demand
    page.wait_for_timeout(600)


@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_closed_lift_and_stairs_marked_and_gone_after_reopen(device, factory_url, chromium, playwright_instance):  # noqa: F811
    context, page = _open(chromium, playwright_instance, factory_url, device)
    try:
        _reset(page)
        before = _zoom(page, 0, 0.12)
        assert before["tier"] == "mid", before
        assert page.evaluate(MARKS)["glyphs"] == []

        _set_closed(page, STAIRS, True)
        _set_closed(page, LIFT, True)
        # 1. the glyph itself changes (prohibition style) for both stops on this floor (near: both fit side by side;
        # at mid the lift glyph yields to the stairs glyph next to it, as it does when open)
        _zoom(page, 0, 0.05)
        assert sorted(page.evaluate(MARKS)["glyphs"]) == sorted(STOPS_F0)
        shown = _zoom(page, 0, 0.12)
        marks = page.evaluate(MARKS)
        assert marks["glyphs"], marks
        # 2. the slab gets the hatched fill; no separate red disc for lifts and stairs any more
        assert marks["drawn"]["fills"] >= 2 and marks["drawn"]["markers"] == 0, marks
        # 3. "Closed" beside the glyph at the mid tier, laid out without overlaps
        assert marks["tags"] >= 1, marks
        assert not shown["overlaps"], shown["overlaps"][:5]
        # far tier: glyphs stay, no tag
        far = _zoom(page, 0, 0.6)
        assert far["kinds"].get("closed-tag", 0) == 0, far
        assert far["kinds"].get("poi-stairs", 0) + far["kinds"].get("poi-lift", 0) >= 1, far
        assert page.evaluate(MARKS)["glyphs"], (far, page.evaluate("window.__twinStore.getState().selection"))

        # 4. a route on this floor names what it goes around
        start, goal = page.evaluate(TWO_F0_ROOMS)
        page.evaluate("([a, b]) => window.__twinStore.getState().route(a, b)", [start, goal])
        page.wait_for_timeout(800)
        avoids = page.evaluate(MARKS)["avoids"]
        assert avoids.startswith("Avoids closed") and "Office lift" in avoids and "Office staircase" in avoids, avoids

        # 5. legend row with the prohibition glyph
        page.evaluate(
            "document.body.dispatchEvent(new KeyboardEvent('keydown', { key: '?', bubbles: true }))"
        )  # the "?" help card
        page.wait_for_selector('[data-legend="closed"] .poi-closed', timeout=5000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 6. reopening removes all of it at once
        _set_closed(page, STAIRS, False)
        _set_closed(page, LIFT, False)
        _zoom(page, 0, 0.12)
        marks = page.evaluate(MARKS)
        assert marks["glyphs"] == [] and marks["tags"] == 0, marks
        assert marks["drawn"]["fills"] == 0 and marks["drawn"]["elements"] == 0, marks
        assert marks["avoids"] == "", marks
        page.evaluate("window.__twinStore.getState().clearRoute()")
        assert not page.errors, page.errors
    finally:
        context.close()


def test_closed_glyph_and_fill_in_3d(factory_url, chromium, playwright_instance):  # noqa: F811
    context, page = _open(chromium, playwright_instance, factory_url, "desktop")
    try:
        _reset(page)
        page.evaluate("window.__twinStore.getState().setViewMode('3d')")
        page.wait_for_timeout(1500)
        _set_closed(page, LIFT, True)
        marks = page.evaluate(MARKS)
        assert marks["drawn"]["fills"] >= 1 and marks["drawn"]["markers"] == 0, marks
        assert any(space in STOPS_F0 or space.endswith(("S003", "S027")) for space in marks["glyphs"]), marks
        _set_closed(page, LIFT, False)
        marks = page.evaluate(MARKS)
        assert marks["glyphs"] == [] and marks["drawn"]["fills"] == 0, marks
        assert not page.errors, page.errors
    finally:
        context.close()
