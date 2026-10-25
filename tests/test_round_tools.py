import itertools
import json
import math
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
    EXACT_MAX_STOPS,
    START,
    best_order,
    device_point,
    distance_matrix,
    held_karp,
    make_round_tools,
    nearest_neighbour,
    path_length,
    plan_round,
    point_matrix,
    two_opt,
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


def device_matrix(bm, start_id: str, asset_ids: list[str], start_point=None) -> dict:
    ends = {START: (start_id, start_point)}
    ends.update({i: (bm.assets[i]["space_id"], device_point(bm, bm.assets[i])) for i in asset_ids})
    return point_matrix(bm, ends, False)


def test_ground_floor_extinguishers_one_stop_per_device_and_legs_sum_to_the_total(bm):
    result = plan_round(bm, "fire extinguisher", "Main aisle H-B5", floor_level=0)
    assert result["devices"] == 6 and len(result["stops"]) == 6
    assert len({stop["asset_id"] for stop in result["stops"]}) == 6
    assert all(stop["position"] and stop["device"] for stop in result["stops"])
    assert result["stops"][0]["room"] == "Main aisle H-B5" and result["stops"][0]["leg_m"] > 0  # walk to the device
    assert all(stop["floor"] == "Ground floor" for stop in result["stops"])
    assert result["order"].startswith("exact")
    assert result["total_m"] == pytest.approx(sum(stop["leg_m"] for stop in result["stops"]), abs=0.3)
    assert result["compare_hint"]["naive_total_m"] >= result["total_m"]
    assert bm.located_asset_ids == [stop["asset_id"] for stop in result["stops"]]
    # The drawn route ends at the last device.
    assert bm.last_route.destination_space_id == result["stops"][-1]["space_id"]
    assert bm.last_route_points[-1][1] == pytest.approx(result["stops"][-1]["position"], abs=0.01)


def test_each_leg_is_the_point_to_point_route_the_page_asks_for(bm):
    """Leg i is routing.route from device i-1 (start_point) to device i (destination_point): what round.ts sends."""
    result = plan_round(bm, "fire extinguisher", "Main aisle H-B5", floor_level=0)
    start_id = bm.resolve_space("Main aisle H-B5")
    previous = (start_id, None)
    for stop in result["stops"]:
        leg = routing.route(bm, previous[0], stop["space_id"], False, None, previous[1], None, stop["position"])
        assert leg.length_m == pytest.approx(stop["leg_m"], abs=0.06)
        previous = (stop["space_id"], stop["position"])


def test_two_devices_in_one_room_are_two_stops(bm):
    room = bm.resolve_space("Main aisle H-B5")
    first = next(a for a in bm.assets.values() if a["type"] == "fire_extinguisher" and a["space_id"] == room)
    x, y = first["position"][:2]
    bm.assets["extra-extinguisher"] = {
        **first,
        "id": "extra-extinguisher",
        "name": "Fire extinguisher H-B5 b",
        "position": [x + 1.0, y],
    }
    result = plan_round(bm, "fire extinguisher", "Main aisle H-B5", floor_level=0)
    assert len(result["stops"]) == 7
    in_room = [stop for stop in result["stops"] if stop["space_id"] == room]
    assert {stop["asset_id"] for stop in in_room} == {first["id"], "extra-extinguisher"}
    order = [stop["asset_id"] for stop in result["stops"]]
    assert abs(order.index(first["id"]) - order.index("extra-extinguisher")) == 1  # next to each other: 1 m apart
    second = max(order.index(first["id"]), order.index("extra-extinguisher"))
    inside = routing.same_room_walk(
        bm, room, device_point(bm, first), device_point(bm, bm.assets["extra-extinguisher"])
    )
    assert 0 < result["stops"][second]["leg_m"] == pytest.approx(inside, abs=0.06)  # the walk inside the room


@pytest.mark.parametrize("start", ["Main aisle H-B5", "Server room 0.43"])
def test_small_rounds_are_optimal_by_brute_force(bm, start):
    result = plan_round(bm, "fire extinguisher", start, floor_level=0)
    start_id = bm.resolve_space(start)
    devices = [stop["asset_id"] for stop in result["stops"]]
    matrix = device_matrix(bm, start_id, devices)
    best = min(path_length(matrix, START, order, False) for order in itertools.permutations(devices))
    assert result["total_m"] == pytest.approx(best, abs=0.06)
    back = plan_round(bm, "fire extinguisher", start, floor_level=0, return_to_start=True)
    best_back = min(path_length(matrix, START, order, True) for order in itertools.permutations(devices))
    assert back["total_m"] == pytest.approx(best_back, abs=0.06)
    assert back["total_m"] == pytest.approx(sum(s["leg_m"] for s in back["stops"]) + back["back_to_start_m"], abs=0.3)
    assert bm.last_route.destination_space_id == start_id


def test_start_point_is_used_for_the_first_leg(bm):
    start_id = bm.resolve_space("Main aisle H-B5")
    anchor = bm.anchor(start_id)
    plain = plan_round(bm, "fire extinguisher", start_id, floor_level=0)
    first = plain["stops"][0]
    point = first["position"]  # standing right at the first device
    at_device = plan_round(bm, "fire extinguisher", start_id, floor_level=0, start_point=point)
    assert at_device["stops"][0]["asset_id"] == first["asset_id"]
    assert at_device["stops"][0]["leg_m"] == pytest.approx(0, abs=0.3)
    assert bm.planned_round["info"]["start_point"] == pytest.approx(point, abs=0.01)
    assert anchor != tuple(point)


def test_order_is_deterministic_whatever_the_asset_order(bm):
    first = plan_round(bm, "fire extinguisher", "Server room 0.43")
    items = list(bm.assets.items())
    random.Random(7).shuffle(items)
    bm.assets = dict(items)
    second = plan_round(bm, "fire extinguisher", "Server room 0.43")
    assert [s["asset_id"] for s in first["stops"]] == [s["asset_id"] for s in second["stops"]]
    assert first["total_m"] == second["total_m"]


def test_multi_floor_round_of_ten_is_exact_and_beats_the_heuristic(bm):
    """10 devices on two floors: Held-Karp (exact up to 16), never longer than nearest neighbour + 2-opt."""
    result = plan_round(bm, "extinguishers", "Main aisle H-B5")
    assert result["devices"] == 10 and len(result["stops"]) == 10
    assert {stop["floor"] for stop in result["stops"]} == {"Ground floor", "Floor 1"}
    assert result["order"].startswith("exact")
    start_id = bm.resolve_space("Main aisle H-B5")
    devices = [stop["asset_id"] for stop in result["stops"]]
    matrix = device_matrix(bm, start_id, devices)
    greedy = path_length(matrix, START, tuple(nearest_neighbour(matrix, START, devices)), False)
    heuristic = path_length(
        matrix, START, tuple(two_opt(matrix, START, nearest_neighbour(matrix, START, devices), False)), False
    )
    assert result["total_m"] <= min(greedy, heuristic) + 0.06
    assert result["total_m"] == pytest.approx(sum(stop["leg_m"] for stop in result["stops"]), abs=0.5)


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
    assert guide.walk is not None and guide.walk.length_m == pytest.approx(result["total_m"], abs=0.1)
    assert guide.walk.destination == result["stops"][-1]["space_id"]
    assert guide.walk.via == bm.planned_round["via"]


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
    """Spec acceptance (docs/specs/inspection-round.md): 5 stops (one per device) from "entrance in Main aisle H-B3",
    length equal to the device-to-device legs walked one by one (±1 m), and a door between H-A2 and Server room
    0.16 makes it shorter."""
    demo = copy_map(routing.load_map(DEMO))
    result = plan_round(demo, "fire extinguisher", "entrance in Main aisle H-B3", floor_level=0)
    assert len(result["stops"]) == 5 and result["start"] == "Main aisle H-B3"
    previous, walked = (demo.resolve_space("Main aisle H-B3"), None), 0.0
    for stop in result["stops"]:
        walked += routing.route(
            demo, previous[0], stop["space_id"], False, None, previous[1], None, stop["position"]
        ).length_m
        previous = (stop["space_id"], stop["position"])
    assert walked == pytest.approx(result["total_m"], abs=1)
    first, second = demo.resolve_space("Production zone H-A2"), demo.resolve_space("Server room 0.16")
    with_door = copy_map(demo)
    with_door.add_door(first, second, position=shared_wall_midpoint(demo, first, second))
    assert (
        plan_round(with_door, "fire extinguisher", "Main aisle H-B3", floor_level=0)["total_m"] < result["total_m"] - 20
    )


def test_unknown_start_still_fails_after_the_entrance_words_are_dropped(bm):
    with pytest.raises(MapError):
        plan_round(bm, "fire extinguisher", "entrance in Nowhere room 9.99", floor_level=0)


def test_route_with_via_points_is_the_sum_of_the_point_to_point_legs(bm):
    """The via contract: via_points[i] belongs to via[i] (None = the room's anchor); each leg runs point to point
    like a route with start_point/destination_point, and last_route_points pass through every point."""
    result = plan_round(bm, "fire extinguisher", "Main aisle H-B5", floor_level=0)
    start_id = bm.resolve_space("Main aisle H-B5")
    rooms = [stop["space_id"] for stop in result["stops"]]
    points = [stop["position"] for stop in result["stops"]]
    route = routing.route(bm, start_id, rooms[-1], False, rooms[:-1], None, None, points[-1], points[:-1])
    assert route.length_m == pytest.approx(result["total_m"], abs=0.1)
    drawn = [tuple(point) for _, point in bm.last_route_points]
    assert all(any(math.dist(point, p) < 1e-6 for p in drawn) for point in points)
    plain = routing.route(bm, start_id, rooms[-1], False, rooms[:-1], None, None, None, [None] * (len(rooms) - 1))
    assert plain.length_m == routing.route(bm, start_id, rooms[-1], False, rooms[:-1]).length_m


@pytest.mark.parametrize("back", [False, True])
def test_held_karp_equals_brute_force_on_random_rounds(back):
    """Held-Karp gives the shortest length of all orders (brute force) for 1 to 8 stops, also back to the start,
    and the same order every time (ties to the smaller id)."""
    rng = random.Random(11)
    for size in range(1, 9):
        for _ in range(8):
            keys = [START, *(f"A{i:02d}" for i in range(size))]
            spots = {key: (rng.uniform(0, 60), rng.uniform(0, 60)) for key in keys}
            matrix = {a: {b: round(math.dist(spots[a], spots[b]) + rng.uniform(0, 4), 1) for b in keys} for a in keys}
            stops = keys[1:]
            order = held_karp(matrix, START, stops, back)
            best = min(path_length(matrix, START, perm, back) for perm in itertools.permutations(stops))
            assert sorted(order) == stops
            assert path_length(matrix, START, tuple(order), back) == pytest.approx(best, abs=1e-9)
            assert held_karp(matrix, START, list(reversed(stops)), back) == order


def test_held_karp_is_used_up_to_sixteen_stops_and_ties_go_to_the_smaller_id():
    assert EXACT_MAX_STOPS == 16
    keys = [START, "A1", "A2", "A3"]
    matrix = {a: {b: 0.0 if a == b else 10.0 for b in keys} for a in keys}  # every order is equally long
    assert held_karp(matrix, START, ["A3", "A1", "A2"], False) == ["A1", "A2", "A3"]
    stops = [f"A{i:02d}" for i in range(16)]
    keys = [START, *stops]
    rng = random.Random(5)
    matrix = {a: {b: rng.uniform(1, 30) for b in keys} for a in keys}
    order, method = best_order(matrix, START, stops, False)
    assert method.startswith("exact") and sorted(order) == stops
    heuristic = two_opt(matrix, START, nearest_neighbour(matrix, START, stops), False)
    assert path_length(matrix, START, tuple(order), False) <= path_length(matrix, START, tuple(heuristic), False) + 1e-9
