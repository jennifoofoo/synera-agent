"""Level 4 door suggestions: offline tests on small synthetic buildings."""

import copy
import json

import pytest

from building_agent.level4.suggest import Suggestion, apply_suggestions, describe_suggestions, suggest_doors
from building_agent.level4.validate import validate
from starter_agent.building_map import OUTSIDE


def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def space(number: int, polygon: list[list[float]], kind: str = "room", room_type: str = "generic_room") -> dict:
    return {
        "id": f"t-F0-S{number:03d}",
        "floor_id": "t-F0",
        "type": kind,
        "room_type": room_type,
        "name": f"Room {number}",
        "ref": f"0.{number:02d}",
        "polygon": polygon,
        "synthetic": False,
    }


def door(number: int, first: str, second: str, kind: str = "door") -> dict:
    return {
        "id": f"t-F0-O{number:04d}",
        "floor_id": "t-F0",
        "space_ids": [first, second],
        "kind": kind,
        "position": [1.0, 1.0],
        "width_m": 0.9,
        "step_free": True,
        "synthetic": False,
    }


def building(spaces: list[dict], openings: list[dict]) -> dict:
    return {
        "building": {"id": "t", "name": "Test"},
        "floors": [{"id": "t-F0", "level": 0, "name": "Ground floor", "elevation_m": 0.0, "height_m": 3.0}],
        "spaces": spaces,
        "openings": openings,
        "vertical_connectors": [],
        "assets": [],
    }


CORRIDOR = "t-F0-S001"
ROOM_A = "t-F0-S002"
ROOM_B = "t-F0-S003"


def base(*extra_spaces: dict, extra_doors: tuple = ()) -> dict:
    corridor = space(1, rect(0, 0, 10, 2), "corridor", "corridor")
    return building([corridor, *extra_spaces], [door(1, CORRIDOR, OUTSIDE, "entrance"), *extra_doors])


def unreachable(data: dict) -> int:
    return sum(len(f.items) for f in validate(data).items if f.code == "room_unreachable")


def pairs(suggestions: list[Suggestion]) -> list[set[str]]:
    return [{s.first, s.second} for s in suggestions]


def test_isolated_room_next_to_corridor_gets_the_corridor_wall():
    data = base(space(2, rect(0, 2, 4, 6)))
    [suggestion] = suggest_doors(data)
    assert {suggestion.first, suggestion.second} == {CORRIDOR, ROOM_A}
    assert suggestion.wall_length_m == pytest.approx(4.0, abs=0.1)
    assert suggestion.position[1] == pytest.approx(2.0, abs=0.01) and 0 <= suggestion.position[0] <= 4
    assert suggestion.first_ref and suggestion.second_ref and suggestion.reason
    assert unreachable(data) == 1 and unreachable(apply_suggestions(data, [suggestion])) == 0


def test_corridor_beats_a_longer_wall_to_a_plain_room():
    data = base(
        space(2, rect(0, 2, 4, 8)),
        space(3, rect(4, 2, 12, 8)),
        extra_doors=(door(2, CORRIDOR, ROOM_B),),
    )
    assert pairs(suggest_doors(data)) == [{CORRIDOR, ROOM_A}]


def test_stair_is_the_last_choice():
    stair = space(3, rect(4, 2, 6, 6), "stair", "stairwell")
    data = base(space(2, rect(0, 2, 4, 6)), stair, extra_doors=(door(2, CORRIDOR, ROOM_B),))
    assert pairs(suggest_doors(data)) == [{CORRIDOR, ROOM_A}]
    only_stair = base(space(2, rect(11, 2, 14, 6)), space(3, rect(14, 2, 16, 6), "stair", "stairwell"))
    only_stair["openings"].append(door(2, CORRIDOR, ROOM_B))
    assert pairs(suggest_doors(only_stair)) == [{ROOM_A, ROOM_B}] or suggest_doors(only_stair) == []


def test_chain_of_two_isolated_rooms_is_fully_connected():
    data = base(space(2, rect(0, 2, 4, 6)), space(3, rect(0, 6, 4, 10)))
    suggestions = suggest_doors(data)
    assert pairs(suggestions) == [{CORRIDOR, ROOM_A}, {ROOM_A, ROOM_B}]
    assert unreachable(apply_suggestions(data, suggestions)) == 0


def test_no_shared_wall_long_enough_gives_nothing():
    far = space(2, rect(0, 5, 4, 9))  # 3 m from the corridor
    short = space(3, rect(9.5, 2, 12, 5))  # only 0.5 m of wall
    assert suggest_doors(base(far, short)) == []


def test_already_connected_gives_empty_list():
    data = base(space(2, rect(0, 2, 4, 6)), extra_doors=(door(2, CORRIDOR, ROOM_A),))
    assert suggest_doors(data) == []


def test_never_suggests_a_pair_that_already_has_a_door():
    data = base(space(2, rect(0, 2, 4, 6)), space(3, rect(4, 2, 8, 6)), extra_doors=(door(2, ROOM_A, ROOM_B),))
    suggestions = suggest_doors(data)
    assert all({s.first, s.second} != {ROOM_A, ROOM_B} for s in suggestions)
    assert unreachable(apply_suggestions(data, suggestions)) == 0


def test_deterministic_and_input_untouched():
    data = base(space(2, rect(0, 2, 4, 6)), space(3, rect(4, 2, 8, 6)), space(4, rect(0, 6, 4, 10)))
    snapshot = copy.deepcopy(data)
    first = suggest_doors(data)
    assert first == suggest_doors(copy.deepcopy(data))
    assert data == snapshot
    assert first == suggest_doors(data)


def test_max_suggestions_caps_the_list():
    rooms = [space(n + 2, rect(n * 2, 2, n * 2 + 2, 5)) for n in range(5)]
    assert len(suggest_doors(base(*rooms), max_suggestions=2)) == 2
    assert suggest_doors(base(*rooms), max_suggestions=0) == []


def test_apply_keeps_data_in_sync_and_ids_unique():
    data = base(space(2, rect(0, 2, 4, 6)), space(3, rect(0, 6, 4, 10)))
    suggestions = suggest_doors(data)
    fixed = apply_suggestions(data, suggestions)
    assert len(data["openings"]) == 1 and len(fixed["openings"]) == 3
    ids = [o["id"] for o in fixed["openings"]]
    assert len(set(ids)) == len(ids)
    new = fixed["openings"][1:]
    assert all(o["synthetic"] is True and o["width_m"] == 0.9 and o["kind"] == "door" for o in new)
    assert all(o["floor_id"] == "t-F0" and len(o["space_ids"]) == 2 for o in new)
    json.dumps(fixed)
    assert not [f for f in validate(fixed).items if f.level == "error"]
    assert apply_suggestions(fixed, suggestions)["openings"] == fixed["openings"]


def test_apply_avoids_taken_ids():
    data = base(space(2, rect(0, 2, 4, 6)))
    [suggestion] = suggest_doors(data)
    taken = {**door(2, CORRIDOR, ROOM_A), "space_ids": [CORRIDOR, OUTSIDE], "id": "t-F0-O-sug2"}
    data["openings"].append(taken)
    ids = [o["id"] for o in apply_suggestions(data, [suggestion])["openings"]]
    assert len(set(ids)) == len(ids)


def test_without_any_entrance_the_larger_group_is_the_reference():
    data = base(space(2, rect(0, 2, 4, 6)), space(3, rect(4, 2, 8, 6)), extra_doors=(door(2, ROOM_A, ROOM_B),))
    data["openings"] = [o for o in data["openings"] if OUTSIDE not in o["space_ids"]]
    assert pairs(suggest_doors(data)) == [{CORRIDOR, ROOM_A}]


def test_room_inside_a_bigger_room_can_get_a_door():
    hall = space(2, rect(20, 20, 60, 60), "hall", "lobby")
    data = base(hall, space(3, rect(30, 30, 33, 33)), extra_doors=(door(2, CORRIDOR, "t-F0-S002"),))
    assert pairs(suggest_doors(data)) == [{"t-F0-S002", ROOM_B}]


def test_describe_suggestions_in_plain_words():
    text = describe_suggestions(suggest_doors(base(space(2, rect(0, 2, 4, 6)))))
    assert text.startswith("I suggest these 1 door: ") and text.endswith("Say yes to add them.")
    assert describe_suggestions([]) == ""
    many = [Suggestion("a", "b", "r1", "r2", "f", (0.0, 0.0), 1.0, 1.0, "x")] * 10
    assert "and 2 more" in describe_suggestions(many)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.update(spaces=[], openings=[]),
        lambda b: b.update(spaces=b["spaces"][:1], openings=[]),
        lambda b: b["spaces"].append(space(9, [[0, 0], [5, 5], [5, 0], [0, 5]])),
        lambda b: b["spaces"].append(space(9, [[0, 0], [1, 1]])),
        lambda b: b["spaces"].append(space(9, [[float("nan"), 0], [1, 1], [2, 0]])),
        lambda b: b["spaces"].append({"id": "x"}),
        lambda b: b["openings"].append({"id": "o", "space_ids": ["nope", OUTSIDE]}),
        lambda b: b["openings"].append({"space_ids": None}),
        lambda b: b.pop("openings"),
        lambda b: b.pop("spaces"),
        lambda b: b["vertical_connectors"].append({"space_ids": ["missing"]}),
    ],
)
def test_fuzz_never_crashes(mutate):
    data = base(space(2, rect(0, 2, 4, 6)))
    mutate(data)
    result = suggest_doors(data)
    assert isinstance(result, list)
    if "spaces" in data and "openings" in data:
        apply_suggestions(data, result)


def test_fuzz_empty_dict():
    assert suggest_doors({}) == []
    assert apply_suggestions({}, [])["openings"] == []
