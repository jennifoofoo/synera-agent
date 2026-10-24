import json
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError

from building_agent import routing
from building_agent import walk as walking
from building_agent.guide_tools import GuideState, building_signature, make_guide_tools
from building_agent.tools import make_tools
from starter_agent.building_map import MapError
from tests.conftest import labelled_questions, load_map
from tests.test_walk import neighbour_pair


def fresh_map(building_dir: str):
    """Edits mutate the map, so tests that edit work on their own copy."""
    from starter_agent.building_map import BuildingMap

    return BuildingMap.load(Path(building_dir))


def route_question():
    building_dir, question = labelled_questions("errand")[0]
    bm = fresh_map(building_dir)
    start = bm.resolve_space(question["inputs"]["start"])
    # The kit model has no way round the outside: take the first asset room that can be reached from the start.
    for asset in bm.assets.values():
        try:
            if asset["space_id"] != start and routing.route(bm, start, asset["space_id"]).length_m > 0:
                return bm, [start, asset["space_id"]]
        except MapError:
            continue
    raise AssertionError("no reachable asset room")


def tools_by_name(bm, tmp_path):
    state = GuideState()
    tools = {tool.name: tool for tool in make_guide_tools(bm, tmp_path, state)}
    return tools, state


def long_route(bm):
    """Two rooms whose route has at least 3 steps (an overview). Fails if the building has none."""
    rooms = [space_id for space_id, space in bm.spaces.items() if space["type"] == "room"]
    for start in rooms[:15]:
        for end in rooms[-15:]:
            if start == end:
                continue
            try:
                route = routing.route(bm, start, end)
            except MapError:
                continue
            if len(walking.build_walk(bm, route).steps) >= walking.MIN_STEPS_FOR_OVERVIEW:
                return start, end
    pytest.fail("no route of 3 or more steps in this building")


def test_a_long_route_is_an_overview_then_one_step_at_a_time(tmp_path):
    bm, _ = route_question()
    start, end = long_route(bm)
    tools, _ = tools_by_name(bm, tmp_path)
    first = json.loads(tools["give_directions"](start=start, destination=end))
    assert "steps" not in first
    assert first["mode"] == "overview" and 2 <= len(first["landmarks"]) <= 4 and first["offer"]
    guided = json.loads(tools["walk"](said="yes"))
    assert guided["step_number"] == 1
    assert json.loads(tools["repeat_steps"]())["step"] == guided["step"]
    seen = [guided["step"]]
    while not guided["arrived"]:
        guided = json.loads(tools["next_steps"]())
        seen.append(guided["step"])
        assert 1 <= guided["step_number"] <= first["steps_total"]
    assert len(seen) == first["steps_total"]


def test_a_short_route_is_read_out_at_once_and_repeats_in_full(tmp_path):
    bm, _ = route_question()
    tools, _ = tools_by_name(bm, tmp_path)
    pair = neighbour_pair(bm)
    first = json.loads(tools["give_directions"](start=pair[0], destination=pair[1]))
    assert 1 <= len(first["steps"]) <= 2
    assert json.loads(tools["repeat_steps"]())["steps"] == first["steps"]  # 'nochmal' gives the same steps again
    assert json.loads(tools["walk"](said="repeat"))["steps"] == first["steps"]
    assert json.loads(tools["next_steps"]())["done"] is True


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
    if state.walk.mode == "plain":  # all steps were read out: they are simply out of date
        with pytest.raises(ToolError, match="changed"):
            tools["next_steps"]()
    else:  # a walk folds the change in: the destination is closed, so there is no route any more
        assert json.loads(tools["next_steps"]())["no_route"] is True
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


def test_new_actions_are_registered_and_change_the_signature():
    from building_agent.guide_tools import ACTIONS, building_signature

    assert {"remove_door", "widen_door", "move_asset"} <= set(ACTIONS)
    bm = fresh_map(str(min(Path("data/dev").glob("*"))))
    before = building_signature(bm)
    door = next(o for o in bm.openings.values() if "outside" not in o["space_ids"])
    door["width_m"] = 3.3
    assert building_signature(bm) != before


# ---------- add_asset, hints and undo ----------


def do(tools, state, reply="Ja, mach das", **kwargs):
    """Propose in one message, confirm in the next, like a real conversation."""
    state.begin_turn()
    card = json.loads(tools["propose_change"](**kwargs))
    state.begin_turn()
    return card, json.loads(tools["confirm_change"](confirmed=True, user_reply=reply))


def undo(tools, state):
    state.begin_turn()
    card = json.loads(tools["propose_change"](action="undo"))
    state.begin_turn()
    return card, json.loads(tools["confirm_change"](confirmed=True, user_reply="ja"))


def factory_tools(tmp_path):
    from tests.test_edit_ops import factory

    bm = factory()
    tools, state = tools_by_name(bm, tmp_path)
    return bm, tools, state


def test_cards_for_hints_and_new_assets_read_in_plain_words(tmp_path):
    bm, tools, state = factory_tools(tmp_path)
    state.begin_turn()
    card = json.loads(
        tools["propose_change"](action="add_asset", element="H-A2", asset_type="cnc mill", hint={"anchor": "NW"})
    )
    lines = card["effect on the whole building"]
    assert card["I understood"].startswith("Add a new CNC mill H-A2")
    assert any("north-west corner, 0.05 m from both walls" in line for line in lines)
    assert any("source generated" in line for line in lines) and card["status"].startswith("nothing changed")
    assert len(bm.assets) == 4 and "B-A00005" not in bm.assets
    state.begin_turn()
    card = json.loads(
        tools["propose_change"](action="move_asset", element="B-A2", to_space="H-A2", hint={"anchor": "SE"})
    )
    lines = card["effect on the whole building"]
    assert any("south-east corner" in line for line in lines)
    state.begin_turn()
    card = json.loads(tools["propose_change"](action="move_asset", element="B-A1", hint={"point": [8, 5]}))
    assert any("Could not use the exact point" in line for line in card["effect on the whole building"])
    state.begin_turn()
    card = json.loads(tools["propose_change"](action="move_asset", element="B-A1", hint={"anchor": "E"}))
    assert any("Could not reach the exact east wall" in line for line in card["effect on the whole building"])


def test_bad_new_actions_are_tool_errors_that_change_nothing(tmp_path):
    bm, tools, state = factory_tools(tmp_path)
    before = building_signature(bm)
    for kwargs in [
        {"action": "add_asset", "element": "H-A2"},
        {"action": "add_asset", "asset_type": "cnc_mil", "to_space": "H-A2"},
        {"action": "add_asset", "asset_type": "chair"},
        {"action": "add_asset", "asset_type": "chair", "to_space": "H-A2", "hint": {"point": [1, 1]}},
        {"action": "move_asset", "element": "B-A1"},
        {"action": "undo"},
    ]:
        state.begin_turn()
        with pytest.raises(ToolError):
            tools["propose_change"](**kwargs)
    assert building_signature(bm) == before and state.pending is None


def snapshot_of(bm):
    return json.dumps([bm.data["assets"], bm.data["openings"], sorted(bm.closed)], sort_keys=True)


def test_undo_a_move_restores_signature_letters_and_aliases(tmp_path):
    from tests.test_edit_ops import assert_in_sync, names

    bm, tools, state = factory_tools(tmp_path)
    original, signature = snapshot_of(bm), building_signature(bm)
    do(tools, state, action="move_asset", element="B-A2", to_space="H-A2", hint={"anchor": "NE"})
    assert names(bm, "B-A2") == ["CNC mill H-A2"] and bm.assets["B-A2"]["aliases"] == ["CNC mill H-A1-B"]
    card, result = undo(tools, state)
    assert card["I understood"] == "Undo: move CNC mill H-A2 back to Hall H-A1."
    assert result["applied"] and building_signature(bm) == signature and snapshot_of(bm) == original
    assert names(bm, "B-A1", "B-A2", "B-A3") == [f"CNC mill H-A1-{c}" for c in "ABC"]
    assert "aliases" not in bm.assets["B-A2"] and bm.last_route is None and state.session is None
    assert_in_sync(bm)
    assert bm.moved_assets["B-A2"]["space_id"] == "B-F0-S0" and bm.moved_assets["B-A2"]["name"] == "CNC mill H-A1-B"


def test_undo_an_added_asset_removes_it_and_reports_it(tmp_path):
    from tests.test_edit_ops import assert_in_sync

    bm, tools, state = factory_tools(tmp_path)
    signature = building_signature(bm)
    do(tools, state, action="add_asset", to_space="H-A2", asset_type="chair")
    assert "B-A00005" in bm.assets and "B-A00005" in bm.added_assets
    card, _ = undo(tools, state)
    assert "remove the added Chair H-A2" in card["I understood"]
    assert "B-A00005" not in bm.assets and bm.added_assets == {} and bm.removed_assets == ["B-A00005"]
    assert building_signature(bm) == signature
    assert_in_sync(bm)
    saved = json.loads((tmp_path / "building_edited.json").read_text())
    assert len(saved["assets"]) == 4


def test_several_undos_in_reverse_order(tmp_path):
    bm, tools, state = factory_tools(tmp_path)
    states = [snapshot_of(bm)]
    do(tools, state, action="move_asset", element="B-A1", to_space="H-A3")
    states.append(snapshot_of(bm))
    do(tools, state, action="add_asset", to_space="H-A2", asset_type="cnc_mill", hint={"anchor": "SW"})
    states.append(snapshot_of(bm))
    do(tools, state, action="close", element="B-O1")
    states.append(snapshot_of(bm))
    do(tools, state, action="move_asset", element="B-A2", hint={"rotation_deg": 90})
    for expected in reversed(states):
        undo(tools, state)
        assert snapshot_of(bm) == expected
    state.begin_turn()
    with pytest.raises(ToolError, match="nothing to undo"):
        tools["propose_change"](action="undo")


def test_undo_stack_holds_twenty_steps(tmp_path):
    bm = fresh_map(str(min(Path("data/dev").glob("*/building.json")).parent))
    tools, state = tools_by_name(bm, tmp_path)
    door = next(iter(bm.openings))
    for number in range(25):
        do(tools, state, action="reopen" if number % 2 else "close", element=door)
    assert len(state.undo) == 20
    for _ in range(20):
        undo(tools, state)
    assert len(state.undo) == 0
    state.begin_turn()
    with pytest.raises(ToolError, match="nothing to undo"):
        tools["propose_change"](action="undo")


def test_undo_after_assume_closed_reopens(tmp_path):
    bm, tools, state = factory_tools(tmp_path)
    tools["assume_closed"](element="B-O2")
    assert "B-O2" in bm.closed
    card, _ = undo(tools, state)
    assert "reopen" in card["I understood"] and bm.closed == set()


def test_undo_restores_a_removed_and_widened_door(tmp_path):
    from tests.test_edit_ops import assert_in_sync

    bm, tools, state = factory_tools(tmp_path)
    original = snapshot_of(bm)
    do(tools, state, action="widen_door", element="B-O1", width_m=2.0)
    do(tools, state, action="remove_door", element="B-O2")
    assert bm.removed_openings == ["B-O2"] and bm.widened_openings == {"B-O1": 2.0}
    undo(tools, state)
    assert bm.removed_openings == [] and "B-O2" in bm.openings
    undo(tools, state)
    assert snapshot_of(bm) == original and bm.widened_openings == {}
    assert_in_sync(bm)


def new_action_cases(tmp_path):
    """(tools, state, bm, kwargs) for each new action; undo needs an earlier edit."""
    cases = []
    for name in ("add_asset", "move_hint", "undo"):
        bm, tools, state = factory_tools(tmp_path)
        if name == "undo":
            do(tools, state, action="close", element="B-O1")
            kwargs = {"action": "undo"}
        elif name == "add_asset":
            kwargs = {"action": "add_asset", "to_space": "H-A2", "asset_type": "cnc_mill", "hint": {"anchor": "NW"}}
        else:
            kwargs = {"action": "move_asset", "element": "B-A2", "hint": {"anchor": "SW"}}
        cases.append((tools, state, bm, kwargs))
    return cases


@pytest.mark.parametrize("index", [0, 1, 2])
def test_guard_for_new_actions(index, tmp_path):
    tools, state, bm, kwargs = new_action_cases(tmp_path)[index]
    signature = building_signature(bm)
    stack = len(state.undo)

    state.begin_turn()
    card = json.loads(tools["propose_change"](**kwargs))
    assert "waiting" in card["status"]
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="ja")  # same message
    assert building_signature(bm) == signature

    state.begin_turn()
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="hmm, vielleicht")  # vague
    assert building_signature(bm) == signature and len(state.undo) == stack

    state.begin_turn()
    tools["propose_change"](**kwargs)
    state.begin_turn()
    state.begin_turn()  # the card is one message too old
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="ja")
    assert building_signature(bm) == signature and len(state.undo) == stack

    state.begin_turn()
    tools["propose_change"](**kwargs)
    state.begin_turn()  # topic switch inside the answer
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="ja, aber lieber etwas anderes")
    assert building_signature(bm) == signature and len(state.undo) == stack

    state.begin_turn()
    tools["propose_change"](**kwargs)
    state.begin_turn()
    bm.closed.add("B-O2")  # the building changes behind the card
    with pytest.raises(ToolError, match="changed"):
        tools["confirm_change"](confirmed=True, user_reply="ja")


@pytest.mark.parametrize("index", [0, 1, 2])
def test_new_actions_apply_after_a_clear_yes_and_declined_ones_do_not(index, tmp_path):
    tools, state, bm, kwargs = new_action_cases(tmp_path)[index]
    signature = building_signature(bm)
    state.begin_turn()
    tools["propose_change"](**kwargs)
    state.begin_turn()
    assert json.loads(tools["confirm_change"](confirmed=False, user_reply="nein"))["applied"] is False
    assert building_signature(bm) == signature
    state.begin_turn()
    tools["propose_change"](**kwargs)
    state.begin_turn()
    assert json.loads(tools["confirm_change"](confirmed=True, user_reply="Ja"))["applied"] is True
    assert building_signature(bm) != signature


def test_signature_sees_names_and_rotation():
    from tests.test_edit_ops import factory

    bm = factory()
    base = building_signature(bm)
    bm.assets["B-A1"]["name"] = "Renamed"
    changed_name = building_signature(bm)
    bm.assets["B-A1"]["footprint"]["rotation_deg"] = 45
    assert len({base, changed_name, building_signature(bm)}) == 3


def test_directions_go_stale_after_an_undo(tmp_path):
    _bm, tools, state = factory_tools(tmp_path)
    do(tools, state, action="widen_door", element="B-O1", width_m=2.0)
    state.begin_turn()
    tools["give_directions"](start="H-A1", destination="H-A3")
    undo(tools, state)
    # the undone widening does not change the route: the walk stays and says nothing about a new route
    result = json.loads(tools["next_steps"]())
    assert result["mode"] == "overview" and "no_route" not in result and "rerouted" not in result


def test_undo_is_refused_when_the_building_changed_in_another_way(tmp_path):
    bm, (_start, end) = route_question()
    tools, state = tools_by_name(bm, tmp_path)
    state.begin_turn()
    tools["assume_closed"](element=bm.resolve_space(end))
    bm.closed.add(next(iter(bm.connectors)))  # a page-side closure that bypasses the undo stack
    state.begin_turn()
    with pytest.raises(ToolError, match="changed in another way"):
        tools["propose_change"](action="undo")
    assert not state.undo
