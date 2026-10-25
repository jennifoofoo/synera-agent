import itertools
import json
import random
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError

from building_agent import routing
from building_agent.guide_tools import GuideState
from building_agent.impact import copy_map
from building_agent.kinds.what_if_door import shared_wall_midpoint
from building_agent.position import make_position
from building_agent.round_tools import (
    best_order,
    distance_matrix,
    make_round_tools,
    nearest_neighbour,
    path_length,
    plan_round,
)
from starter_agent.building_map import MapError

FACTORY = Path("data/dev/proc-factory-dev-003")


@pytest.fixture
def bm():
    return copy_map(routing.load_map(FACTORY))


def tool(bm, guide=None):
    guide = guide or GuideState()
    return make_round_tools(bm, guide)[0], guide


def call(round_tool, **kwargs) -> dict:
    return json.loads(round_tool.call(kwargs))


def stop_rooms(result: dict) -> list[str]:
    return [stop["room"] for stop in result["stops"]]


def test_ground_floor_extinguishers_one_stop_per_room_and_total_matches_the_drawn_route(bm):
    result = plan_round(bm, "fire extinguisher", "Main aisle H-B5", floor_level=0)
    assert result["devices"] == 6 and len(result["stops"]) == 6
    assert result["stops"][0]["room"] == "Main aisle H-B5" and result["stops"][0]["leg_m"] == 0
    assert all(stop["floor"] == "Ground floor" for stop in result["stops"])
    assert result["order"].startswith("exact")
    assert result["total_m"] == pytest.approx(sum(stop["leg_m"] for stop in result["stops"]), abs=0.3)
    assert bm.last_route.length_m == pytest.approx(result["total_m"], abs=0.06)
    assert result["compare_hint"]["naive_total_m"] >= result["total_m"]
    assert len(bm.located_asset_ids) == 6


@pytest.mark.parametrize("start", ["Main aisle H-B5", "Server room 0.43"])
def test_small_rounds_are_optimal_by_brute_force(bm, start):
    result = plan_round(bm, "fire extinguisher", start, floor_level=0)
    start_id = bm.resolve_space(start)
    rooms = [stop["space_id"] for stop in result["stops"]]
    matrix = distance_matrix(bm, sorted({start_id, *rooms}), False)
    best = min(path_length(matrix, start_id, order, False) for order in itertools.permutations(rooms))
    assert result["total_m"] == pytest.approx(best, abs=0.06)
    back = plan_round(bm, "fire extinguisher", start, floor_level=0, return_to_start=True)
    best_back = min(path_length(matrix, start_id, order, True) for order in itertools.permutations(rooms))
    assert back["total_m"] == pytest.approx(best_back, abs=0.06)
    assert bm.last_route.destination_space_id == start_id


def test_order_is_deterministic_whatever_the_asset_order(bm):
    first = plan_round(bm, "fire extinguisher", "Server room 0.43")
    items = list(bm.assets.items())
    random.Random(7).shuffle(items)
    bm.assets = dict(items)
    second = plan_round(bm, "fire extinguisher", "Server room 0.43")
    assert stop_rooms(first) == stop_rooms(second) and first["total_m"] == second["total_m"]


def test_multi_floor_round_uses_the_heuristic_and_beats_nearest_neighbour(bm):
    result = plan_round(bm, "extinguishers", "Main aisle H-B5")
    assert result["devices"] == 10
    assert {stop["floor"] for stop in result["stops"]} == {"Ground floor", "Floor 1"}
    assert result["order"] == "nearest neighbour + 2-opt"
    start_id = bm.resolve_space("Main aisle H-B5")
    rooms = [stop["space_id"] for stop in result["stops"]]
    matrix = distance_matrix(bm, sorted({start_id, *rooms}), False)
    greedy = path_length(matrix, start_id, tuple(nearest_neighbour(matrix, start_id, rooms)), False)
    assert result["total_m"] <= greedy + 0.06
    assert bm.last_route.length_m == pytest.approx(result["total_m"], abs=0.06)


def test_heuristic_matches_brute_force_on_random_small_sets(bm):
    """Up to 8 stops the tool is exact; 2-opt on its own is checked here against brute force for the record."""
    rooms = sorted({asset["space_id"] for asset in bm.assets.values()})
    rng = random.Random(3)
    for _ in range(5):
        chosen = rng.sample(rooms, 6)
        start = chosen.pop()
        matrix = distance_matrix(bm, sorted({start, *chosen}), False)
        order, method = best_order(matrix, start, chosen, False)
        best = min(path_length(matrix, start, perm, False) for perm in itertools.permutations(chosen))
        assert method.startswith("exact") and path_length(matrix, start, tuple(order), False) == pytest.approx(best)


@pytest.mark.parametrize("words", ["Feuerlöscher", "fire extinguisher", "fire_extinguisher"])
def test_area_filter_hall_and_ref_prefix(bm, words):
    hall = plan_round(bm, words, "Main aisle H-B5", area="Hall A")
    assert stop_rooms(hall) == ["Production zone H-A4", "Production zone H-A1"]
    assert stop_rooms(plan_round(bm, words, "Main aisle H-B5", area="H-A")) == stop_rooms(hall)
    servers = plan_round(bm, words, "Main aisle H-B5", floor_level=0, area="server rooms")
    assert sorted(stop_rooms(servers)) == ["Server room 0.29", "Server room 0.43", "Server room 0.45"]
    with pytest.raises(MapError, match="No matching device"):
        plan_round(bm, words, "Main aisle H-B5", area="Kitchen")


def test_step_free_round_is_never_shorter(bm):
    normal = plan_round(bm, "fire extinguisher", "Main aisle H-B5", return_to_start=True)
    step_free = plan_round(bm, "fire extinguisher", "Main aisle H-B5", return_to_start=True, step_free=True)
    assert step_free["step_free"] and bm.last_route.step_free
    assert step_free["total_m"] >= normal["total_m"] - 0.06


def test_new_door_shortens_the_round(bm):
    before = plan_round(bm, "fire extinguisher", "Server room 0.43", floor_level=0)["total_m"]
    first, second = bm.resolve_space("Production zone H-A4"), bm.resolve_space("Main aisle H-B5")
    after_map = copy_map(bm)
    after_map.add_door(first, second, position=shared_wall_midpoint(bm, first, second))
    after = plan_round(after_map, "fire extinguisher", "Server room 0.43", floor_level=0)["total_m"]
    assert after < before


def test_tool_needs_a_start_without_position_and_lists_entrances(bm):
    round_tool, guide = tool(bm)
    result = call(round_tool, what="fire extinguisher", floor_level=0)
    assert result["needs_start"] and result["entrances"]
    assert all(entry["space_id"] in bm.spaces for entry in result["entrances"])
    assert guide.walk is None


def test_tool_starts_here_and_remembers_the_round_for_guiding(bm):
    guide = GuideState()
    guide.position = make_position(bm, bm.resolve_space("Main aisle H-B5"))
    round_tool, _ = tool(bm, guide)
    result = call(round_tool, what="Feuerlöscher", start="here", floor_level=0)
    assert "Main aisle H-B5" in result["start_assumed"]
    assert guide.walk is not None and guide.walk.length_m == pytest.approx(result["total_m"], abs=0.06)
    assert guide.walk.destination == result["stops"][-1]["space_id"]
    assert guide.walk.via == [stop["space_id"] for stop in result["stops"][:-1]]


def test_tool_reports_unknown_device_as_tool_error(bm):
    round_tool, _ = tool(bm)
    with pytest.raises(ToolError):
        round_tool.call({"what": "teleporter", "start": "Main aisle H-B5"})


def test_tool_in_a_benchmark_message_never_asks_for_a_start(bm):
    round_tool, guide = tool(bm)
    guide.last_user_text = "Shortest round over all fire extinguishers. Answer: <metres>"
    with pytest.raises(ToolError, match="start is given in the question"):
        round_tool.call({"what": "fire extinguisher"})


DEMO = Path("data/train/proc-factory-train-015")


@pytest.mark.skipif(not DEMO.exists(), reason="data/train is missing")
def test_demo_round_from_the_entrance_matches_the_spec():
    """Spec acceptance (docs/specs/inspection-round.md): 5 stops from "entrance in Main aisle H-B3", length equal to
    the route through the same stops (±1 m), and a door between H-A2 and Server room 0.16 makes it shorter."""
    demo = copy_map(routing.load_map(DEMO))
    result = plan_round(demo, "fire extinguisher", "entrance in Main aisle H-B3", floor_level=0)
    assert len(result["stops"]) == 5 and result["start"] == "Main aisle H-B3"
    via = [stop["space_id"] for stop in result["stops"]]
    same_order = routing.route(demo, demo.resolve_space("Main aisle H-B3"), via[-1], False, via[:-1])
    assert same_order.length_m == pytest.approx(result["total_m"], abs=1)
    first, second = demo.resolve_space("Production zone H-A2"), demo.resolve_space("Server room 0.16")
    with_door = copy_map(demo)
    with_door.add_door(first, second, position=shared_wall_midpoint(demo, first, second))
    assert (
        plan_round(with_door, "fire extinguisher", "Main aisle H-B3", floor_level=0)["total_m"] < result["total_m"] - 20
    )


def test_unknown_start_still_fails_after_the_entrance_words_are_dropped(bm):
    with pytest.raises(MapError):
        plan_round(bm, "fire extinguisher", "entrance in Nowhere room 9.99", floor_level=0)
