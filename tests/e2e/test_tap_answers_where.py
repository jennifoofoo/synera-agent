"""Wanda asks "Where are you?": a tap on the map answers it (twin/src/tapAnswer.ts, twin/src/asksWhere.ts).

Flow: find a floor spot by a normal tap (the room card opens, as without a question), ask a question whose (faked)
reply is "Where are you?", see the hint "Tap where you are", tap the same spot: no card, but a chat request
"I'm here." with context.here (the tapped room and point), and the hint is gone. Afterwards a tap opens the card again.
The first reply is faked with page.route; the second goes to tests/e2e/fake_chat_server.py. No API key, no cost.

Run: scripts/build_twin.sh && uv run pytest -m e2e tests/e2e/test_tap_answers_where.py
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e import test_here_ui as here_ui

# The fake chat server and the desktop/phone page of test_here_ui, shared as fixtures.
server = here_ui.server
page = here_ui.page
shot, tap = here_ui.shot, here_ui.tap

pytestmark = pytest.mark.e2e

SELECTION = "() => { const s = window.__twinAudit.store.getState().selection; return s ? { kind: s.kind, id: s.id, space_id: s.space_id || null, point: s.point || null } : null; }"


def find_floor_spot(page):
    """A screen spot (upper half, clear of the bottom sheet) whose tap selects a room floor; the card is closed again."""
    size = page.viewport_size
    for fy in (0.3, 0.35, 0.25, 0.4, 0.45):
        for fx in (0.5, 0.4, 0.6, 0.3, 0.7, 0.45, 0.55, 0.35, 0.65):
            x, y = size["width"] * fx, size["height"] * fy
            tap(page, x, y)
            page.wait_for_timeout(150)
            if page.locator("[data-testid=card-point]").count():
                selection = page.evaluate(SELECTION)
                space_id = selection["id"] if selection["kind"] == "space" else selection["space_id"]
                return x, y, space_id
    pytest.fail("no tap landed on a floor")


def test_tap_answers_where_are_you(page, server):
    # 1. no pending question: a tap opens the room card as before
    x, y, space_id = find_floor_spot(page)
    assert page.locator(".card-selection").count() == 1
    page.evaluate("() => window.__twinAudit.store.getState().select(null)")
    page.wait_for_timeout(200)

    requests = []

    def on_chat(route):
        body = json.loads(route.request.post_data or "{}")
        requests.append(body)
        if len(requests) == 1:
            reply = {"reply": "I need your position first. Where are you?", "backend": "fake"}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(reply))
        else:
            route.continue_()

    page.route("**/api/chat", on_chat)

    # 2. a question without a position: Wanda asks where, the hint shows
    page.evaluate("() => window.__twinAudit.store.getState().ask('Where is the nearest coffee machine?')")
    hint = page.locator("[data-testid=tap-where]")
    hint.wait_for(state="visible", timeout=10000)
    assert "Tap where you are" in hint.inner_text()
    assert len(requests) == 1
    shot(page, "tap-where-hint")

    # 3. the tap answers: "I'm here." with context.here of the tapped room, no card
    tap(page, x, y)
    for _ in range(50):
        if len(requests) >= 2:
            break
        page.wait_for_timeout(100)
    assert len(requests) == 2, "the tap did not send a chat message"
    answer = requests[1]
    assert answer["message"] == "I'm here."
    here = answer["context"]["here"]
    assert here["space_id"] == space_id
    assert here.get("point"), "the exact tapped point travels with context.here"
    assert "space_id" not in answer["context"], "no selection context with the answer"
    hint.wait_for(state="hidden", timeout=5000)
    page.wait_for_function("!window.__twinAudit.store.getState().chatBusy", timeout=10000)
    assert page.locator(".card-selection").count() == 0, "the answering tap must not open the room card"
    position = page.evaluate("() => window.__twinAudit.store.getState().state.position")
    assert position and position["space_id"] == space_id
    shot(page, "tap-where-answered")

    # 4. the question is answered: the next tap opens the card again
    tap(page, x, y)
    page.locator(".card-selection").wait_for(state="visible", timeout=5000)
    assert len(requests) == 2
    assert not page.errors, page.errors


def test_hint_dismiss_keeps_taps_normal(page, server):
    if page.kind != "desktop":
        pytest.skip("one viewport is enough: dismissing is store logic")
    x, y, _ = find_floor_spot(page)
    page.evaluate("() => window.__twinAudit.store.getState().select(null)")
    page.route(
        "**/api/chat",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"reply": "Which room are you in?", "backend": "fake"}),
        ),
    )
    page.evaluate("() => window.__twinAudit.store.getState().ask('Where is the exit?')")
    hint = page.locator("[data-testid=tap-where]")
    hint.wait_for(state="visible", timeout=10000)
    hint.get_by_role("button", name="Not now").click()
    hint.wait_for(state="hidden", timeout=5000)
    tap(page, x, y)
    page.locator(".card-selection").wait_for(state="visible", timeout=5000)
    assert not page.errors, page.errors
