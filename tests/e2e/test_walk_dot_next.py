"""Step guide without motion: Next moves the "You are here" dot (twin/src/walkWithMe.ts stepStart/confirmStep).

Pressing Next means "I did this step": the dot jumps to the end of that step on the route line (door, landing,
stairs), Back moves it back, after a ride the shown floor switches with it. Nothing is sent to the server on Next;
the next chat message carries the confirmed point as context.here. End route midway puts the old position back.
With Walk with me on, Next resets the estimate to the same point, and the Next button is a normal (secondary)
button while the estimate follows, primary again while waiting at stairs/lift.
The chat turn is faked (tests/e2e/fake_chat_server.py): no API key, no cost. Skips without Playwright, a browser,
data/dev or twin/dist.

Run: scripts/build_twin.sh && uv run pytest -m e2e tests/e2e/test_walk_dot_next.py
"""

from __future__ import annotations

import json
import math

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e import test_walk_with_me as walk_with_me

FIND_ROUTE = walk_with_me.FIND_ROUTE
# the same server (fake chat, a multi-floor dev building) and phone-sized page as the Walk with me test
server = walk_with_me.server
page = walk_with_me.page

pytestmark = pytest.mark.e2e

# Distance (m) of a point to the route line on its floor.
OFF_ROUTE = """([point, floor]) => {
  const r = window.__twinStore.getState().state.route;
  const dist = (p, pts) => {
    if (pts.length === 1) return Math.hypot(p[0] - pts[0][0], p[1] - pts[0][1]);
    let best = Infinity;
    for (let i = 1; i < pts.length; i++) {
      const [a, b] = [pts[i - 1], pts[i]], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
      const t = l2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) : 0;
      best = Math.min(best, Math.hypot(a[0] + t * dx - p[0], a[1] + t * dy - p[1]));
    }
    return best;
  };
  return Math.min(...r.segments.filter((s) => s.floor_id === floor).map((s) => dist(point, s.points)));
}"""

# World position of the drawn dot (scene object "here-dot" or "walk-estimate"), model metres.
DOT_WORLD = """(name) => {
  const scene = window.__twinScene;
  const obj = scene && scene.getObjectByName(name);
  if (!obj) return null;
  obj.updateWorldMatrix(true, false);
  const e = obj.matrixWorld.elements;
  return [e[12], -e[14]];
}"""

STATE = """() => { const s = window.__twinStore.getState();
  return { step: s.walkStep, position: s.state.position, pending: s.pendingHere, focused: s.focusedFloorId }; }"""


def _next(page):
    page.get_by_role("button", name="Next", exact=True).click()
    page.wait_for_timeout(450)  # past the 250 ms glide
    return page.evaluate(STATE)


def _check_at_step(page, now):
    pos = now["position"]
    assert pos is not None, "Next set the dot"
    expected = page.evaluate("(step) => window.__walkStepStart(step)", now["step"])
    assert expected["floorId"] == pos["floor_id"]
    assert math.dist(expected["point"], pos["point"]) < 0.05, "the dot sits at the start of the current step"
    assert page.evaluate(OFF_ROUTE, [pos["point"], pos["floor_id"]]) < 0.5, "the dot lies on the route line"
    assert now["focused"] == pos["floor_id"], "the shown floor is the dot's floor"
    assert now["pending"] and now["pending"]["point"] == pos["point"], "kept for the next chat message"
    drawn = page.evaluate(DOT_WORLD, "here-dot") or page.evaluate(DOT_WORLD, "walk-estimate")
    # Guide me follow-cam (scene/FollowCam.tsx): the drawn dot starts at the step and walks it at walking pace, so it
    # is drawn on the route line (at the step start or already ahead of it), not pinned to the start.
    assert drawn is not None, "the dot is drawn"
    assert page.evaluate(OFF_ROUTE, [drawn, pos["floor_id"]]) < 0.5, "the drawn dot lies on the route line"


def test_next_moves_the_dot_back_moves_it_back(page):
    found = page.evaluate(FIND_ROUTE)
    if not found:
        pytest.skip("no route across floors with a walk before the stairs in the picked building")
    steps = found["steps"]
    if len(steps) > 1 and steps[0].startswith(("Start in ", "Start at ")):
        steps = steps[1:]
    ride = next(i for i, line in enumerate(steps) if line.startswith(("Take ", "Use ")))
    assert page.evaluate("() => window.__twinStore.getState().state.position") is None
    page.evaluate("() => { window.__sent.length = 0; window.__twinStore.getState().startWalk(); }")
    page.wait_for_function("() => window.__twinStore.getState().walkStep === 0", timeout=5000)
    next_button = page.get_by_role("button", name="Next", exact=True)
    assert "primary" in next_button.get_attribute("class"), "Walk with me off: Next is the main action"
    start_floor = page.evaluate("() => window.__twinStore.getState().focusedFloorId")

    # Next three times: the dot moves every time, along the route, to successive step boundaries.
    seen = []
    for _ in range(min(3, len(steps) - 1)):
        now = _next(page)
        _check_at_step(page, now)
        assert (
            not seen
            or math.dist(seen[-1]["position"]["point"], now["position"]["point"]) > 0.3
            or (seen[-1]["position"]["floor_id"] != now["position"]["floor_id"])
        ), "the dot moved"
        seen.append(now)
    assert [s["step"] for s in seen] == list(range(1, len(seen) + 1))

    # Back: the dot goes back to the start of the step before.
    page.get_by_role("button", name="Back", exact=True).click()
    page.wait_for_timeout(450)
    back = page.evaluate(STATE)
    _check_at_step(page, back)
    assert back["step"] == seen[-1]["step"] - 1
    if len(seen) >= 2:
        assert back["position"]["point"] == seen[-2]["position"]["point"]

    # Through the stairs/lift: on the ride step the dot waits on the old floor, the step after is on the new one.
    while page.evaluate("() => window.__twinStore.getState().walkStep") < ride:
        _check_at_step(page, _next(page))
    at_ride = page.evaluate(STATE)
    assert at_ride["position"]["floor_id"] == start_floor
    after = _next(page)
    _check_at_step(page, after)
    assert after["position"]["floor_id"] != start_floor, "the dot is on the new floor"
    assert after["focused"] == after["position"]["floor_id"], "the shown floor switched"

    # Nothing reached the server on Next/Back.
    for request in page.evaluate("() => window.__sent"):
        assert "/api/chat" not in request["url"], request
        assert '"here"' not in request["body"], request

    # A question to the agent carries the confirmed point as context.here.
    confirmed = after["position"]
    page.evaluate("() => window.__twinStore.getState().ask('where am I?')")
    page.wait_for_function("() => !window.__twinStore.getState().chatBusy", timeout=10000)
    chats = [r for r in page.evaluate("() => window.__sent") if "/api/chat" in r["url"]]
    assert len(chats) == 1
    here = json.loads(chats[0]["body"])["context"]["here"]
    assert here["space_id"] == confirmed["space_id"] and here["floor_id"] == confirmed["floor_id"]
    assert here["point"] == confirmed["point"]

    # One more step (Back: stays midway, Next could be the last), then End route midway: the guide stops, the
    # guide's own dot goes; what remains is what the server was told (the chat above) or nothing.
    page.get_by_role("button", name="Back", exact=True).click()
    page.wait_for_timeout(450)
    _check_at_step(page, page.evaluate(STATE))
    page.get_by_role("button", name="End route").click()
    page.wait_for_function("() => window.__twinStore.getState().walkStep === null", timeout=5000)
    page.wait_for_timeout(600)
    end = page.evaluate(STATE)
    assert end["pending"] is None
    assert end["position"] is None or end["position"]["point"] == confirmed["point"], "the guide's own dot is gone"
    assert not page.errors, page.errors


def test_done_leaves_the_dot_at_the_destination(page):
    found = page.evaluate(FIND_ROUTE)
    if not found:
        pytest.skip("no route across floors in the picked building")
    page.evaluate("() => window.__twinStore.getState().startWalk()")
    page.wait_for_function("() => window.__twinStore.getState().walkStep === 0", timeout=5000)
    total = page.evaluate("() => window.__twinStore.getState().state.route.steps.length")
    for _ in range(total + 2):
        if page.get_by_role("button", name="Done", exact=True).count():
            break
        page.get_by_role("button", name="Next", exact=True).click()
    page.wait_for_timeout(300)
    destination = page.evaluate("() => window.__walkStepStart(1e9)")
    page.get_by_role("button", name="Done", exact=True).click()
    page.wait_for_function("() => window.__twinStore.getState().walkStep === null", timeout=5000)
    page.wait_for_timeout(800)  # the route is cleared on the server
    pos = page.evaluate("() => window.__twinStore.getState().state.position")
    assert pos and pos["floor_id"] == destination["floorId"]
    assert math.dist(pos["point"], destination["point"]) < 0.05
    assert not page.errors, page.errors


def test_walk_with_me_next_agrees_with_the_dot_and_next_is_secondary(page):
    found = page.evaluate(FIND_ROUTE)
    if not found:
        pytest.skip("no route across floors with a walk before the stairs in the picked building")
    steps = found["steps"]
    if len(steps) > 1 and steps[0].startswith(("Start in ", "Start at ")):
        steps = steps[1:]
    ride = next(i for i, line in enumerate(steps) if line.startswith(("Take ", "Use ")))
    if ride < 2:
        pytest.skip("stairs come right away: no walk step before them")
    page.evaluate("() => window.__twinStore.getState().startWalk()")
    page.wait_for_function("() => window.__twinStore.getState().walkStep === 0", timeout=5000)
    page.get_by_role("switch", name="Walk with me").click()
    page.wait_for_function("() => !!window.__walkMotion.getState().estimate", timeout=5000)
    next_button = page.get_by_role("button", name="Next", exact=True)
    assert "primary" not in next_button.get_attribute("class"), "following: Next is a normal button"
    assert next_button.bounding_box()["height"] >= 44

    _next(page)
    now = page.evaluate(STATE)
    est = page.evaluate("() => window.__walkMotion.getState().estimate")
    assert est["floorId"] == now["position"]["floor_id"]
    assert math.dist(est["point"], now["position"]["point"]) < 0.05, "estimate and dot show the same point"

    while page.evaluate("() => window.__twinStore.getState().walkStep") < ride:
        _next(page)
    page.wait_for_function("() => window.__walkMotion.getState().estimate?.atConnector", timeout=5000)
    assert "primary" in next_button.get_attribute("class"), "waiting at stairs/lift: Next is the main action again"

    after = _next(page)
    est = page.evaluate("() => window.__walkMotion.getState().estimate")
    assert not est["atConnector"]
    assert est["floorId"] == after["position"]["floor_id"] == after["focused"]
    assert math.dist(est["point"], after["position"]["point"]) < 0.05
    assert "primary" not in next_button.get_attribute("class")
    assert not page.errors, page.errors
