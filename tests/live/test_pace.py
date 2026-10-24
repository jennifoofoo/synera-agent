"""Live conversation with auto-pace 'ask' on a 5+ step route (docs/specs/auto-pace.md). Ticks and wait are answered by
the server without the model, so the assertions are exact; only the spoken steps come from the model."""

import json
import re

import pytest

from tests.live.harness import TICK, run_script
from tests.live.test_walk import assert_speakable, route_case, step_results


@pytest.mark.live
def test_ask_mode_ticks_ask_yes_advances_wait_pauses_go_continues():
    path, bm, start, end, _lift = route_case()
    start_name, end_name = bm.spaces[start]["name"], bm.spaces[end]["name"]
    transcript = run_script(
        path,
        [
            f"I'm in {start_name}. How do I get to {end_name}?",
            "yes please",
            TICK,
            "yes",
            TICK,
            TICK,
            "wait",
            TICK,
            "go",
            TICK,
        ],
        pace="ask",
    )
    turns = transcript.turns
    # 1 and 2: the overview, then the first step with its walking time added by the server
    assert turns[0].called("give_directions") and not step_results(transcript, 0)
    first = step_results(transcript, 1)
    assert first and first[-1]["step_number"] == 1
    assert re.search(r"\b(about|around)\b.*\b(seconds?|minutes?|minute)\b", turns[1].reply, re.IGNORECASE)
    assert_speakable(turns[1].reply)
    # 3: the tick asks for step 2 in one sentence, no model call, nothing moved
    assert turns[2].reply == "Ready for step 2?" and not turns[2].calls
    # 4: yes advances exactly one step
    second = step_results(transcript, 3)
    assert second and second[-1]["step_number"] == 2
    # 5 and 6: one question per step, a second tick on the same step is dropped
    assert turns[4].reply == "Ready for step 3?" and not turns[4].calls
    assert turns[5].reply == "" and not turns[5].calls
    # 7 and 8: wait pauses at once, a tick while paused says nothing
    assert "go" in turns[6].reply and not turns[6].calls
    assert turns[7].reply == "" and not turns[7].calls
    # 9: go continues with step 3, 10: and the timer asks about step 4 again
    third = step_results(transcript, 8)
    assert third and third[-1]["step_number"] == 3
    assert turns[9].reply == "Ready for step 4?" and not turns[9].calls
    assert all("guide_tick" not in json.dumps([c.args for c in t.calls]) for t in turns)
