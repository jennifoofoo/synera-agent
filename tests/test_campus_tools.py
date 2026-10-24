"""Campus tools: routes with chunked directions, and link changes behind the card and the clear yes."""

import json

import pytest
from anthropic.lib.tools import ToolError

from building_agent.campus import entrances, load_campus, load_maps, make_example_campus
from building_agent.campus_tools import CampusHolder, make_campus_tools
from building_agent.guide_tools import GuideState, make_guide_tools
from tests.conftest import DATA

CAMPUS_A, FACTORY, RESPLAN = "proc-campus-dev-000", "proc-factory-dev-003", "resplan-439"


def setup(tmp_path, drop_second_link: bool = False):
    campus = make_example_campus(DATA)
    if drop_second_link:
        campus.links.pop()
    maps, _ = load_maps(campus)
    holder = CampusHolder(campus, maps, path=tmp_path / "campus.json", bm=maps[CAMPUS_A])
    state = GuideState()
    tools = {tool.name: tool for tool in make_campus_tools(holder, tmp_path, state)}
    guide = {tool.name: tool for tool in make_guide_tools(maps[CAMPUS_A], tmp_path, state)}
    return holder, state, tools, guide


def space_in(holder, building_id: str, index: int = 0) -> str:
    bm = holder.maps[building_id]
    return sorted(space for space, item in bm.spaces.items() if item["room_type"] != "corridor")[index]


def call(tool, **kwargs):
    return json.loads(tool(**kwargs))


def test_list_buildings_shows_entrances_and_links(tmp_path):
    _holder, _, tools, _ = setup(tmp_path)
    result = call(tools["list_buildings"])
    assert len(result["buildings"]) == 3 and len(result["links"]) == 2
    first = result["buildings"][0]
    assert first["floors"] >= 1 and first["entrances"] and "side" in first["entrances"][0]
    assert result["links"][0]["between"] == ["Hörsaalzentrum 024", "Fertigung Ost 27"]


def test_campus_route_hands_out_three_steps_and_next_steps_works(tmp_path):
    holder, state, tools, guide = setup(tmp_path)
    state.begin_turn()
    result = call(
        tools["campus_route"], start=space_in(holder, CAMPUS_A), destination=space_in(holder, RESPLAN), step_free=True
    )
    assert 0 < len(result["steps"]) <= 3
    assert result["buildings"] == ["Hörsaalzentrum 024", "Fertigung Ost 27", "Residence 439"]
    assert len(result["links_used"]) == 2 and result["normal_route_length_m"] is not None
    seen = list(result["steps"])
    while True:
        more = call(guide["next_steps"])
        if more["done"]:
            break
        assert len(more["steps"]) <= 3
        seen += more["steps"]
    assert len(seen) == len(result["steps"]) + result["steps_remaining"]
    assert any("Leave" in step and "enter" in step for step in seen)


def test_campus_route_errors_are_tool_errors_with_a_next_move(tmp_path):
    holder, state, tools, _ = setup(tmp_path, drop_second_link=True)
    state.begin_turn()
    with pytest.raises(ToolError, match="connect_buildings"):
        tools["campus_route"](start=space_in(holder, CAMPUS_A), destination=space_in(holder, RESPLAN))
    with pytest.raises(ToolError, match="No building matches"):
        tools["campus_route"](start="x", destination="y", start_building="Atlantis")
    holder.maps[FACTORY].spaces[space_in(holder, FACTORY)]["name"] = holder.maps[CAMPUS_A].spaces[
        space_in(holder, CAMPUS_A)
    ]["name"]
    with pytest.raises(ToolError, match="Candidates"):
        tools["campus_route"](start=holder.maps[CAMPUS_A].spaces[space_in(holder, CAMPUS_A)]["name"], destination="z")


def test_building_names_resolve_a_shared_room_name(tmp_path):
    holder, state, tools, _ = setup(tmp_path)
    name = holder.maps[CAMPUS_A].spaces[space_in(holder, CAMPUS_A)]["name"]
    holder.maps[FACTORY].spaces[space_in(holder, FACTORY)]["name"] = name
    state.begin_turn()
    result = call(
        tools["campus_route"],
        start=name,
        start_building="Fertigung",
        destination=space_in(holder, RESPLAN),
    )
    assert result["buildings"][0] == "Fertigung Ost 27"


def _entrances(holder, building_id):
    return [item["id"] for item in entrances(holder.maps[building_id])]


def propose_connect(holder, tools, **extra):
    return call(
        tools["connect_buildings"],
        first_building="Fertigung",
        first_entrance=_entrances(holder, FACTORY)[1],
        second_building="Residence 439",
        second_entrance="",
        kind="bridge",
        **extra,
    )


def test_connect_buildings_card_then_clear_yes_applies_and_saves(tmp_path):
    holder, state, tools, _ = setup(tmp_path, drop_second_link=True)
    state.begin_turn()
    card = propose_connect(holder, tools, length_m=55)
    assert set(card) >= {"I understood", "length", "effect on the campus", "effect on routes", "status"}
    assert "Residence 439" in card["effect on the campus"][0] and "55" in card["length"]
    assert len(holder.campus.links) == 1  # nothing changed yet
    with pytest.raises(ToolError, match="Ask the person first"):
        tools["confirm_campus_change"](confirmed=True, user_reply="ja")  # same message
    state.begin_turn()
    result = call(tools["confirm_campus_change"], confirmed=True, user_reply="Ja, bitte")
    assert result["applied"] is True
    assert [link.id for link in holder.campus.links] == ["L1", "L2"]
    saved, findings = load_campus(tmp_path / "campus.json")
    assert saved.links[1].length_m == 55 and findings.ok
    state.begin_turn()
    route = call(tools["campus_route"], start=space_in(holder, CAMPUS_A), destination=space_in(holder, RESPLAN))
    assert route["buildings"][-1] == "Residence 439"


@pytest.mark.parametrize("reply", ["whatever", "ja ja", "yes but make it shorter", "mach einfach", "hmm"])
def test_vague_yes_is_refused_and_the_card_is_gone(tmp_path, reply):
    holder, state, tools, _ = setup(tmp_path, drop_second_link=True)
    state.begin_turn()
    propose_connect(holder, tools, length_m=55)
    state.begin_turn()
    with pytest.raises(ToolError, match="not a clear yes"):
        tools["confirm_campus_change"](confirmed=True, user_reply=reply)
    assert len(holder.campus.links) == 1
    with pytest.raises(ToolError, match="Nothing to confirm"):
        tools["confirm_campus_change"](confirmed=True, user_reply="yes")


def test_stale_card_is_refused(tmp_path):
    holder, state, tools, _ = setup(tmp_path, drop_second_link=True)
    state.begin_turn()
    propose_connect(holder, tools, length_m=55)
    state.begin_turn()
    state.begin_turn()  # the person talked about something else in between
    with pytest.raises(ToolError, match="out of date"):
        tools["confirm_campus_change"](confirmed=True, user_reply="yes")
    assert len(holder.campus.links) == 1


def test_decline_changes_nothing(tmp_path):
    holder, state, tools, _ = setup(tmp_path, drop_second_link=True)
    state.begin_turn()
    propose_connect(holder, tools, length_m=55)
    state.begin_turn()
    assert call(tools["confirm_campus_change"], confirmed=False, user_reply="nein")["applied"] is False
    assert len(holder.campus.links) == 1 and not (tmp_path / "campus.json").exists()


def test_campus_changed_since_the_card_is_refused(tmp_path):
    holder, state, tools, _ = setup(tmp_path, drop_second_link=True)
    state.begin_turn()
    propose_connect(holder, tools, length_m=55)
    holder.campus.links[0].closed = True
    state.begin_turn()
    with pytest.raises(ToolError, match="campus changed"):
        tools["confirm_campus_change"](confirmed=True, user_reply="yes")


def test_one_proposal_per_message(tmp_path):
    holder, state, tools, _ = setup(tmp_path, drop_second_link=True)
    state.begin_turn()
    propose_connect(holder, tools, length_m=55)
    with pytest.raises(ToolError, match="One proposal per message"):
        tools["close_link"](link_id="L1")


def test_missing_length_is_estimated_and_says_why(tmp_path):
    holder, state, tools, _ = setup(tmp_path, drop_second_link=True)
    state.begin_turn()
    card = propose_connect(holder, tools)
    assert "estimate" in card["length"] and "1.2" in card["length"]
    state.begin_turn()
    call(tools["confirm_campus_change"], confirmed=True, user_reply="yes")
    assert holder.campus.links[-1].length_estimated is True and holder.campus.links[-1].length_m > 0


def test_entrance_must_be_clear_and_buildings_must_differ(tmp_path):
    _holder, state, tools, _ = setup(tmp_path, drop_second_link=True)
    state.begin_turn()
    with pytest.raises(ToolError, match="Which entrance"):
        tools["connect_buildings"](
            first_building="Fertigung", first_entrance="", second_building="Residence 439", second_entrance=""
        )
    state.begin_turn()
    with pytest.raises(ToolError, match="two different buildings"):
        tools["connect_buildings"](
            first_building="Fertigung", first_entrance="x", second_building=FACTORY, second_entrance="y"
        )
    with pytest.raises(ToolError, match="No building matches"):
        tools["connect_buildings"](
            first_building="Atlantis", first_entrance="", second_building="x", second_entrance=""
        )
    with pytest.raises(ToolError, match="kind must be"):
        tools["connect_buildings"](
            first_building="Fertigung", first_entrance="", second_building="x", second_entrance="", kind="teleporter"
        )


def test_duplicate_link_is_refused(tmp_path):
    holder, state, tools, _ = setup(tmp_path)
    link = holder.campus.links[1]
    state.begin_turn()
    with pytest.raises(ToolError, match="already joined"):
        tools["connect_buildings"](
            first_building=link.from_building,
            first_entrance=link.from_entrance,
            second_building=link.to_building,
            second_entrance=link.to_entrance,
            length_m=10,
        )


def test_close_link_card_effect_and_guard(tmp_path):
    holder, state, tools, _ = setup(tmp_path)
    assert "Residence 439" in call(tools["link_what_changes"], link_id="L2")["effect"][0]
    state.begin_turn()
    card = call(tools["close_link"], link_id="Glass bridge", closed=True)
    assert "no longer connected" in card["effect on the campus"][0]
    assert holder.campus.links[1].closed is False
    with pytest.raises(ToolError, match="Ask the person first"):
        tools["confirm_campus_change"](confirmed=True, user_reply="yes")
    state.begin_turn()
    assert call(tools["confirm_campus_change"], confirmed=True, user_reply="yes")["applied"] is True
    assert holder.campus.links[1].closed is True
    state.begin_turn()
    with pytest.raises(ToolError, match="closed"):
        tools["campus_route"](start=space_in(holder, CAMPUS_A), destination=space_in(holder, RESPLAN))
    with pytest.raises(ToolError, match="already closed"):
        tools["close_link"](link_id="L2", closed=True)
    with pytest.raises(ToolError, match="No link matches"):
        tools["close_link"](link_id="L77")


def test_closing_a_link_ends_the_running_directions(tmp_path):
    holder, state, tools, guide = setup(tmp_path)
    state.begin_turn()
    call(tools["campus_route"], start=space_in(holder, CAMPUS_A), destination=space_in(holder, FACTORY))
    call(tools["close_link"], link_id="L1")
    state.begin_turn()
    call(tools["confirm_campus_change"], confirmed=True, user_reply="yes")
    with pytest.raises(ToolError):
        guide["next_steps"]()
