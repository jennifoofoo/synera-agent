"""Level 4 graph score: room connectivity of a built building against the true one. Offline, no API."""

import copy

import pytest

from building_agent.level4.graph_score import graph_score


def space(index: int, x: float, y: float = 0.0, kind: str = "room") -> dict:
    return {
        "id": f"S{index}",
        "floor_id": "F0",
        "type": kind,
        "polygon": [[x, y], [x + 4, y], [x + 4, y + 4], [x, y + 4]],
    }


def door(a: str, b: str) -> dict:
    return {"id": f"{a}-{b}", "floor_id": "F0", "space_ids": [a, b], "kind": "door", "position": [0, 0]}


@pytest.fixture
def truth() -> dict:
    """Four rooms in a row, the first one has the entrance."""
    return {
        "floors": [{"id": "F0", "level": 0}],
        "spaces": [space(i, 4 * i) for i in range(4)],
        "openings": [door("outside", "S0"), door("S0", "S1"), door("S1", "S2"), door("S2", "S3")],
    }


def test_identical_building_scores_one(truth):
    score = graph_score(copy.deepcopy(truth), truth)
    assert score.composite == pytest.approx(1.0) and score.jaccard == 1.0 and score.matched == 4


def test_ids_do_not_matter_only_geometry(truth):
    built = copy.deepcopy(truth)
    renames = {f"S{i}": f"X{i}" for i in range(4)}
    for item in built["spaces"]:
        item["id"] = renames[item["id"]]
    for opening in built["openings"]:
        opening["space_ids"] = [renames.get(end, end) for end in opening["space_ids"]]
    assert graph_score(built, truth).composite == pytest.approx(1.0)


def test_missing_door_lowers_jaccard_and_door_ratio(truth):
    built = copy.deepcopy(truth)
    built["openings"].pop()
    score = graph_score(built, truth)
    assert score.jaccard == pytest.approx(3 / 4)
    assert score.doors == pytest.approx(3 / 4)
    assert score.composite < 1.0


def test_missing_room_lowers_the_score_without_crashing(truth):
    built = copy.deepcopy(truth)
    built["spaces"].pop()
    built["openings"].pop()
    score = graph_score(built, truth)
    assert score.matched == 3 and score.rooms == pytest.approx(3 / 4)
    assert score.degree < 1.0 and score.composite < 1.0


def test_extra_room_counts_against_the_build(truth):
    built = copy.deepcopy(truth)
    built["spaces"].append(space(9, 40))
    built["openings"].append(door("S3", "S9"))
    score = graph_score(built, truth)
    assert score.matched == 4 and score.jaccard == pytest.approx(4 / 5)
    assert score.built_rooms == 5 and score.degree < 1.0


def test_wrong_connection_between_matched_rooms(truth):
    built = copy.deepcopy(truth)
    built["openings"][-1] = door("S0", "S3")
    score = graph_score(built, truth)
    assert score.jaccard == pytest.approx(3 / 5)


def test_offset_aligns_a_shifted_frame(truth):
    built = copy.deepcopy(truth)
    for item in built["spaces"]:
        item["polygon"] = [[x + 100, y + 50] for x, y in item["polygon"]]
    assert graph_score(built, truth).matched == 0
    assert graph_score(built, truth, offset=(100, 50)).composite == pytest.approx(1.0)


def test_other_floor_level_does_not_match(truth):
    built = copy.deepcopy(truth)
    built["floors"] = [{"id": "F0", "level": 1}]
    assert graph_score(built, truth).matched == 0


def test_stairs_and_outdoor_are_not_nodes(truth):
    built = copy.deepcopy(truth)
    built["spaces"].append(space(8, 0, 10, kind="stair"))
    built["openings"].append(door("S0", "S8"))
    assert graph_score(built, truth).composite == pytest.approx(1.0)


def test_empty_buildings_do_not_crash():
    empty = {"floors": [], "spaces": [], "openings": []}
    assert graph_score(empty, empty).composite == pytest.approx(1.0)
    one = {"floors": [{"id": "F0", "level": 0}], "spaces": [space(0, 0)], "openings": [door("outside", "S0")]}
    assert graph_score(empty, one).composite < 0.3
    assert graph_score(one, empty).composite < 0.3


def test_broken_polygons_and_doors_are_skipped(truth):
    built = copy.deepcopy(truth)
    built["spaces"][1]["polygon"] = [[0, 0], [1, 1]]
    built["openings"].append({"space_ids": ["nope", "S0"]})
    assert graph_score(built, truth).composite < 1.0


def test_built_room_over_a_true_stair_is_ignored_not_extra(truth):
    truth["spaces"].append(space(8, 0, 10, kind="stair"))
    built = copy.deepcopy(truth)
    built["spaces"][-1]["type"] = "room"  # the extraction typed the stair as a room
    built["openings"].append(door("S0", "S8"))
    score = graph_score(built, truth)
    assert score.built_rooms == 4 and score.composite == pytest.approx(1.0)
