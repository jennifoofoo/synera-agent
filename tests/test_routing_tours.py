"""Tours (via stops) in building_agent/routing.py: legs in order, like the labelled tours, scored like Synera does."""

import itertools
import json
import random
import statistics
import time
from functools import cache
from pathlib import Path

import pytest

from building_agent import routing
from building_agent.judge_score import score_route
from building_agent.structured import route_entry
from starter_agent.building_map import BuildingMap, MapError
from tests.conftest import LABELLED_SPLITS, load_map

DATA = Path("data")
TOUR_SAMPLE = 150  # of the 240 labelled tours
SEED = 11
LENGTH_TOLERANCE = 0.001  # labels add rounded legs
BIGGEST = "data/dev/osm-way27917482"


@cache
def questions(kind: str) -> tuple[tuple[str, dict], ...]:
    found = []
    for split in LABELLED_SPLITS:
        for path in sorted((DATA / split).glob("*/questions_basic.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip() and (question := json.loads(line))["kind"] == kind:
                    found.append((str(path.parent), question))
    return tuple(found)


def plan(directory: str, start: str, end: str, via=None, step_free=False, closed=()):
    """Route on the shared map with extra closures applied; closures are restored afterwards."""
    bm = load_map(directory)
    before = set(bm.closed)
    bm.closed |= set(closed)
    try:
        return bm, routing.route(bm, start, end, step_free, via)
    finally:
        bm.closed = before


def tour_buildings() -> list[tuple[str, list[dict]]]:
    """Buildings with labelled tours, shuffled by seed and cut after TOUR_SAMPLE tours (whole buildings)."""
    by_building: dict[str, list[dict]] = {}
    for directory, question in questions("tour"):
        by_building.setdefault(directory, []).append(question)
    names = sorted(by_building)
    random.Random(SEED).shuffle(names)
    picked, count = [], 0
    for name in names:
        if count >= TOUR_SAMPLE:
            break
        picked.append((name, by_building[name]))
        count += len(by_building[name])
    return picked


def test_labelled_tours_score_like_synera():
    scores, invalid, unreachable = [], 0, 0
    for directory, tours in tour_buildings():
        judge_map = BuildingMap.load(Path(directory))
        for question in tours:
            stops = question["answer"]["stops"]
            try:
                bm, result = plan(directory, stops[0], stops[-1], via=stops[1:-1])
                entry = route_entry(bm)
                if question["answer"].get("reachable") is not False:
                    legs = []
                    for leg in question["answer"]["legs"]:
                        legs += leg["space_path"] if not legs else leg["space_path"][1:]
                    assert result.space_path == legs, question["id"]
                    label = question["answer"]["optimal_length_m"]
                    assert abs(result.length_m - label) <= max(0.02, LENGTH_TOLERANCE * label), question["id"]
            except MapError:
                entry = None
                unreachable += 1
            judged = score_route(judge_map, entry, question)
            invalid += not judged.valid
            scores.append(judged.score)
    full = sum(value >= 0.99 for value in scores) / len(scores)
    print(
        f"tours n={len(scores)} unreachable={unreachable} valid={1 - invalid / len(scores):.4f} "
        f"share>=0.99={full:.4f} mean={statistics.mean(scores):.4f} worst={min(scores):.3f}"
    )
    assert len(scores) >= TOUR_SAMPLE
    assert unreachable > 0  # the sample holds tours with an unreachable stop; they must say so, not crash
    assert invalid == 0
    assert full == 1.0


def test_unreachable_tours_raise_no_route():
    checked = 0
    for directory, question in questions("tour"):
        answer = question["answer"]
        if answer.get("reachable") is not False:
            continue
        stops = answer["stops"]
        bm = load_map(directory)
        with pytest.raises(MapError, match="No .*route"):
            routing.route(bm, stops[0], stops[-1], via=stops[1:-1])
        assert bm.last_route is None
        checked += 1
    assert checked >= 5


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def synthetic_tour_map() -> BuildingMap:
    """A starts at the left of a long hall M. Via X (A-M door at x=5) the hall must be crossed to reach B at x=40;
    via Y (not step-free) the walk ends next to B. Zero cost inside stop spaces picks X, the joint plan picks Y."""
    names = {"A": rect(0, 0, 10, 10), "M": rect(0, 10, 40, 12), "Y": rect(10, 0, 40, 10), "B": rect(40, 10, 50, 12)}
    spaces = [
        {"id": sid, "floor_id": "F0", "type": "room", "room_type": "office", "name": sid, "polygon": polygon}
        for sid, polygon in names.items()
    ]

    def door(oid, first, second, position, step_free=True):
        return {
            "id": oid,
            "floor_id": "F0",
            "space_ids": [first, second],
            "kind": "door",
            "position": position,
            "width_m": 0.9,
            "step_free": step_free,
        }

    return BuildingMap(
        {
            "building": {"id": "syn-tour", "name": "Tour", "source": "test"},
            "floors": [{"id": "F0", "level": 0, "name": "Ground floor", "elevation_m": 0.0, "height_m": 3.0}],
            "spaces": spaces,
            "openings": [
                door("D-AM", "A", "M", [5, 10]),
                door("D-AY", "A", "Y", [10, 5], step_free=False),
                door("D-YM", "Y", "M", [38, 10]),
                door("D-MB", "M", "B", [40, 11]),
            ],
            "vertical_connectors": [],
            "assets": [],
        }
    )


def test_tour_is_the_sum_of_its_legs():
    bm = synthetic_tour_map()
    first, second = routing.route(bm, "A", "M"), routing.route(bm, "M", "B")
    result = routing.route(bm, "A", "B", via=["M"])
    assert result.space_path == ["A", "M", "B"]
    assert result.length_m == pytest.approx(first.length_m + second.length_m, abs=0.01)
    assert routing.route(bm, "A", "B").length_m < result.length_m  # via Y is shorter, but the tour must stop at M


def test_step_free_tour_avoids_the_step():
    bm = synthetic_tour_map()
    result = routing.route(bm, "A", "B", step_free=True, via=["M"])
    assert result.space_path == ["A", "M", "B"]
    assert result.step_free
    assert result.length_m == pytest.approx(45.32, abs=0.05)


def test_tour_can_revisit_a_space():
    bm = synthetic_tour_map()
    result = routing.route(bm, "A", "B", via=["M", "A"])
    path = result.space_path
    assert path.count("A") == 2 and path[0] == "A" and path[-1] == "B"
    assert path.index("M") < len(path) - 1 - path[::-1].index("A")
    assert all(first != second for first, second in itertools.pairwise(path))
    assert bm.last_route is result


def test_stop_equal_to_previous_stop_adds_nothing():
    bm = synthetic_tour_map()
    once = routing.route(bm, "A", "B", via=["M"])
    twice = routing.route(bm, "A", "B", via=["M", "M"])
    assert twice.space_path == once.space_path and twice.length_m == once.length_m
    start_twice = routing.route(bm, "A", "B", via=["A"])
    assert start_twice.space_path == routing.route(bm, "A", "B").space_path


def test_closure_that_cuts_a_leg_raises():
    bm = synthetic_tour_map()
    bm.closed = {"D-MB"}
    with pytest.raises(MapError):
        routing.route(bm, "A", "B", via=["M"])
    bm.closed = {"M"}
    with pytest.raises(MapError):
        routing.route(bm, "A", "B", via=["M"])
    bm.closed = {"D-AM", "D-YM"}  # M is then cut off from A and Y
    with pytest.raises(MapError):
        routing.route(bm, "A", "B", via=["M"])
    bm.closed = {"D-AY"}
    assert routing.route(bm, "A", "B", via=["M"]).space_path == ["A", "M", "B"]


def test_tour_steps_cover_every_space_change():
    bm = synthetic_tour_map()
    result = routing.route(bm, "A", "B", via=["M"])
    assert result.steps[0].startswith("Start in") and "You have arrived at" in result.steps[-1]
    assert len(result.steps) == len(result.space_path) + 1


def test_runtime_of_tours_on_the_largest_building():
    if not Path(BIGGEST).exists():
        pytest.skip("largest dev building missing")
    bm = BuildingMap.load(Path(BIGGEST))
    ids = sorted(bm.spaces)
    rng = random.Random(SEED)
    started = time.perf_counter()
    for _ in range(10):
        stops = rng.sample(ids, 4)
        try:
            routing.route(bm, stops[0], stops[-1], via=stops[1:-1])
        except MapError:
            pass
    elapsed = time.perf_counter() - started
    print(f"largest building: graph + 10 tours with 2 via stops in {elapsed:.2f}s")
    assert elapsed < 10
