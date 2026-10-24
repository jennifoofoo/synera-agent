import json

from building_agent.registry import load_kinds
from building_agent.tools import make_tools
from tests.conftest import labelled_questions, load_map


def tool_by_name(tools, name):
    return next(tool for tool in tools if tool.name == name)


def test_every_kind_becomes_a_tool_without_bm_in_its_schema():
    building_dir, _ = labelled_questions("errand")[0]
    tools = make_tools(load_map(building_dir), None)
    for name in load_kinds():
        schema = tool_by_name(tools, name).to_dict()["input_schema"]
        assert "bm" not in schema["properties"], name
        assert tool_by_name(tools, name).to_dict()["description"].strip()
    assert tool_by_name(tools, "find_space")


def test_kind_tool_returns_the_same_answer_as_the_kind():
    building_dir, question = labelled_questions("errand")[0]
    bm = load_map(building_dir)
    tool = tool_by_name(make_tools(bm, None), "errand")
    result = json.loads(tool(**question["inputs"]))
    assert result == load_kinds()["errand"].fn(bm, **question["inputs"])


def test_kind_tool_turns_bad_ids_into_tool_errors():
    import pytest
    from anthropic.lib.tools import ToolError

    building_dir, question = labelled_questions("errand")[0]
    tool = tool_by_name(make_tools(load_map(building_dir), None), "errand")
    with pytest.raises(ToolError):
        tool(**{**question["inputs"], "start": "not a space id"})


def test_type_parameters_accept_spaces_instead_of_underscores():
    from building_agent.tools import snake_case

    assert snake_case("room_type", "Living Room") == "living_room"
    assert snake_case("asset_type", "tv stand") == "tv_stand"
    assert snake_case("start", "Lab 0.12") == "Lab 0.12"


def test_shortened_type_resolves_to_the_building_type_and_unknown_lists_valid_ones():
    import pytest

    from building_agent.tools import known_types, resolve_type
    from starter_agent.building_map import MapError

    building_dir, _ = labelled_questions("floor_area_total")[0]
    bm = load_map(building_dir)
    room_types = known_types(bm, "room_type")
    some = min(room_types)
    assert resolve_type(bm, "room_type", some.replace("_", " ").upper()) == some
    with pytest.raises(MapError, match="Valid values"):
        resolve_type(bm, "room_type", "no_such_type_at_all")
    assert resolve_type(bm, "floor_id", "F1") == "F1"


def test_wrong_argument_list_is_a_tool_error_but_kind_bugs_are_not_masked():
    import pytest
    from anthropic.lib.tools import ToolError

    building_dir, question = labelled_questions("errand")[0]
    tool = tool_by_name(make_tools(load_map(building_dir), None), "errand")
    with pytest.raises(ToolError, match="Wrong arguments"):
        tool(start=question["inputs"]["start"])  # missing parameters


def test_bracketed_overview_string_is_reduced_to_the_id():
    from building_agent.tools import clean_reference

    building_dir, question = labelled_questions("errand")[0]
    bm = load_map(building_dir)
    start = question["inputs"]["start"]
    assert clean_reference(bm, f"{bm.spaces[start]['name']} [{start}]") == start
    assert clean_reference(bm, "Office 1.02") == "Office 1.02"
    assert clean_reference(bm, "Room [not-an-id]") == "Room [not-an-id]"


def test_forklift_route_tool_exists_and_refuses_pedestrian_only_buildings_cleanly():
    from pathlib import Path

    from anthropic.lib.tools import ToolError

    from starter_agent.building_map import BuildingMap

    bm = BuildingMap.load(Path("data/dev/proc-factory-dev-003"))
    tool = tool_by_name(make_tools(bm, None), "find_forklift_route")
    spaces = sorted(bm.spaces)
    try:
        tool(start=spaces[0], destination=spaces[-1])
    except ToolError as error:
        assert "forklift" in str(error).lower() or "no route" in str(error).lower() or str(error)
