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
        tools["confirm_change"](confirmed=True, user_reply="ja")  # same turn
    state.begin_turn()
    result = json.loads(tools["confirm_change"](confirmed=True, user_reply="Ja, bitte"))
    assert result["applied"] is True
    assert bm.resolve_space(end) in bm.closed


def test_declined_change_changes_nothing(tmp_path):
    bm, (_start, end) = route_question()
    tools, state = tools_by_name(bm, tmp_path)
    state.begin_turn()
    tools["propose_change"](action="close", element=bm.resolve_space(end))
    state.begin_turn()
    assert json.loads(tools["confirm_change"](confirmed=False, user_reply="nein"))["applied"] is False
    assert bm.closed == set()
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="ja")  # nothing pending any more


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


def test_stale_card_expires_after_an_unrelated_message(tmp_path):
    bm, (_start, end) = route_question()
    tools, state = tools_by_name(bm, tmp_path)
    state.begin_turn()
    tools["propose_change"](action="close", element=bm.resolve_space(end))
    state.begin_turn()  # the person answers
    state.begin_turn()  # ...but this is a later, unrelated message
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="ja")


def test_only_a_clear_yes_confirms(tmp_path):
    bm, (_start, end) = route_question()
    tools, state = tools_by_name(bm, tmp_path)
    for reply in ("where is the kitchen?", "nein, lieber nicht", "ja aber nicht jetzt"):
        state.begin_turn()
        tools["propose_change"](action="close", element=bm.resolve_space(end))
        state.begin_turn()
        with pytest.raises(ToolError):
            tools["confirm_change"](confirmed=True, user_reply=reply)
        assert bm.closed == set()


def test_second_proposal_in_one_message_is_refused(tmp_path):
    bm, (_start, end) = route_question()
    tools, state = tools_by_name(bm, tmp_path)
    state.begin_turn()
    tools["propose_change"](action="close", element=bm.resolve_space(end))
    with pytest.raises(ToolError):
        tools["propose_change"](action="close", element=bm.resolve_space(end))


def test_noop_changes_are_refused_and_card_uses_names_not_ids(tmp_path):
    bm, (_start, end) = route_question()
    tools, state = tools_by_name(bm, tmp_path)
    state.begin_turn()
    with pytest.raises(ToolError):
        tools["propose_change"](action="reopen", element=bm.resolve_space(end))  # not closed
    card = json.loads(tools["propose_change"](action="close", element=bm.resolve_space(end)))
    assert bm.spaces[bm.resolve_space(end)]["name"] in card["I understood"]


def test_directions_and_cards_go_stale_when_the_building_changes(tmp_path):
    bm, (start, end) = route_question()
    tools, state = tools_by_name(bm, tmp_path)
    state.begin_turn()
    tools["give_directions"](start=start, destination=end)
    bm.set_closed(bm.resolve_space(end), True)  # e.g. the user closes something on the page
    with pytest.raises(ToolError, match="changed"):
        tools["next_steps"]()
    tools["propose_change"](action="reopen", element=bm.resolve_space(end))
    bm.set_closed(bm.resolve_space(end), False)  # page edit between card and answer
    state.begin_turn()
    with pytest.raises(ToolError, match="changed"):
        tools["confirm_change"](confirmed=True, user_reply="ja")


@pytest.mark.parametrize("reply", ["mach einfach", "ja ja", "whatever", "ja, aber nicht Lift 1", "ok"])
def test_vague_or_conditional_replies_do_not_confirm(tmp_path, reply):
    bm, (_start, end) = route_question()
    tools, state = tools_by_name(bm, tmp_path)
    state.begin_turn()
    tools["propose_change"](action="close", element=bm.resolve_space(end))
    state.begin_turn()
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply=reply)
    assert bm.closed == set()


def test_stated_closure_applies_at_once_and_routes_respect_it(tmp_path):
    bm, (start, end) = route_question()
    tools, state = tools_by_name(bm, tmp_path)
    state.begin_turn()
    before = json.loads(tools["give_directions"](start=start, destination=end))["length_m"]
    connector = next(iter(bm.connectors))
    result = json.loads(tools["assume_closed"](element=connector))
    assert connector in bm.closed and connector in " ".join(result["all_closed"])
    try:
        after = json.loads(tools["give_directions"](start=start, destination=end))["length_m"]
    except ToolError:
        after = None  # no route any more is also a valid effect of a closure
    assert after is None or after >= before


def test_agent_tools_include_assume_closed():
    from building_agent.tools import make_tools

    building_dir, _ = labelled_questions("errand")[0]
    assert "assume_closed" in {tool.name for tool in make_tools(load_map(building_dir), tmp_dir())}


def tmp_dir():
    return Path("agent_output") / "test"


def test_close_card_describes_the_effect_on_the_whole_building(tmp_path):
    bm, _ = route_question()
    tools, state = tools_by_name(bm, tmp_path)
    state.begin_turn()
    connector = next(iter(bm.connectors))
    card = json.loads(tools["propose_change"](action="close", element=connector))
    assert card["effect on the whole building"], "the card needs plain sentences about the building"
    assert bm.closed == set()  # still only a proposal
