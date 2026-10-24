"""The route model (building_agent/routing.py) against the labelled answers, and against the kit's BuildingMap."""

import csv
import json
import random
import statistics
import time
from collections import defaultdict
from functools import cache
from pathlib import Path

import pytest

from building_agent import routing
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError
from tests.conftest import LABELLED_SPLITS, load_map

DATA = Path("data")
SOURCES = ("osm", "proc", "resplan", "swiss")
ROUTE_KINDS = ("route", "route_step_free", "route_with_closure", "tour")
BIGGEST = "data/dev/osm-way27917482"
SEED = 7
MAX_CLOSURES = 4
MAX_PER_BUILDING = 12
PER_SOURCE = 160  # cases per source, at least 300 reachable ones in total (about half are unreachable)
LENGTH_TOLERANCE = 0.001  # tour labels add rounded legs, so lengths agree to 0.1 percent, plain routes exactly
KIT_PAIRS = 300
KIT_BUILDINGS = 20


@cache
def building_dir(building_id: str) -> str:
    for split in LABELLED_SPLITS:
        path = DATA / split / building_id
        if path.exists():
            return str(path)
    raise FileNotFoundError(building_id)


def load_cases() -> dict[str, list[dict]]:
    """Reachable and unreachable route cases per source: start, end, step_free, closed element."""
    pools: dict[str, list[dict]] = defaultdict(list)
    for split in LABELLED_SPLITS:
        for path in sorted((DATA / split).glob("*/questions_basic.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                question = json.loads(line)
                kind, answer = question["kind"], question["answer"]
                if kind not in ROUTE_KINDS:
                    continue
                source = question["building_id"].split("-")[0]
                common = {"building": question["building_id"], "kind": kind}
                if kind == "tour":
                    for leg in answer.get("legs", []):  # no legs when a stop is unreachable (test_routing_tours)
                        pools[source].append(
                            {
                                **common,
                                "start": leg["from_space_id"],
                                "end": leg["to_space_id"],
                                "reachable": leg.get("reachable") is not False,
                                "length": leg.get("optimal_length_m"),
                                "space_path": leg.get("space_path"),
                            }
                        )
                    continue
                pools[source].append(
                    {
                        **common,
                        "start": answer["from_space_id"],
                        "end": answer["to_space_id"],
                        "step_free": kind == "route_step_free",
                        "closed": answer.get("closed_element_id"),
                        "reachable": answer.get("reachable") is not False,
                        "length": answer.get("optimal_length_m"),
                        "space_path": answer.get("space_path"),
                    }
                )
    rng = random.Random(SEED)
    for cases in pools.values():
        rng.shuffle(cases)
    # The sample stays on a few buildings per source and caps closure cases.
    picked = {}
    for source in SOURCES:
        buildings = sorted({c["building"] for c in pools[source]})
        random.Random(SEED).shuffle(buildings)
        keep, count = set(), 0
        for building in buildings:  # add buildings until the source has enough cases
            if count >= PER_SOURCE:
                break
            keep.add(building)
            count += min(MAX_PER_BUILDING, sum(c["building"] == building for c in pools[source]))
        pool = []
        per_building: dict[str, int] = defaultdict(int)
        for case in pools[source]:
            if case["building"] in keep and per_building[case["building"]] < MAX_PER_BUILDING:
                per_building[case["building"]] += 1
                pool.append(case)
        closures = [c for c in pool if c.get("closed")][:MAX_CLOSURES]
        others = [c for c in pool if not c.get("closed")]
        picked[source] = others[: PER_SOURCE - len(closures)] + closures
    return picked


@cache
def cases() -> tuple[dict, ...]:
    return tuple(case for source in SOURCES for case in load_cases()[source])


def run_route(case: dict):
    """Route one case with its closure applied; returns (bm, result)."""
    bm = load_map(building_dir(case["building"]))
    closed_before = set(bm.closed)
    if case.get("closed"):
        bm.closed.add(case["closed"])
    try:
        return bm, routing.route(bm, case["start"], case["end"], case.get("step_free", False))
    finally:
        bm.closed = closed_before


def joined(bm: BuildingMap, first: str, second: str, step_free: bool) -> bool:
    for opening in bm.openings.values():
        if set(opening["space_ids"]) == {first, second} and not (step_free and not opening["step_free"]):
            return opening["id"] not in bm.closed
    for connector in bm.connectors.values():
        if connector["id"] in bm.closed or (step_free and not connector["step_free"]):
            continue
        if first in connector["space_ids"] and second in connector["space_ids"]:
            return True
    return False


def test_agreement_with_the_labels():
    reachable = [case for case in cases() if case["reachable"]]
    assert len(reachable) >= 300
    ratios = []
    for case in reachable:
        bm, result = run_route(case)
        step_free = case.get("step_free", False)
        assert result.space_path == case["space_path"], case
        assert abs(result.length_m - case["length"]) <= max(0.02, LENGTH_TOLERANCE * case["length"]), case
        for first, second in zip(result.space_path, result.space_path[1:], strict=False):
            assert joined(bm, first, second, step_free), (case, first, second)
        ratios.append(result.length_m / case["length"] if case["length"] else 1.0)
    print(
        f"agreement n={len(ratios)} median={statistics.median(ratios):.5f} worst={max(ratios, key=lambda r: abs(r - 1)):.5f}"
    )


def test_unreachable_raises_map_error():
    unreachable = [case for case in cases() if not case["reachable"]]
    assert unreachable
    for case in unreachable:
        bm = load_map(building_dir(case["building"]))
        with pytest.raises(MapError, match="No .*route"):
            run_route(case)
        assert bm.last_route is None  # a failed route never leaves a stale route to be reported as the answer


@cache
def small_map() -> str:
    return building_dir("swiss-3355")


def test_closure_makes_target_unreachable():
    bm = BuildingMap.load(Path(small_map()))
    start, end = "swiss-3355-F0-S023", "swiss-3355-F2-S004"
    assert routing.route(bm, start, end).length_m > 0
    for connector in bm.connectors.values():
        bm.closed.add(connector["id"])
    with pytest.raises(MapError):
        routing.route(bm, start, end)
    bm.closed.clear()
    bm.closed.add(end)
    with pytest.raises(MapError):
        routing.route(bm, start, end)


def test_via_keeps_order():
    checked = 0
    for split in LABELLED_SPLITS:
        for path in sorted((DATA / split).glob("swiss-*/questions_basic.jsonl"))[:10]:
            for line in path.read_text(encoding="utf-8").splitlines():
                question = json.loads(line)
                if question["kind"] != "tour" or len(question["answer"].get("stops", [])) < 3:
                    continue
                stops = question["answer"]["stops"]
                bm = load_map(str(path.parent))
                try:
                    result = routing.route(bm, stops[0], stops[-1], via=stops[1:-1])
                except MapError:
                    continue
                position = -1
                for stop in stops:
                    position = result.space_path.index(stop, position + 1)
                assert bm.last_route is result
                assert len(result.steps) >= len(stops)
                checked += 1
    assert checked >= 5


def test_step_free_never_uses_a_step():
    checked = 0
    for case in cases():
        if case["kind"] != "route_step_free" or not case["reachable"]:
            continue
        bm, result = run_route(case)
        for first, second in zip(result.space_path, result.space_path[1:], strict=False):
            assert joined(bm, first, second, True)
        checked += 1
    assert checked >= 20


def test_no_route_leaves_and_reenters():
    bm = load_map(building_dir("swiss-3355"))
    entrances = [o for o in bm.openings.values() if OUTSIDE in o["space_ids"]]
    assert len(entrances) >= 2
    graph = routing.routing_graph(bm, False).graph
    assert OUTSIDE not in graph
    for entrance in entrances:
        node = f"door:{entrance['id']}"
        inside = bm.other_side(entrance, OUTSIDE)
        if node in graph:
            assert {space for _, _, space in graph.edges(node, data="space")} == {inside}


def test_same_length_as_the_kit_model():
    """One model: the same pair of rooms never gets two lengths in one building."""
    with (DATA / "manifest.csv").open(encoding="utf-8", newline="") as handle:
        paths = sorted(row["path"] for row in csv.DictReader(handle))
    rng = random.Random(SEED)
    buildings = rng.sample(paths, KIT_BUILDINGS)
    per_building = KIT_PAIRS // KIT_BUILDINGS
    compared = reachable = 0
    for relative in buildings:
        bm = load_map(str(DATA / relative))
        ids = sorted(bm.spaces)
        for _ in range(per_building):
            start, end = rng.sample(ids, 2)
            step_free = rng.random() < 0.3
            try:
                kit = bm.route(start, end, step_free)
            except MapError:
                with pytest.raises(MapError):
                    routing.route(bm, start, end, step_free)
                compared += 1
                continue
            ours = routing.route(bm, start, end, step_free)
            assert ours.length_m == kit.length_m and ours.space_path == kit.space_path, (start, end)
            assert ours.steps == kit.steps
            compared += 1
            reachable += 1
    assert compared == KIT_PAIRS and reachable >= KIT_PAIRS // 2


def test_same_room_route_is_trivial_in_both_models():
    bm = load_map(building_dir("swiss-3355"))
    space = next(iter(bm.spaces))
    ours = routing.route(bm, space, space)
    kit = bm.route(space, space)
    assert ours.space_path == kit.space_path == [space]
    assert ours.length_m == kit.length_m == 0.0
    assert len(ours.steps) == len(kit.steps) == 2


def test_cache_follows_closures_and_doors():
    bm = BuildingMap.load(Path(small_map()))
    first = routing.routing_graph(bm, False)
    assert routing.routing_graph(bm, False) is first
    bm.closed.add(next(iter(bm.connectors)))
    assert routing.routing_graph(bm, False) is not first
    assert routing.routing_graph(bm, True) is not routing.routing_graph(bm, False)


def test_runtime_on_largest_building():
    if not Path(BIGGEST).exists():
        pytest.skip("largest dev building missing")
    bm = BuildingMap.load(Path(BIGGEST))
    assert len(bm.spaces) > 1500
    ids = sorted(bm.spaces)
    rng = random.Random(SEED)
    started = time.perf_counter()
    answered = 0
    for _ in range(20):
        start, end = rng.sample(ids, 2)
        try:
            routing.route(bm, start, end)
        except MapError:
            pass
        answered += 1
    elapsed = time.perf_counter() - started
    print(f"largest building: graph + {answered} routes in {elapsed:.2f}s")
    assert elapsed < 10


def test_cache_notices_changed_opening_flags():
    bm = BuildingMap.load(Path(small_map()))
    first = routing.routing_graph(bm, False)
    opening = next(iter(bm.openings.values()))
    opening["step_free"] = not opening["step_free"]
    assert routing.routing_graph(bm, False) is not first


def test_load_map_shares_the_walks_between_maps():
    first = routing.load_map(Path(small_map()))
    start, end = "swiss-3355-F0-S023", "swiss-3355-F2-S004"
    expected = routing.route(first, start, end).length_m
    second = routing.load_map(Path(small_map()))
    assert second is not first and second.walks and second.walks.keys() == first.walks.keys()
    assert routing.route(second, start, end).length_m == expected
    second.closed.add(next(iter(second.openings)))  # edits of one map never leak into the other
    assert not first.closed
