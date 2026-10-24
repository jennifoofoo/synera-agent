"""The door-to-door route model (building_agent/routing.py) against the geodesic measure from the route spike."""

import json
import random
import statistics
import time
from collections import defaultdict
from functools import cache
from pathlib import Path

import pytest

from building_agent import routing
from spikes.route.geodesic import model_for
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError
from tests.conftest import LABELLED_SPLITS, load_map

DATA = Path("data")
SOURCES = ("osm", "proc", "resplan", "swiss")
ROUTE_KINDS = ("route", "route_step_free", "route_with_closure", "tour")
BIGGEST = "data/dev/osm-way27917482"
SEED = 7
MAX_CLOSURES = 4
MAX_PER_BUILDING = 12  # keeps the slow geodesic reference graphs of single buildings out of the test time
PER_SOURCE = 80  # cases per source, at least 300 reachable ones in total
# The whole dev+train population (1457 reachable cases) gives 99.4 percent; a sparse sample of osm/swiss-heavy
# cases scatters around 98.8 to 99.4, so the test guards at 98 percent.
MIN_SHARE_FULL_MARKS = 0.98


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
                    legs = [
                        (leg["from_space_id"], leg["to_space_id"], leg.get("reachable") is not False)
                        for leg in answer["legs"]
                    ]
                    for start, end, reachable in legs:
                        pools[source].append({**common, "start": start, "end": end, "reachable": reachable})
                    continue
                pools[source].append(
                    {
                        **common,
                        "start": answer["from_space_id"],
                        "end": answer["to_space_id"],
                        "step_free": kind == "route_step_free",
                        "closed": answer.get("closed_element_id"),
                        "reachable": answer.get("reachable") is not False,
                    }
                )
    rng = random.Random(SEED)
    for cases in pools.values():
        rng.shuffle(cases)
    # The geodesic reference graph is slow to build (once per building, step-free flag and closure), so the
    # sample stays on a few buildings per source and caps closure cases.
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


def score(case: dict, result) -> float:
    bm = load_map(building_dir(case["building"]))
    closed_before = set(bm.closed)
    if case.get("closed"):
        bm.closed.add(case["closed"])
    try:
        step_free = case.get("step_free", False)
        model = model_for(bm, step_free=step_free, closed=bm.closed)
        # The spike builds the per-space visibility graphs once per model; share them across variants.
        model.geoms = bm.__dict__.setdefault("_shared_geoms", {})
        best = model.best_route(case["start"], case["end"])
        ours = model.measure(result.space_path)
    finally:
        bm.closed = closed_before
    if ours is None:
        return 0.0
    assert best is not None
    return 1.0 if ours <= 1e-9 else min(1.0, best[1] / ours)


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


def test_agreement_with_geodesic_measure():
    reachable = [case for case in cases() if case["reachable"]]
    assert len(reachable) >= 300
    scores = []
    for case in reachable:
        bm, result = run_route(case)
        step_free = case.get("step_free", False)
        assert result.space_path[0] == case["start"] and result.space_path[-1] == case["end"]
        for first, second in zip(result.space_path, result.space_path[1:], strict=False):
            assert joined(bm, first, second, step_free), (case, first, second)
        scores.append(score(case, result))
    share = sum(value >= 0.99 for value in scores) / len(scores)
    print(
        f"agreement n={len(scores)} share>=0.99={share:.4f} median={statistics.median(scores):.3f} worst={min(scores):.3f}"
    )
    assert share >= MIN_SHARE_FULL_MARKS


def test_unreachable_raises_map_error():
    unreachable = [case for case in cases() if not case["reachable"]]
    assert unreachable
    for case in unreachable:
        with pytest.raises(MapError):
            run_route(case)


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
        for path in sorted((DATA / split).glob("swiss-*/questions_basic.jsonl"))[:3]:
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


def test_outside_entrances_cost_nothing():
    bm = load_map(building_dir("swiss-3355"))
    entrances = [o for o in bm.openings.values() if OUTSIDE in o["space_ids"]]
    inside = [bm.other_side(o, OUTSIDE) for o in entrances]
    assert len(entrances) >= 2
    graph = routing.routing_graph(bm, False).graph
    for entrance in entrances:
        node = ("o", entrance["id"], OUTSIDE)
        assert graph.degree(node) >= 1
        for neighbour in graph[node]:
            if neighbour[2] == OUTSIDE:
                assert graph[node][neighbour]["weight"] == 0.0
    assert inside


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
