import itertools

import pytest
from shapely.geometry import Polygon

from building_agent.directions import (
    ADJACENT_DISTANCE_M,
    DirectionsSession,
    chunk_steps,
    landmark_directions,
    leg_landmarks,
    leg_space,
)
from starter_agent.building_map import OUTSIDE, MapError
from tests.conftest import DATA, load_map

BUILDINGS = sorted(str(path.parent) for path in (DATA / "dev").glob("*/building.json"))[:6]


def sample_routes(building_dir: str, limit: int = 8):
    """Deterministic routes between spaces spread over the building (several floors when possible)."""
    bm = load_map(building_dir)
    ids = sorted(bm.spaces)
    picks = ids[:: max(1, len(ids) // 6)]
    routes = []
    for start, end in itertools.permutations(picks, 2):
        try:
            routes.append(bm.route(start, end))
        except MapError:
            continue
        if len(routes) >= limit:
            break
    return bm, routes


def test_dev_buildings_present():
    assert BUILDINGS


@pytest.mark.parametrize("building_dir", BUILDINGS)
def test_steps_use_only_names_from_data(building_dir):
    bm, routes = sample_routes(building_dir)
    assert routes
    for route in routes:
        steps = landmark_directions(bm, route)
        assert len(steps) == len(route.steps)
        landmarks = leg_landmarks(bm, route)
        for index in range(1, len(route.space_path)):
            space_id = route.space_path[index]
            previous = route.space_path[index - 1]
            if OUTSIDE in (space_id, previous):
                continue
            if bm.spaces[space_id]["floor_id"] == bm.spaces[previous]["floor_id"]:
                assert bm.spaces[space_id]["name"] in steps[index]
        for step, landmark in zip(steps, landmarks, strict=True):
            if landmark:
                assert landmark.label in step


@pytest.mark.parametrize("building_dir", BUILDINGS)
def test_landmark_lies_in_or_touches_leg_space(building_dir):
    bm, routes = sample_routes(building_dir)
    found = 0
    for route in routes:
        for index, landmark in enumerate(leg_landmarks(bm, route)):
            if landmark is None:
                continue
            found += 1
            space_id = leg_space(route, index)
            if landmark.kind == "asset":
                assert bm.assets[landmark.id]["space_id"] == space_id
            else:
                other = bm.spaces[landmark.id]
                assert other["floor_id"] == bm.spaces[space_id]["floor_id"]
                gap = Polygon(bm.spaces[space_id]["polygon"]).distance(Polygon(other["polygon"]))
                assert gap <= ADJACENT_DISTANCE_M
    assert found


@pytest.mark.parametrize("building_dir", BUILDINGS)
def test_directions_are_deterministic(building_dir):
    bm, routes = sample_routes(building_dir, limit=3)
    for route in routes:
        assert landmark_directions(bm, route) == landmark_directions(bm, route)


def test_chunks_never_exceed_three():
    for count in range(12):
        steps = [f"s{i}" for i in range(count)]
        chunks = chunk_steps(steps)
        assert all(1 <= len(chunk) <= 3 for chunk in chunks)
        assert [step for chunk in chunks for step in chunk] == steps
    with pytest.raises(ValueError):
        chunk_steps(["a"], max_steps=0)


@pytest.mark.parametrize("building_dir", BUILDINGS)
def test_route_chunks_at_most_three(building_dir):
    bm, routes = sample_routes(building_dir)
    for route in routes:
        session = DirectionsSession.from_route(bm, route)
        assert all(len(chunk) <= 3 for chunk in session.chunks)


def test_session_next_repeat_remaining():
    steps = [f"s{i}" for i in range(7)]
    session = DirectionsSession(steps)
    assert session.repeat() == []
    assert session.remaining() == 7
    assert session.next() == ["s0", "s1", "s2"]
    assert session.remaining() == 4
    assert session.repeat() == ["s0", "s1", "s2"]
    assert session.remaining() == 4
    assert session.next() == ["s3", "s4", "s5"]
    assert session.next() == ["s6"]
    assert session.remaining() == 0
    assert session.next() == []
    assert session.repeat() == ["s6"]
