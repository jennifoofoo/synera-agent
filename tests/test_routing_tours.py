"""Tours (via stops) in building_agent/routing.py: joint planning over all stops, scored like Synera does."""

import hashlib
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
GOLDEN = Path(__file__).parent / "fixtures" / "routing_plain_golden.json"
PLAIN_KINDS = ("route", "route_step_free", "route_with_closure")
PLAIN_SAMPLE = 300
TOUR_SAMPLE = 150  # of the 240 labelled tours; keeps the geodesic judge inside the time budget
SEED = 11
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


def plain_questions() -> list[tuple[str, dict]]:
    pool = [item for kind in PLAIN_KINDS for item in questions(kind)]
    return sorted(random.Random(SEED).sample(pool, PLAIN_SAMPLE), key=lambda item: item[1]["id"])


def plan(directory: str, start: str, end: str, via=None, step_free=False, closed=()):
    """Route on the shared map with extra closures applied; closures are restored afterwards."""
    bm = load_map(directory)
    before = set(bm.closed)
    bm.closed |= set(closed)
    try:
        return bm, routing.route(bm, start, end, step_free, via)
    finally:
        bm.closed = before


def route_digest(item: tuple[str, dict]):
    directory, question = item
    answer = question["answer"]
    closed = [answer["closed_element_id"]] if answer.get("closed_element_id") else []
    try:
        _, result = plan(
            directory,
            answer["from_space_id"],
            answer["to_space_id"],
            step_free=question["kind"] == "route_step_free",
            closed=closed,
        )
    except MapError:
        return "unreachable"
    return [result.length_m, hashlib.md5("|".join(result.space_path).encode()).hexdigest()]


def test_plain_routes_unchanged():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    items = plain_questions()
    assert len(items) == PLAIN_SAMPLE
    changed = [item[1]["id"] for item in items if route_digest(item) != golden[item[1]["id"]]]
    assert not changed, changed


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
    scores, invalid = [], 0
    for directory, tours in tour_buildings():
        judge_map = BuildingMap.load(Path(directory))
        for question in tours:
            stops = question["answer"]["stops"]
            try:
                bm, _ = plan(directory, stops[0], stops[-1], via=stops[1:-1])
                entry = route_entry(bm)
            except MapError:
                entry = None
            judged = score_route(judge_map, entry, question)
            invalid += not judged.valid
            scores.append(judged.score)
    full = sum(value >= 0.99 for value in scores) / len(scores)
    print(
        f"tours n={len(scores)} valid={1 - invalid / len(scores):.4f} share>=0.99={full:.4f} "
        f"mean={statistics.mean(scores):.4f} median={statistics.median(scores):.3f} worst={min(scores):.3f} "
        "(leg by leg before: share 0.983 and mean 0.9958 on all 240, worst 0.374)"
    )
    assert len(scores) >= TOUR_SAMPLE
    assert 1 - invalid / len(scores) >= 0.99
    assert full >= 0.97
    assert statistics.median(scores) == 1.0
    assert min(scores) >= 0.9


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


def leg_by_leg(bm: BuildingMap, stops: list[str]) -> list[str]:
    """The previous planner: every leg on its own, zero cost inside the stop spaces."""
    rg = routing.routing_graph(bm, False)
    spaces: list[str] = []
    for first, second in itertools.pairwise(stops):
        found = routing.shortest_leg(bm, rg, first, second)
        assert found is not None
        leg = routing.leg_spaces(first, second, found[1])
        spaces += leg if not spaces else leg[1:]
    return spaces


def test_joint_plan_beats_leg_by_leg():
    bm = synthetic_tour_map()
    assert leg_by_leg(bm, ["A", "M", "B"]) == ["A", "M", "B"]
    result = routing.route(bm, "A", "B", via=["M"])
    assert result.space_path == ["A", "Y", "M", "B"]
    assert result.length_m == pytest.approx(28.43 + 2.24, abs=0.05)
    assert routing.route(bm, "A", "B").length_m == result.length_m  # M lies on the best plain route anyway


def test_step_free_tour_avoids_the_step():
    bm = synthetic_tour_map()
    result = routing.route(bm, "A", "B", step_free=True, via=["M"])
    assert result.space_path == ["A", "M", "B"]
    assert result.step_free
    assert result.length_m == pytest.approx(35.01, abs=0.05)


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
    assert result.steps[0].startswith("Start in") and result.steps[-1].startswith("You have arrived")
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
