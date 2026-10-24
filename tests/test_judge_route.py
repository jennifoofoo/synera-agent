"""Tests for the jury-model router (building_agent/judge_route.py). No API calls.

Small synthetic buildings pin the rules (geodesics, stairs/lift costs, forklift, bays, closures, no route); the
data sweep checks every kit building routes without crashing and reports how often the space sequence differs from
the kit router on the labelled route questions (`pytest -s tests/test_judge_route.py -k report`)."""

import copy
import itertools
import json
import math
import time

import pytest

from building_agent.judge_route import (
    FORKLIFT_MIN_WIDTH_M,
    LIFT_WAIT_M,
    STAIRS_M_PER_M_CLIMBED,
    WALL_CLEARANCE_M,
    JudgeRouter,
    forklift_may_use,
    is_bay,
    is_forklift_aisle,
    judge_route,
    router_for,
    shrink,
)
from starter_agent.building_map import BuildingMap
from tests.conftest import DATA, load_map

# ---------- a small synthetic factory with two floors ----------
#
# Ground floor:                                        Floor 1:
#   S1 office (0..5, 0..5)                               T1 office (5..10, 0..10)
#   L  L-shaped corridor right of and above S1 (concave  T2 stairwell (10..13, 0..5), T3 lift (10..12, 5..10)
#      corner at (5, 5)), W stairwell (10..13, 0..5), K lift (10..12, 5..10)
#   A  main aisle (0..20, 10..14), bays B1 (0..10, 14..24) and B2 (10..20, 14..24), store R (20..24, 10..24)


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def space(sid, floor, kind, room_type, name, polygon):
    return {"id": sid, "floor_id": floor, "type": kind, "room_type": room_type, "name": name, "polygon": polygon}


def opening(oid, floor, a, b, position, width=0.9, kind="door", step_free=True):
    return {
        "id": oid,
        "floor_id": floor,
        "space_ids": [a, b],
        "kind": kind,
        "position": list(position),
        "width_m": width,
        "step_free": step_free,
    }


def synthetic_building() -> dict:
    l_shape = [[5, 0], [10, 0], [10, 10], [0, 10], [0, 5], [5, 5]]  # wraps S1's right and top: concave at (5, 5)
    return {
        "building": {"id": "syn", "name": "Synthetic", "source": "test"},
        "floors": [
            {"id": "F0", "level": 0, "name": "Ground floor", "elevation_m": 0.0, "height_m": 4.0},
            {"id": "F1", "level": 1, "name": "Floor 1", "elevation_m": 4.0, "height_m": 3.0},
        ],
        "spaces": [
            space("S1", "F0", "room", "office", "Office 0.1", rect(0, 0, 5, 5)),
            space("L", "F0", "corridor", "corridor", "Corridor 0.L", l_shape),
            space("W", "F0", "stair", "stairwell", "Stairs 0", rect(10, 0, 13, 5)),
            space("K", "F0", "lift", "lift", "Lift 0", rect(10, 5, 12, 10)),
            space("A", "F0", "corridor", "corridor", "Main aisle H1", rect(0, 10, 20, 14)),
            space("B1", "F0", "hall", "production_zone", "Production bay 1", rect(0, 14, 10, 24)),
            space("B2", "F0", "hall", "assembly_zone", "Assembly bay 2", rect(10, 14, 20, 24)),
            space("R", "F0", "room", "storage", "Store 0.9", rect(20, 10, 24, 24)),
            space("T1", "F1", "room", "office", "Office 1.1", rect(5, 0, 10, 10)),
            space("T2", "F1", "stair", "stairwell", "Stairs 1", rect(10, 0, 13, 5)),
            space("T3", "F1", "lift", "lift", "Lift 1", rect(10, 5, 12, 10)),
        ],
        "openings": [
            opening("D-S1-L", "F0", "S1", "L", (5, 4.5)),  # right wall of S1, just below the inner corner of L
            opening("D-L-W", "F0", "L", "W", (10, 2.5)),
            opening("D-L-K", "F0", "L", "K", (10, 7.5)),
            opening("D-L-A", "F0", "L", "A", (1, 10)),
            opening("O-A-B1", "F0", "A", "B1", (5, 14), width=4.0, kind="opening"),
            opening("O-A-B2", "F0", "A", "B2", (15, 14), width=4.0, kind="opening"),
            opening("O-B1-B2", "F0", "B1", "B2", (10, 19), width=4.0, kind="opening"),
            opening("D-B2-R", "F0", "B2", "R", (20, 19), width=1.6),
            opening("D-A-R", "F0", "A", "R", (20, 12), width=1.6),
            opening("E-A", "F0", "A", "outside", (0, 12), width=4.0, kind="entrance"),
            opening("D-T1-T2", "F1", "T1", "T2", (10, 2.5)),
            opening("D-T1-T3", "F1", "T1", "T3", (10, 7.5)),
        ],
        "vertical_connectors": [
            {
                "id": "V-stairs",
                "kind": "stairs",
                "name": "Stairs",
                "floor_ids": ["F0", "F1"],
                "space_ids": ["W", "T2"],
                "step_free": False,
            },
            {
                "id": "V-lift",
                "kind": "lift",
                "name": "Lift",
                "floor_ids": ["F0", "F1"],
                "space_ids": ["K", "T3"],
                "step_free": True,
            },
        ],
        "assets": [
            {
                "id": "A1",
                "name": "Press 1",
                "category": "machine",
                "type": "press",
                "space_id": "B1",
                "floor_id": "F0",
                "position": [3, 20],
            },
        ],
    }


@pytest.fixture
def syn() -> BuildingMap:
    return BuildingMap(synthetic_building())


def connected(bm: BuildingMap, a: str, b: str) -> bool:
    """Is there a real door/opening/stair/lift between two consecutive spaces of a route?"""
    for o in bm.openings.values():
        if set(o["space_ids"]) == {a, b}:
            return True
    for c in bm.connectors.values():
        stops = c["space_ids"]
        if a in stops and b in stops and abs(stops.index(a) - stops.index(b)) == 1:
            return True
    return False


def assert_valid_path(bm: BuildingMap, result: dict) -> None:
    assert result["ok"], result["reason"]
    path = result["space_path"]
    assert len(result["element_path"]) == len(path) - 1
    for a, b in itertools.pairwise(path):
        assert connected(bm, a, b), (a, b)


# ---------- rules on the synthetic building ----------


def test_walks_around_the_corner_of_a_concave_corridor(syn):
    # S1 -> L -> A: the inner corner of L at (5, 5) lies between the two doors; a straight line would cut S1.
    result = judge_route(syn, "S1", "A", endpoint="door")
    assert result["space_path"] == ["S1", "L", "A"]
    door_a, door_b = (5.0, 4.5), (1.0, 10.0)
    clearance = WALL_CLEARANCE_M
    corner = (5 + clearance, 5 + clearance)
    inside_a, inside_b = (5 + clearance, 4.5), (1.0, 10 - clearance)  # 15 cm off the wall, in front of each door
    around = clearance + math.dist(inside_a, corner) + math.dist(corner, inside_b) + clearance
    assert result["length_m"] > math.dist(door_a, door_b)
    assert result["length_m"] == pytest.approx(around, abs=0.01)


def test_centre_endpoint_adds_the_walk_inside_start_and_end(syn):
    by_door = judge_route(syn, "S1", "A", endpoint="door")["length_m"]
    by_centre = judge_route(syn, "S1", "A", endpoint="centre")["length_m"]
    assert by_centre > by_door + 10  # about 3 m to the door inside S1 plus about 9 m inside A


def test_stairs_cost_two_metres_per_metre_climbed(syn):
    # Floor 1 is 4 m up. Stairs: 8 m; lift: 15 + 4 = 19 m. From W to T2 directly (door endpoint) is only the climb.
    result = judge_route(syn, "W", "T2", endpoint="door")
    assert result["space_path"] == ["W", "T2"]
    assert result["element_path"] == ["V-stairs"]
    assert result["length_m"] == pytest.approx(STAIRS_M_PER_M_CLIMBED * 4.0)


def test_lift_costs_wait_plus_height(syn):
    # Without step_free the stairs (8 m plus a short walk) beat the lift (19 m); with it only the lift remains.
    result = judge_route(syn, "K", "T3", step_free=True, endpoint="door")
    assert result["element_path"] == ["V-lift"]
    assert result["length_m"] == pytest.approx(LIFT_WAIT_M + 4.0)


def test_step_free_never_uses_stairs(syn):
    free = judge_route(syn, "S1", "T1", step_free=True)
    assert_valid_path(syn, free)
    assert "V-stairs" not in free["element_path"] and "V-lift" in free["element_path"]
    normal = judge_route(syn, "S1", "T1")
    assert "V-stairs" in normal["element_path"]
    assert normal["length_m"] < free["length_m"]


def test_step_free_no_route_says_so(syn):
    syn.closed.add("V-lift")
    result = judge_route(syn, "S1", "T1", step_free=True)
    assert result["ok"] is False and result["space_path"] == []
    assert "No step-free route" in result["reason"]


def test_closures_are_respected(syn):
    assert judge_route(syn, "S1", "W")["space_path"] == ["S1", "L", "W"]
    syn.closed.add("D-L-W")
    detour = judge_route(syn, "S1", "W")
    assert detour["space_path"] == ["S1", "L", "K", "T3", "T1", "T2", "W"]  # up by lift, down by stairs
    syn.closed.add("K")
    assert judge_route(syn, "S1", "W")["ok"] is False
    syn.closed.clear()
    assert judge_route(syn, "S1", "W")["space_path"] == ["S1", "L", "W"]


def test_bays_are_destinations_not_shortcuts(syn):
    syn.closed.add("D-A-R")  # now R is only reachable through bay B2
    result = judge_route(syn, "A", "R")
    assert result["ok"] is False, "a bay must not be used as a corridor"
    assert judge_route(syn, "A", "B2")["ok"]  # ...but it may be the destination
    assert judge_route(syn, "B2", "R")["space_path"] == ["B2", "R"]  # or the start


def test_assets_resolve_to_their_space(syn):
    result = judge_route(syn, "S1", "Press 1")
    assert_valid_path(syn, result)
    assert result["space_path"][-1] == "B1"


def test_via_stops(syn):
    result = judge_route(syn, "S1", "B2", via=["B1"])
    assert_valid_path(syn, result)
    assert result["space_path"] == ["S1", "L", "A", "B1", "B2"]


def test_same_start_and_end(syn):
    assert judge_route(syn, "S1", "S1") == {
        "ok": True,
        "space_path": ["S1"],
        "length_m": 0.0,
        "element_path": [],
        "reason": "",
    }


def test_forklift_uses_only_aisles_bays_and_wide_openings(syn):
    assert is_forklift_aisle(syn.spaces["A"]) and not is_forklift_aisle(syn.spaces["L"])
    assert is_bay(syn.spaces["B1"]) and not is_bay(syn.spaces["A"]) and not is_bay(syn.spaces["R"])
    result = judge_route(syn, "A", "B2", forklift=True)
    assert result["space_path"] == ["A", "B2"]
    assert all(syn.openings[e]["width_m"] >= FORKLIFT_MIN_WIDTH_M for e in result["element_path"])
    assert judge_route(syn, "A", "R", forklift=True)["ok"] is False  # store is neither aisle nor bay
    assert judge_route(syn, "L", "A", forklift=True)["ok"] is False  # pedestrian corridor
    # Width rule: the B1-B2 opening is 4 m, narrow it below 3 m and the forklift must go via the aisle.
    building = copy.deepcopy(synthetic_building())
    building["openings"][6]["width_m"] = 2.5
    narrow = BuildingMap(building)
    assert judge_route(narrow, "B1", "B2", forklift=True)["space_path"] == ["B1", "A", "B2"]
    assert judge_route(narrow, "B1", "B2")["space_path"] == ["B1", "B2"]


def test_shrink_falls_back_for_tiny_or_pinched_polygons():
    from shapely.geometry import Polygon

    tiny = Polygon(rect(0, 0, 0.2, 0.2))
    assert 0 < shrink(tiny).area < tiny.area  # vanishes at 15 cm: shrink by less
    hairline = Polygon(rect(0, 0, 0.05, 2))
    assert shrink(hairline).equals(hairline)  # vanishes at any clearance: keep the outline
    pinched = Polygon([[0, 0], [4, 0], [4, 2], [2.1, 2], [2.1, 4], [1.9, 4], [1.9, 2], [0, 2]])
    walkable = shrink(pinched)
    assert walkable.geom_type == "Polygon" and walkable.area > 0


def test_lift_without_elevation_uses_level_times_three():
    building = synthetic_building()
    for floor in building["floors"]:
        del floor["elevation_m"]
    bm = BuildingMap(building)
    assert judge_route(bm, "W", "T2", endpoint="door")["length_m"] == pytest.approx(STAIRS_M_PER_M_CLIMBED * 3.0)


# ---------- real buildings ----------


def route_questions() -> list[tuple[str, dict]]:
    found = []
    for split in ("train", "dev"):
        for path in sorted((DATA / split).glob("*/questions_basic.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    question = json.loads(line)
                    if question["kind"] in ("route", "route_step_free", "route_with_closure"):
                        found.append((str(path.parent), question))
    return found


ROUTE_CASES = route_questions()


@pytest.mark.skipif(not ROUTE_CASES, reason="data/ not fetched")
def test_labelled_route_questions_are_valid_and_agree_on_reachability():
    """Every route is a real walk (doors, stairs, lifts) and reachability matches the kit labels exactly."""
    checked = 0
    for building_dir, question in ROUTE_CASES:
        bm = load_map(building_dir)
        answer = question["answer"]
        bm.closed = {answer["closed_element_id"]} if "closed_element_id" in answer else set()
        try:
            result = judge_route(
                bm, answer["from_space_id"], answer["to_space_id"], step_free=question["kind"] == "route_step_free"
            )
        finally:
            bm.closed = set()
        if "space_path" not in answer:
            assert result["ok"] is False, question["id"]
            continue
        assert_valid_path(bm, result)
        assert result["space_path"][0] == answer["from_space_id"]
        assert result["space_path"][-1] == answer["to_space_id"]
        if "closed_element_id" in answer:
            assert answer["closed_element_id"] not in result["element_path"]
            assert answer["closed_element_id"] not in result["space_path"]
        if question["kind"] == "route_step_free":
            assert all(bm.openings[e]["step_free"] for e in result["element_path"] if e in bm.openings)
            assert all(bm.connectors[e]["step_free"] for e in result["element_path"] if e in bm.connectors)
        # Never shorter than the straight line between the two anchors (same floor only; height costs otherwise).
        router = router_for(bm)
        if bm.spaces[answer["from_space_id"]]["floor_id"] == bm.spaces[answer["to_space_id"]]["floor_id"]:
            straight = math.dist(router.anchor(answer["from_space_id"]), router.anchor(answer["to_space_id"]))
            assert result["length_m"] >= straight - 0.01, question["id"]
        checked += 1
    assert checked > 100


@pytest.mark.skipif(not ROUTE_CASES, reason="data/ not fetched")
def test_report_sequence_differences_from_kit_router(capsys):
    """Report only: how often the jury-model sequence differs from the kit label, per endpoint choice."""
    totals: dict[tuple[str, str], list[int]] = {}
    for building_dir, question in ROUTE_CASES:
        answer = question["answer"]
        if "space_path" not in answer:
            continue
        bm = load_map(building_dir)
        bm.closed = {answer["closed_element_id"]} if "closed_element_id" in answer else set()
        try:
            for endpoint in ("centre", "door"):
                result = judge_route(
                    bm,
                    answer["from_space_id"],
                    answer["to_space_id"],
                    step_free=question["kind"] == "route_step_free",
                    endpoint=endpoint,
                )
                counts = totals.setdefault((question["kind"], endpoint), [0, 0])
                counts[0] += 1
                counts[1] += result["space_path"] != answer["space_path"]
        finally:
            bm.closed = set()
    with capsys.disabled():
        print("\njudge_route vs kit labels (space sequence differs):")
        for (kind, endpoint), (total, differs) in sorted(totals.items()):
            print(f"  {kind:20s} endpoint={endpoint:6s} {differs:4d} of {total:4d} ({100 * differs / total:.0f}%)")


ALL_BUILDINGS = sorted(DATA.glob("*/*/building.json"))


@pytest.mark.skipif(not ALL_BUILDINGS, reason="data/ not fetched")
def test_every_building_routes_without_crashing():
    for path in ALL_BUILDINGS:
        bm = BuildingMap.load(path)
        ids = sorted(bm.spaces)
        result = judge_route(bm, ids[0], ids[-1])
        if result["ok"]:
            assert_valid_path(bm, result)
        forklift = judge_route(bm, ids[0], ids[-1], forklift=True)
        assert forklift["ok"] in (True, False)


@pytest.mark.skipif(not ALL_BUILDINGS, reason="data/ not fetched")
def test_factory_forklift_route_exists_and_bays_never_intermediate():
    factories = [p for p in ALL_BUILDINGS if "factory" in p.parent.name]
    assert factories
    routed = 0
    for path in factories:
        bm = BuildingMap.load(path)
        bays = [s for s in bm.spaces.values() if is_bay(s)]
        aisles = [s for s in bm.spaces.values() if is_forklift_aisle(s)]
        assert bays and aisles, path
        result = judge_route(bm, aisles[0]["id"], bays[-1]["id"], forklift=True)
        if result["ok"]:
            routed += 1
            assert_valid_path(bm, result)
            assert all(bm.openings[e]["width_m"] >= FORKLIFT_MIN_WIDTH_M for e in result["element_path"])
            assert all(s == "outside" or forklift_may_use(bm.spaces[s]) for s in result["space_path"])
            assert not any(s in bm.spaces and is_bay(bm.spaces[s]) for s in result["space_path"][1:-1])
        # pedestrians: bays are never a shortcut either
        walk = judge_route(bm, min(bm.spaces), bays[-1]["id"])
        if walk["ok"]:
            assert not any(s in bm.spaces and is_bay(bm.spaces[s]) for s in walk["space_path"][1:-1])
    assert routed > 0


@pytest.mark.skipif(not ALL_BUILDINGS, reason="data/ not fetched")
def test_one_route_on_the_largest_building_is_fast():
    largest = max(ALL_BUILDINGS, key=lambda p: p.stat().st_size)
    bm = BuildingMap.load(largest)  # fresh map: nothing cached yet
    ids = sorted(bm.spaces)
    start = time.perf_counter()
    result = judge_route(bm, ids[0], ids[-1])
    cold = time.perf_counter() - start
    start = time.perf_counter()
    judge_route(bm, ids[len(ids) // 3], ids[-2])
    warm = time.perf_counter() - start
    assert result["ok"] or result["reason"]
    assert cold < 1.0, f"cold route took {cold:.2f}s"
    assert warm < 0.5, f"warm route took {warm:.2f}s"
    assert isinstance(router_for(bm), JudgeRouter)


def test_unknown_place_is_a_reason_not_a_crash(syn):
    result = judge_route(syn, "S1", "Nowhere")
    assert result["ok"] is False and "No place matches" in result["reason"]


def test_closed_start_is_a_reason(syn):
    syn.closed.add("S1")
    assert "closed" in judge_route(syn, "S1", "W")["reason"]
