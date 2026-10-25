"""Knowledge panel (twin/src/ui/KnowledgeGraph.tsx, docs/specs/knowledge-graph-view.md) in the browser against the real
web server (fake chat, no key): facts seeded via POST /api/facts show up in the ego graph of their room, the time
slider hides a note after its valid_to, the AAS link points to format=aas, and the panel fits a 390 px phone.

Skips without Playwright, chromium, data/train or twin/dist.
Run: scripts/build_twin.sh && uv run --group e2e pytest -m e2e tests/e2e/test_knowledge_graph.py
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e.test_round_and_notes import DEMO, server  # noqa: F401 - the server fixture (temp cwd, fake chat)

pytestmark = pytest.mark.e2e

ROOM = "proc-factory-train-015-F0-S002"  # Production zone H-A2
FLOOR = "proc-factory-train-015-F0"
LATHE = "proc-factory-train-015-A00011"
DAY_MS = 86_400_000


def post_fact(url: str, fact: dict) -> str:
    body = json.dumps({"key": DEMO, **fact}).encode()
    request = urllib.request.Request(
        url + "/api/facts", data=body, headers={"Content-Type": "application/json", "Origin": url}
    )
    return json.loads(urllib.request.urlopen(request, timeout=10).read())["fact"]["id"]


@pytest.fixture()
def seeded(server):  # noqa: F811 - pytest fixture injection
    tomorrow = (datetime.now() + timedelta(days=1)).replace(microsecond=0).isoformat()
    lathe = post_fact(
        server, {"kind": "note", "anchor": {"asset_id": LATHE}, "text": "Coolant leak", "author": "Marta"}
    )
    forklift = post_fact(
        server,
        {
            "kind": "note",
            "anchor": {"space_id": ROOM},
            "text": "Forklift in the aisle",
            "author": "Ali",
            "valid_to": tomorrow,
        },
    )
    return server, lathe, forklift


def open_panel(playwright_instance, url: str, viewport: dict, planner: bool = False):
    try:
        browser = playwright_instance.chromium.launch()
    except Exception as error:  # noqa: BLE001 - missing browser binary
        pytest.skip(f"chromium not installed: {str(error)[:80]}")
    context = browser.new_context(viewport=viewport)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.route("**/api/speak", lambda route: route.fulfill(status=503, body="no voice"))
    page.goto(f"{url}/?building={DEMO}")
    page.wait_for_function("() => !!window.__twinStore?.getState().model", timeout=30000)
    if planner:  # a narrow window forced to the laptop profile (the phone profile has no Knowledge button)
        page.evaluate("() => window.__twinStore.getState().setProfile('planner')")
    page.evaluate(
        "([id, floor_id]) => window.__twinStore.getState().select({ kind: 'space', id, floor_id })", [ROOM, FLOOR]
    )
    page.get_by_test_id("knowledge-open").click()
    page.wait_for_selector("[data-testid=knowledge-svg]", timeout=15000)
    return browser, page


def facts_listed(page) -> list[str]:
    return page.locator("[data-testid=knowledge-facts] li").all_inner_texts()


def node_shown(page, fact_id: str) -> bool:
    return page.locator(f'[data-testid=knowledge-svg] g[data-id$=":fact:{fact_id}"]').count() == 1


def set_slider(page, offset_ms: int) -> None:
    page.get_by_test_id("knowledge-slider").evaluate(
        """(el, offset) => {
            const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            set.call(el, String(Math.round((Date.now() + offset) / 3600000) * 3600000));
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }""",
        offset_ms,
    )


def test_panel_slider_and_aas(seeded, playwright_instance):
    url, lathe, forklift = seeded
    browser, page = open_panel(playwright_instance, url, {"width": 1280, "height": 860})
    try:
        # now: both notes, each with an edge to its anchor and a reporter node, the room's REC type in the tag
        assert node_shown(page, lathe) and node_shown(page, forklift)
        listed = " ".join(facts_listed(page))
        assert "Coolant leak" in listed and "Forklift in the aisle" in listed, listed
        assert page.locator('[data-testid=knowledge-svg] g[data-id$=":person:marta"]').count() == 1
        assert page.get_by_test_id("knowledge-room-type").inner_text() == "rec:ProductionRoom"

        # two days ahead: the forklift note (valid until tomorrow) is gone, the lathe note stays
        set_slider(page, 2 * DAY_MS)
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=knowledge-facts]').innerText.includes('Forklift')"
        )
        assert node_shown(page, lathe) and not node_shown(page, forklift)
        assert page.get_by_test_id("knowledge-time").inner_text() != "Now"
        # "Show ended" brings it back, faded
        page.get_by_text("Show ended").click()
        assert page.locator(f'g.ended[data-id$=":fact:{forklift}"]').count() == 1
        # two days back: nothing was said yet
        page.get_by_text("Show ended").click()
        set_slider(page, -2 * DAY_MS)
        page.wait_for_function(
            "() => document.querySelectorAll('[data-testid=knowledge-svg] g[data-id*=\":fact:\"]').length === 0"
        )

        link = page.get_by_test_id("knowledge-aas")
        href = link.get_attribute("href")
        assert "format=aas" in href and "key=" in href, href
        assert (link.get_attribute("download") or "").endswith(".json")
        export = json.loads(urllib.request.urlopen(url + href, timeout=10).read())
        assert isinstance(export, dict) and export, export
        assert page.errors == [], page.errors
    finally:
        browser.close()


def test_panel_fits_phone(seeded, playwright_instance):
    url, _, _ = seeded
    browser, page = open_panel(playwright_instance, url, {"width": 390, "height": 844}, planner=True)
    try:
        box = page.get_by_test_id("knowledge-panel").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 390 + 0.5, box
        assert page.evaluate("() => document.documentElement.scrollWidth") <= 390
        svg = page.get_by_test_id("knowledge-svg").bounding_box()
        assert svg["width"] <= 390, svg
        assert page.errors == [], page.errors
    finally:
        browser.close()


def test_more_node_expands_as_text_and_labels_are_not_cut(seeded, playwright_instance):
    url, _, _ = seeded
    browser, page = open_panel(playwright_instance, url, {"width": 390, "height": 844}, planner=True)
    try:
        assert "\u2026" not in page.get_by_test_id("knowledge-svg").text_content()
        assert page.get_by_test_id("knowledge-more-list").count() == 0
        more = page.locator("[data-testid=knowledge-svg] g.kg-node.more")
        dot = more.locator("circle.kg-hit")
        if more.count():  # one node for the rest, which opens as plain text below the graph
            dot.click()
            assert page.get_by_test_id("knowledge-more-list").inner_text().startswith("Also here")
            dot.click()
            assert page.get_by_test_id("knowledge-more-list").count() == 0
        assert page.evaluate("() => document.documentElement.scrollWidth") <= 390
        assert page.errors == [], page.errors
    finally:
        browser.close()


def select_room(page, room: str, floor: str) -> None:
    page.evaluate(
        "([id, floor_id]) => window.__twinStore.getState().select({ kind: 'space', id, floor_id })", [room, floor]
    )


def open_page(playwright_instance, url: str, viewport: dict):
    try:
        browser = playwright_instance.chromium.launch()
    except Exception as error:  # noqa: BLE001 - missing browser binary
        pytest.skip(f"chromium not installed: {str(error)[:80]}")
    page = browser.new_context(viewport=viewport).new_page()
    page.route("**/api/speak", lambda route: route.fulfill(status=503, body="no voice"))
    page.goto(f"{url}/?building={DEMO}")
    page.wait_for_function("() => !!window.__twinStore?.getState().model", timeout=30000)
    return browser, page


def test_button_only_for_planner_and_rooms_with_notes(seeded, playwright_instance):
    url, _, _ = seeded
    other = "proc-factory-train-015-F0-S003"  # a room without notes
    browser, page = open_page(playwright_instance, url, {"width": 1280, "height": 860})
    try:
        select_room(page, ROOM, FLOOR)
        page.wait_for_selector("[data-testid=knowledge-open]", timeout=15000)
        select_room(page, other, FLOOR)
        page.wait_for_selector("text=Route", timeout=15000)
        assert page.get_by_test_id("knowledge-open").count() == 0
    finally:
        browser.close()


def test_no_button_on_the_phone(seeded, playwright_instance):
    url, _, _ = seeded
    browser, page = open_page(playwright_instance, url, {"width": 390, "height": 844})
    try:
        select_room(page, ROOM, FLOOR)
        page.wait_for_selector("text=Route", timeout=15000)
        page.wait_for_timeout(1000)  # notes are loaded by now; the room has some
        assert page.get_by_test_id("knowledge-open").count() == 0
    finally:
        browser.close()
