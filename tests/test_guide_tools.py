import json
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError

from building_agent.guide_tools import GuideState, make_guide_tools
from building_agent.tools import make_tools
from tests.conftest import labelled_questions, load_map


def fresh_map(building_dir: str):
    """Edits mutate the map, so tests that edit work on their own copy."""
    from starter_agent.building_map import BuildingMap

    return BuildingMap.load(Path(building_dir))


def route_question():
    building_dir, question = labelled_questions("errand")[0]
    bm = fresh_map(building_dir)
    stops = [bm.resolve_space(question["inputs"]["start"]), next(iter(bm.assets.values()))["space_id"]]
    return bm, stops


def tools_by_name(bm, tmp_path):
    state = GuideState()
    tools = {tool.name: tool for tool in make_guide_tools(bm, tmp_path, state)}
    return tools, state


def test_directions_come_in_chunks_of_three_with_next_and_repeat(tmp_path):
    bm, (start, end) = route_question()
    tools, _ = tools_by_name(bm, tmp_path)
    first = json.loads(tools["give_directions"](start=start, destination=end))
    assert len(first["steps"]) <= 3
    assert json.loads(tools["repeat_steps"]())["steps"] == first["steps"]
    seen = list(first["steps"])
    while True:
        more = json.loads(tools["next_steps"]())
        if more["done"]:
            break
        assert len(more["steps"]) <= 3
        seen += more["steps"]
    assert len(seen) == len(first["steps"]) + first["steps_remaining"]


def test_next_steps_without_directions_is_a_tool_error(tmp_path):
    bm, _ = route_question()
    tools, _ = tools_by_name(bm, tmp_path)
    with pytest.raises(ToolError):
        tools["next_steps"]()


def test_change_needs_a_new_user_message_before_it_is_applied(tmp_path):
    bm, (start, end) = route_question()
    tools, state = tools_by_name(bm, tmp_path)
    state.begin_turn()
    tools["give_directions"](start=start, destination=end)
    card = json.loads(tools["propose_change"](action="close", element=bm.resolve_space(end)))
    assert "waiting" in card["status"]
    assert bm.closed == set()
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True)  # same turn
    state.begin_turn()
    result = json.loads(tools["confirm_change"](confirmed=True))
    assert result["applied"] is True
    assert bm.resolve_space(end) in bm.closed


def test_declined_change_changes_nothing(tmp_path):
    bm, (_start, end) = route_question()
    tools, state = tools_by_name(bm, tmp_path)
    state.begin_turn()
    tools["propose_change"](action="close", element=bm.resolve_space(end))
    state.begin_turn()
    assert json.loads(tools["confirm_change"](confirmed=False))["applied"] is False
    assert bm.closed == set()
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True)  # nothing pending any more


def test_unknown_action_is_a_tool_error(tmp_path):
    bm, _ = route_question()
    tools, _ = tools_by_name(bm, tmp_path)
    with pytest.raises(ToolError):
        tools["propose_change"](action="demolish", element="x")


def test_agent_tools_replace_raw_edit_tools():
    building_dir, _ = labelled_questions("errand")[0]
    names = {tool.name for tool in make_tools(load_map(building_dir), Path("agent_output") / "test")}
    assert {"give_directions", "propose_change", "confirm_change", "next_steps", "repeat_steps"} <= names
    assert not {"set_closed", "add_door"} & names
