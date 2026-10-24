"""query_tools answers the plan questions no wired tool can (checked against the labelled dev kinds)."""

from pathlib import Path

import pytest

from building_agent.kinds.floor_area_total import KIND as AREA
from building_agent.kinds.largest_room import KIND as LARGEST
from building_agent.query_tools import (
    QUERY_TOOL_NAMES,
    door_effect,
    doors_by_width,
    floor_totals,
    make_query_tools,
    room_dimensions,
    rooms_table,
)
from starter_agent.building_map import MapError
from tests.conftest import labelled_questions, load_map

DEV = Path("data/dev/proc-factory-dev-003")
pytestmark = pytest.mark.skipif(not DEV.exists(), reason="dev data not fetched")


def test_rooms_table_agrees_with_the_kinds():
    bm = load_map(str(DEV))
    floor = next(f for f in bm.floors.values() if f["level"] == 1)
    table = rooms_table(bm, 1, "office")
    total = AREA.fn(bm, floor_id=floor["id"], room_type="office")
    assert table["total"] == total["count"]
    assert table["total_area_m2"] == pytest.approx(total["total_m2"], abs=0.02)
    biggest = LARGEST.fn(bm, floor_id=floor["id"], room_type="office")
    assert table["rooms"][0]["space_id"] == biggest["space_id"]
    ascending = rooms_table(bm, 1, "office", order="area_asc")["rooms"]
    assert ascending[0]["area_m2"] <= ascending[1]["area_m2"]
    assert rooms_table(bm, 1, "office", limit=3)["total"] == table["total"]


def test_floor_totals_cover_every_type():
    bm = load_map(str(DEV))
    totals = floor_totals(bm, 1)
    assert totals["total_area_m2"] == pytest.approx(sum(v["area_m2"] for v in totals["by_type"].values()), abs=0.05)
    assert totals["rooms_area_m2"] < totals["total_area_m2"]


def test_doors_by_width_splits_the_openings():
    bm = load_map(str(DEV))
    everything = doors_by_width(bm)
    narrow = doors_by_width(bm, narrower_than=1.0)
    wide = doors_by_width(bm, wider_than=1.0)
    assert 0 < narrow["count"] < everything["count"]
    assert narrow["count"] + wide["count"] <= everything["count"]  # a width of exactly 1.0 is in neither
    assert doors_by_width(bm, include_entrances=True)["count"] > everything["count"]


def test_room_dimensions_and_errors():
    bm = load_map(str(DEV))
    size = room_dimensions(bm, "Office 1.04")
    assert size["box_width_m"] * size["box_depth_m"] >= size["area_m2"] - 0.01
    with pytest.raises(MapError):
        rooms_table(bm, 42)
    with pytest.raises(MapError):
        room_dimensions(bm, "Ballroom 9.99")


def test_tools_return_json_and_report_errors():
    bm = load_map(str(DEV))
    tools = {tool.name: tool for tool in make_query_tools(bm)}
    assert set(tools) == QUERY_TOOL_NAMES
    assert '"total"' in tools["list_rooms"].func(floor_level=0, room_type="office")


WHAT_IF_CASES = labelled_questions("what_if_door")


@pytest.mark.parametrize("building_dir,question", WHAT_IF_CASES, ids=[case[1]["id"] for case in WHAT_IF_CASES])
def test_door_effect_counts_agree_with_labelled_what_if_door(building_dir, question):
    bm = load_map(building_dir)
    inputs = question["inputs"]
    level = bm.floors[inputs["floor_id"]]["level"]
    openings_before, closed_before = len(bm.openings), set(bm.closed)
    result = door_effect(bm, inputs["first"], inputs["second"], floor_level=level)
    assert result["rooms_with_shorter_walk_out"]["count"] == question["answer"]["value"]
    assert len(bm.openings) == openings_before and bm.closed == closed_before  # the live building is untouched


def test_door_effect_walk_before_after_and_no_mutation():
    bm = load_map(str(DEV))
    first = next(s for s in bm.spaces.values() if s["room_type"] == "production_zone")
    pair = next(
        (
            (s["id"], o)
            for o in bm.openings.values()
            for s in [bm.spaces[o["space_ids"][0]]]
            if "outside" not in o["space_ids"]
        ),
        None,
    )
    assert pair and first
    a, b = bm.openings[pair[1]["id"]]["space_ids"]
    last_before = bm.last_route
    result = door_effect(bm, a, b, from_space=a, to_space=b)
    walk = result["walk"]
    assert walk["after_m"] <= walk["before_m"]
    assert walk["saving_m"] == pytest.approx(walk["before_m"] - walk["after_m"], abs=0.01)
    assert bm.last_route is last_before
    with pytest.raises(MapError):
        door_effect(bm, a, b, from_space=a)
    other_floor = next(
        s for s in bm.spaces.values() if s["floor_id"] != bm.spaces[a]["floor_id"] and s["room_type"] == "office"
    )
    with pytest.raises(MapError):
        door_effect(bm, a, other_floor["id"])


def test_door_effect_saving_matches_a_real_door():
    from building_agent import routing
    from building_agent.impact import copy_map

    bm = load_map(str(DEV))
    office = [s for s in bm.spaces.values() if s["room_type"] == "office" and s["floor_id"].endswith("F1")]
    start = office[0]["id"]
    neighbour = next(
        i for i in kinds_neighbours(bm, start) if bm.spaces[i]["room_type"] not in ("corridor", "stairwell", "lift")
    )
    effect = door_effect(bm, start, neighbour, from_space=start, to_space=neighbour)
    real = copy_map(bm)
    from building_agent.kinds.what_if_door import shared_wall_midpoint

    real.add_door(start, neighbour, position=shared_wall_midpoint(bm, start, neighbour))
    assert effect["walk"]["after_m"] == pytest.approx(routing.route(real, start, neighbour).length_m, abs=0.01)


def kinds_neighbours(bm, start):
    from building_agent.kinds.shared_walls_count import shared_walls_count

    return shared_walls_count(bm, start)["space_ids"]


def test_query_tools_wired_but_hidden_in_benchmark_messages(monkeypatch):
    from building_agent import agent as agent_module
    from building_agent.agent import Agent
    from building_agent.query_tools import QUERY_RULES

    agent = Agent(load_map(str(DEV)), Path("agent_output") / "test", client=object())
    assert QUERY_TOOL_NAMES <= {tool.name for tool in agent.tools}
    assert QUERY_RULES in agent.system[0]["text"]
    base_prompt = agent.system[0]["text"]
    seen = {}

    def fake_ask(self, text):
        seen[text] = {tool.name for tool in self.tools}
        return "ok"

    monkeypatch.setattr(agent_module.StarterAgent, "ask", fake_ask)
    chat, bench = (
        "List all offices on floor 1.",
        "How many offices are on floor 1? Finish with a line 'Answer: <number>'.",
    )
    agent.ask(chat)
    agent.ask(bench)
    assert QUERY_TOOL_NAMES <= seen[chat]
    assert not (QUERY_TOOL_NAMES & seen[bench])  # the benchmark message sees exactly the tools main had
    assert seen[bench] == {tool.name for tool in agent.tools} - QUERY_TOOL_NAMES
    assert agent.system[0]["text"] == base_prompt
    assert QUERY_TOOL_NAMES <= {tool.name for tool in agent.tools}  # restored after the benchmark message
