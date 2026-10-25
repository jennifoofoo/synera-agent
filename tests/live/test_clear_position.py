"""Live: 'I'm not there any more' removes the position (clear_position) and Wanda asks back without tool talk."""

import re
from pathlib import Path

import pytest

from starter_agent.building_map import BuildingMap
from tests.live.harness import run_script

TOOL_TALK = re.compile(r"\btools?\b|\bfunction\b|\bS\d{3}\b|clear_position|set_position", re.IGNORECASE)


@pytest.mark.live
def test_not_there_any_more_clears_the_position_and_asks_back():
    path = min(Path("data/dev").glob("proc-*/building.json")).parent
    bm = BuildingMap.load(path)
    names = [space["name"] for space in bm.spaces.values()]
    room = next(s for s in bm.spaces.values() if s["type"] == "room" and names.count(s["name"]) == 1)
    transcript = run_script(path, [f"I'm in {room['name']}.", "I'm not there any more."])
    assert transcript.turns[0].called("set_position"), transcript.turns[0].calls
    cleared = [call for call in transcript.turns[1].called("clear_position") if not call.is_error]
    assert cleared, transcript.turns[1].calls
    assert not transcript.turns[1].called("set_position"), transcript.turns[1].calls
    reply = transcript.replies()[1]
    assert "?" in reply, reply
    assert not TOOL_TALK.search(reply), reply
