"""Wanda asked where the person is, then "I'm here" on a room with notes: the question goes on at once, no notes sheet.

The demo bug (Urban Colab): "Where is the nearest toilet?" got "Could you tap the room you're in on the plan, or tell
me its name or number?"; "I'm here" on Flur Süd only set the pill, nothing was sent, and the "What's here?" sheet
opened over the conversation. Now the chat reply's needs_position (web/chat.py) makes the page wait for a place
(twin/src/asksWhere.ts waitsForPlace), "I'm here" on the room card answers with "I'm here." and context.here
(twin/src/tapAnswer.ts hereAnswers), and the notes sheet never opens by itself on a position change.

The first reply is faked with page.route; the second goes to tests/e2e/fake_chat_server.py. No API key, no cost.
Run: scripts/build_twin.sh && uv run --group e2e pytest -m e2e tests/e2e/test_here_answers_pending.py
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e import test_round_and_notes as round_notes

# The fake chat server on the demo building and its desktop page, shared as fixtures.
server = round_notes.server
page = round_notes.page
space_id, wait_until = round_notes.space_id, round_notes.wait_until

pytestmark = pytest.mark.e2e

BUG_REPLY = (
    "I can't see a spot marked on the map yet. Could you tap the room you're in on the plan, or tell me its name or "
    "number? Then I'll find the closest toilet for you."
)


def test_im_here_answers_the_pending_question_and_keeps_notes_closed(page):
    room = space_id(page, "Server room 0.16")
    # A room with a note: before the fix, setting the position there opened the "What's here?" sheet.
    wait_until(page, "() => window.__twinNotes.useNotes.getState().storage?.kind === 'server'")
    page.evaluate("(id) => window.__twinStore.getState().select({ kind: 'space', id })", room)
    assert page.evaluate("() => window.__twinNotes.addNoteHere('rack 3 fan is loud')").startswith("Noted at")
    page.evaluate("() => window.__twinStore.getState().select(null)")
    assert page.evaluate("() => window.__twinNotes.useNotes.getState().sheet") == "closed"

    requests = []

    def on_chat(route):
        requests.append(json.loads(route.request.post_data or "{}"))
        if len(requests) == 1:
            reply = {"reply": BUG_REPLY, "backend": "fake", "needs_position": True}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(reply))
        else:
            route.continue_()

    page.route("**/api/chat", on_chat)
    page.evaluate("() => window.__twinStore.getState().ask('Where is the nearest toilet?')")
    wait_until(page, "() => !!window.__twinStore.getState().awaitingPlace")  # the hint "Tap where you are" shows
    assert page.locator("[data-testid=tap-where]").count() == 1
    assert len(requests) == 1

    # She opens the room and presses "I'm here" (the card path; a plain map tap is test_tap_answers_where.py).
    page.evaluate("(id) => window.__twinStore.getState().select({ kind: 'space', id })", room)
    page.locator(".card-selection").get_by_role("button", name="I'm here").click()
    for _ in range(150):
        if len(requests) >= 2:
            break
        page.wait_for_timeout(100)
    assert len(requests) == 2, "'I'm here' did not answer Wanda's pending question"
    assert requests[1]["message"] == "I'm here."
    assert requests[1]["context"]["here"]["space_id"] == room
    wait_until(page, "() => !window.__twinStore.getState().chatBusy")
    assert page.evaluate("() => window.__twinStore.getState().state.position.space_id") == room
    page.wait_for_timeout(500)
    assert page.evaluate("() => window.__twinNotes.useNotes.getState().sheet") == "closed", "notes sheet opened"
    assert page.locator("[data-testid=tap-where]").count() == 0

    # Nothing pending any more: "I'm here" on another room only sets the position, no chat message.
    other = space_id(page, "Main aisle H-B3")
    page.evaluate("(id) => window.__twinStore.getState().select({ kind: 'space', id })", other)
    page.locator(".card-selection").get_by_role("button", name="I'm here").click()
    page.wait_for_timeout(500)
    assert len(requests) == 2
    assert page.evaluate("() => window.__twinStore.getState().state.position.space_id") == other
