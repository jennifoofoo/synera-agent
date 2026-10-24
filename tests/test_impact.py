import copy
import json
import time
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError

from building_agent.impact import analyse, make_impact_tools
from building_agent.kinds.step_free_reachable_count import step_free_reachable_count
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError
from tests.conftest import DATA, labelled_questions, load_map

CASES = labelled_questions("step_free_reachable_count")
HUGE = DATA / "dev" / "osm-way27917482"


def square(x: float, y: float = 0.0) -> list[list[float]]:
    return [[x, y], [x + 4, y], [x + 4, y + 4], [x, y + 4]]


def space(space_id: str, floor: str, kind: str, x: float, name: str | None = None) -> dict:
    return {
        "id": space_id,
        "floor_id": floor,
        "type": kind,
        "room_type": "generic_room" if kind == "room" else kind,
        "name": name or space_id,
        "ref": None,
        "polygon": square(x),
    }


def door(opening_id: str, first: str, second: str, x: float, step_free: bool = True) -> dict:
    return {
        "id": opening_id,
        "floor_id": "f0",
        "space_ids": [first, second],
        "kind": "door",
        "position": [x, 2.0],
        "width_m": 1.0,
        "step_free": step_free,
    }


def small_building(with_entrance: bool = True) -> dict:
    """Two floors: entrance hall, a lift and a staircase to a room upstairs."""
    spaces = [
        space("hall", "f0", "room", 0, "Hall"),
        space("lift0", "f0", "lift", 4),
        space("stair0", "f0", "stair", 8),
        space("lift1", "f1", "lift", 4),
        space("stair1", "f1", "stair", 8),
        space("up", "f1", "room", 12, "Office 1.01"),
        space("up2", "f1", "room", 16, "Office 1.02"),
    ]
    openings = [
        door("d-lift0", "hall", "lift0", 6),
        door("d-stair0", "hall", "stair0", 12),
        door("d-lift1", "lift1", "up", 20),
        door("d-stair1", "stair1", "up", 22),
        door("d-up2", "up", "up2", 28),
    ]
    for opening in openings[2:]:
        opening["floor_id"] = "f1"
    if with_entrance:
        openings.append(door("d-main", OUTSIDE, "hall", 0))
    return {
        "building": {"id": "small", "name": "Small", "source": "test"},
        "floors": [
            {"id": "f0", "level": 0, "name": "Ground floor"},
            {"id": "f1", "level": 1, "name": "1st floor"},
        ],
        "spaces": spaces,
        "assets": [],
        "vertical_connectors": [
            {
                "id": "L1",
                "kind": "lift",
                "name": "Lift 1",
                "floor_ids": ["f0", "f1"],
                "space_ids": ["lift0", "lift1"],
                "step_free": True,
            },
            {
                "id": "S1",
                "kind": "stairs",
                "name": "Staircase 1",
                "floor_ids": ["f0", "f1"],
                "space_ids": ["stair0", "stair1"],
                "step_free": False,
            },
        ],
        "openings": openings,
    }


def small_map(with_entrance: bool = True) -> BuildingMap:
    return BuildingMap(small_building(with_entrance))


def snapshot(bm: BuildingMap) -> tuple:
    return (
        set(bm.closed),
        json.dumps(bm.openings, sort_keys=True),
        json.dumps(bm.data["openings"], sort_keys=True),
        bm.last_route,
    )


@pytest.mark.parametrize("building_dir,question", CASES, ids=[question["id"] for _, question in CASES])
def test_matches_step_free_reachable_count(building_dir, question):
    bm = load_map(building_dir)
    inputs = question["inputs"]
    report = analyse(bm, closed_add=[inputs["closed"]])
    expected = step_free_reachable_count(bm, **inputs)["count"]
    assert report.step_free_rooms_by_floor.get(inputs["floor_id"], {"after": 0})["after"] == expected


def test_single_lift_cuts_upper_floor_off_for_wheelchairs_only():
    report = analyse(small_map(), closed_add=["Lift 1"])
    assert report.floors_cut_off_step_free == ["1st floor"]
    assert report.floors_cut_off == []
    assert report.lost_route == []
    assert sorted(report.lost_step_free) == ["up", "up2"]
    assert report.longer_count == 0
    first = report.sentences()[0]
    assert first.startswith("Closing Lift 1 cuts 1st floor off for wheelchair users")
    assert "2 rooms can no longer be reached step-free" in first


def test_closing_the_stairs_changes_nothing_for_step_free_and_the_walk_stays_short():
    report = analyse(small_map(), closed_add=["Staircase 1"])
    assert report.floors_cut_off_step_free == []
    assert report.lost_step_free == []
    assert report.lost_route == []


def test_closing_both_connectors_cuts_the_floor_off_completely():
    report = analyse(small_map(), closed_add=["Lift 1", "Staircase 1"])
    assert report.floors_cut_off == ["1st floor"]
    assert sorted(report.lost_route) == ["up", "up2"]
    assert len(report.sentences()) <= 5


def test_irrelevant_closure_changes_nothing():
    bm = small_map()
    report = analyse(bm, closed_add=["up2"])  # a dead-end room: nobody else needs to pass through it
    assert report.lost_route == [] and report.floors_cut_off == []
    assert report.sentences() == ["Closing Office 1.02 changes nothing for any room.", "No rooms are affected."]


def test_longer_walk_is_reported_with_the_detour():
    building_dir, question = CASES[0]  # a building where the lift is the quickest way for many rooms
    report = analyse(load_map(building_dir), closed_add=[question["inputs"]["closed"]])
    assert report.longer_count > 0
    assert report.longer_worst[0].delta_m > 1
    assert report.longer_worst[0].delta_m >= report.longer_worst[-1].delta_m
    assert "get a longer walk to the nearest entrance" in " ".join(report.sentences())


def test_reopen_is_the_inverse():
    bm = small_map()
    bm.closed.add("L1")
    report = analyse(bm, closed_remove=["Lift 1"])
    assert report.reopening
    assert sorted(report.gained_step_free) == ["up", "up2"]
    assert report.floors_regained_step_free == ["1st floor"]
    assert "can be reached step-free again" in report.sentences()[0]
    closing = analyse(small_map(), closed_add=["Lift 1"])
    assert sorted(closing.lost_step_free) == sorted(report.gained_step_free)


def test_reopen_on_real_building_mirrors_close():
    building_dir, question = CASES[0]
    bm = load_map(building_dir)
    closing = analyse(bm, closed_add=[question["inputs"]["closed"]])
    reopened = copy.copy(bm)
    reopened.closed = {bm.find_element(question["inputs"]["closed"])}
    opening = analyse(reopened, closed_remove=[question["inputs"]["closed"]])
    assert sorted(opening.gained_step_free) == sorted(closing.lost_step_free + closing.lost_route)
    assert opening.longer_count == 0
    assert opening.shorter_count == closing.longer_count


def test_never_mutates_the_real_map():
    bm = small_map()
    bm.closed.add("d-up2")
    bm.route("hall", "up")
    before = snapshot(bm)
    analyse(bm, closed_add=["Lift 1"])
    analyse(bm, closed_remove=["d-up2"])
    analyse(bm, doors_add=[("hall", "lift0")])
    assert snapshot(bm) == before


def test_what_changes_tool_returns_json_with_sentences():
    (tool,) = make_impact_tools(small_map())
    assert tool.name == "what_changes"
    result = json.loads(tool(element="Lift 1"))
    assert result["floors_cut_off_step_free"] == ["1st floor"]
    assert 2 <= len(result["sentences"]) <= 5


def test_what_changes_tool_errors_are_clear():
    bm = small_map()
    bm.closed.add("L1")
    (tool,) = make_impact_tools(bm)
    with pytest.raises(ToolError, match="No place matches"):
        tool(element="Lift 9")
    with pytest.raises(ToolError, match="already closed"):
        tool(element="Lift 1")
    with pytest.raises(ToolError, match="not closed"):
        tool(element="Staircase 1", action="reopen")
    with pytest.raises(ToolError, match="action must be"):
        tool(element="Lift 1", action="explode")


def test_unknown_and_double_closure_raise_map_errors():
    bm = small_map()
    with pytest.raises(MapError):
        analyse(bm, closed_add=["nonexistent thing"])
    bm.closed.add("S1")
    with pytest.raises(MapError, match="already closed"):
        analyse(bm, closed_add=["S1"])


def test_closing_every_connector_and_no_entrance_complete():
    bm = small_map()
    report = analyse(bm, closed_add=list(bm.connectors))
    assert report.floors_cut_off == ["1st floor"]
    blind = small_map(with_entrance=False)
    report = analyse(blind, closed_add=["Lift 1"])
    assert report.lost_route == [] and report.sentences()[-1] == "No rooms are affected."


def test_huge_building_is_fast():
    if not HUGE.exists():
        pytest.skip("huge building not in data")
    bm = BuildingMap.load(HUGE)
    started = time.perf_counter()
    for connector in sorted(bm.connectors)[:2]:
        analyse(bm, closed_add=[connector])
    assert time.perf_counter() - started < 15


def all_buildings() -> list[Path]:
    return sorted(path.parent for split in ("train", "dev", "test") for path in (DATA / split).glob("*/building.json"))


def sampled(connectors: list[str]) -> list[str]:
    if len(connectors) <= 3:
        return connectors
    return [connectors[0], connectors[len(connectors) // 2], connectors[-1]]


def test_sweep_over_all_buildings():
    buildings = all_buildings()
    assert len(buildings) >= 280
    started = time.perf_counter()
    for building_dir in buildings:
        bm = BuildingMap.load(building_dir)
        for connector in sampled(sorted(bm.connectors)):
            first = analyse(bm, closed_add=[connector])
            second = analyse(bm, closed_add=[connector])
            assert first.to_dict() == second.to_dict(), building_dir
            assert 2 <= len(first.sentences()) <= 5
            for number in (first.longer_count, first.shorter_count, first.longer_median_m, first.shorter_median_m):
                assert number >= 0
            assert all(change.delta_m > 0 for change in first.longer_worst)
            assert set(first.lost_route).isdisjoint(first.lost_step_free)
    assert time.perf_counter() - started < 40
