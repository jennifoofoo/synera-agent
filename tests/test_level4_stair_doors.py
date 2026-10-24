"""Level 4 stair hall doors: offline tests on small synthetic buildings and a regression on real Swiss floors."""

import copy

import pytest

from building_agent.level4 import stair_doors
from building_agent.level4.convert import FloorInput, convert_floors_with_findings
from building_agent.level4.stair_doors import (
    describe_stair_doors,
    is_stair_hall,
    suggest_stair_doors,
    suggest_stairs_then_generic,
)
from building_agent.level4.suggest import apply_suggestions, describe_suggestions
from building_agent.level4.validate import validate
from scripts.eval_suggest import drop_stair_doors, run
from starter_agent.building_map import OUTSIDE
from tests.level4_helpers import DATA_DEV, floor_case
from tests.test_level4_suggest import building, door, rect, space

HALL = "t-F0-S001"
FIRST = "t-F0-S002"
SECOND = "t-F0-S003"


def hall(number: int = 1, polygon=None, kind: str = "corridor", room_type: str = "stairwell") -> dict:
    return space(number, polygon or rect(0, 0, 3, 10), kind, room_type)


def base(*spaces: dict, extra_doors: tuple = ()) -> dict:
    return building([hall(), *spaces], [door(1, HALL, OUTSIDE, "entrance"), *extra_doors])


def pairs(suggestions) -> list[set[str]]:
    return [{s.first, s.second} for s in suggestions]


def unreachable(data: dict) -> int:
    return sum(len(f.items) for f in validate(data).items if f.code == "room_unreachable")


def test_isolated_apartment_gets_a_door_to_the_stair_hall():
    data = base(space(2, rect(3, 0, 8, 5)), space(3, rect(3, 5, 8, 10)), extra_doors=(door(2, FIRST, SECOND),))
    [suggestion] = suggest_stair_doors(data)
    assert {suggestion.first, suggestion.second} <= {HALL, FIRST, SECOND} and HALL in pairs([suggestion])[0]
    assert suggestion.wall_length_m == pytest.approx(5.0, abs=0.1)
    assert suggestion.position[0] == pytest.approx(3.0, abs=0.01)
    assert unreachable(data) == 2 and unreachable(apply_suggestions(data, [suggestion])) == 0


def test_picks_the_stair_hall_not_a_plain_corridor_with_a_longer_wall():
    data = base(
        space(2, rect(3, 0, 8, 10)),
        space(3, rect(3, 10, 13, 12), "corridor", "corridor"),
        space(4, rect(8, 0, 13, 10)),
        extra_doors=(door(2, SECOND, "t-F0-S004"),),
    )
    assert pairs(suggest_stair_doors(data)) == [{HALL, FIRST}]


def test_corridor_type_hall_beats_a_pure_stair_with_a_longer_wall():
    stairs = space(3, rect(3, -6, 8, 0), "stair", "stairwell")
    data = building(
        [hall(), space(2, rect(3, 0, 8, 10)), stairs],
        [door(1, HALL, OUTSIDE, "entrance"), door(2, SECOND, HALL)],
    )
    assert pairs(suggest_stair_doors(data)) == [{HALL, FIRST}]
    only_stairs = building([space(2, rect(3, 0, 8, 10)), stairs], [])
    assert pairs(suggest_stair_doors(only_stairs)) == [{FIRST, SECOND}]


def test_the_door_goes_to_the_living_room_not_the_bathroom():
    data = base(
        space(2, rect(3, 0, 8, 5), "room", "bathroom"),
        space(3, rect(3, 5, 8, 10), "room", "living_room"),
        extra_doors=(door(2, FIRST, SECOND),),
    )
    assert pairs(suggest_stair_doors(data)) == [{HALL, SECOND}]


def test_no_shared_wall_of_at_least_0_9_m_gives_nothing():
    data = base(space(2, rect(3, 9.5, 8, 14)))
    assert suggest_stair_doors(data) == []
    assert suggest_stair_doors(base(space(2, rect(4, 0, 8, 10)))) == []


def test_already_connected_or_no_stair_hall_gives_nothing():
    connected = base(space(2, rect(3, 0, 8, 10)), extra_doors=(door(2, HALL, FIRST),))
    assert suggest_stair_doors(connected) == []
    plain = building([space(1, rect(0, 0, 3, 10)), space(2, rect(3, 0, 8, 10))], [door(1, "t-F0-S001", OUTSIDE)])
    assert suggest_stair_doors(plain) == []


def test_a_stair_hall_named_in_the_plan_counts():
    named = space(1, rect(0, 0, 3, 10), "room", "generic_room")
    named["name"] = "Treppenhaus"
    assert is_stair_hall(named) and not is_stair_hall(space(2, rect(0, 0, 1, 1)))
    data = building([named, space(2, rect(3, 0, 8, 10))], [door(1, HALL, OUTSIDE, "entrance")])
    assert pairs(suggest_stair_doors(data)) == [{HALL, FIRST}]


def test_one_door_per_apartment_and_per_stair_hall(monkeypatch):
    data = base(space(2, rect(3, 0, 8, 5)), space(3, rect(3, 5, 8, 10)))
    assert len(suggest_stair_doors(data)) == 2
    monkeypatch.setattr(stair_doors, "MAX_DOORS_PER_HALL", 1)
    assert len(suggest_stair_doors(data)) == 1
    one_apartment = base(space(2, rect(3, 0, 8, 5)), space(3, rect(3, 5, 8, 10)), extra_doors=(door(2, FIRST, SECOND),))
    assert len(suggest_stair_doors(one_apartment)) == 1


def test_deterministic_and_input_untouched():
    data = base(space(2, rect(3, 0, 8, 5)), space(3, rect(3, 5, 8, 10)))
    before = copy.deepcopy(data)
    first = suggest_stair_doors(data)
    assert first == suggest_stair_doors(data) and data == before
    assert suggest_stair_doors(data, max_suggestions=1) == first[:1]


def test_works_with_describe_suggestions():
    text = describe_suggestions(suggest_stair_doors(base(space(2, rect(3, 0, 8, 10)))))
    assert text.endswith("Say yes to add them.")


def test_card_text_for_stair_doors():
    text = describe_stair_doors(suggest_stair_doors(base(space(2, rect(3, 0, 8, 10)))))
    assert text.startswith(
        "These apartments have no door to the stair hall in the plan (it is usually not drawn). I suggest: "
    )
    assert text.endswith("Say yes to add them.") and "\u2014" not in text
    assert describe_stair_doors([]) == ""


def test_stairs_first_then_generic_for_what_is_left():
    corridor = space(4, rect(3, 10, 13, 12), "corridor", "corridor")
    far = space(5, rect(3, 12, 8, 16))
    data = base(space(2, rect(3, 0, 8, 10)), corridor, far, extra_doors=(door(2, "t-F0-S004", OUTSIDE, "entrance"),))
    stairs, rest = suggest_stairs_then_generic(data)
    assert pairs(stairs) == [{HALL, FIRST}]
    assert all({s.first, s.second} != {HALL, FIRST} for s in rest)
    assert unreachable(apply_suggestions(data, stairs + rest)) == 0
    assert suggest_stairs_then_generic({}) == ([], [])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.update(spaces=[], openings=[]),
        lambda b: b.update(spaces=b["spaces"][:1], openings=[]),
        lambda b: b["spaces"].append(space(9, [[0, 0], [5, 5], [5, 0], [0, 5]])),
        lambda b: b["spaces"].append(space(9, [[0, 0], [1, 1]])),
        lambda b: b["spaces"].append(space(9, [[float("nan"), 0], [1, 1], [2, 0]])),
        lambda b: b["spaces"].append({"id": "x"}),
        lambda b: b["spaces"].append({"id": "x", "floor_id": "t-F0", "polygon": rect(8, 0, 9, 1), "name": None}),
        lambda b: b["openings"].append({"id": "o", "space_ids": ["nope", OUTSIDE]}),
        lambda b: b["openings"].append({"space_ids": None}),
        lambda b: b.pop("openings"),
        lambda b: b.pop("spaces"),
        lambda b: b["vertical_connectors"].append({"space_ids": ["missing"]}),
    ],
)
def test_fuzz_never_crashes(mutate):
    data = base(space(2, rect(3, 0, 8, 10)))
    mutate(data)
    result = suggest_stair_doors(data)
    assert isinstance(result, list)
    if "spaces" in data and "openings" in data:
        apply_suggestions(data, result)


def test_fuzz_empty_dict():
    assert suggest_stair_doors({}) == []


# Measured on these floors with the stair doors dropped (see docs/eval-log.md): precision 100 percent, judge pairs >= 0.99 from 9-28 percent to 100 percent.
REAL_FLOORS = [("swiss-31", 0), ("swiss-203", 0), ("swiss-2074", 0)]


@pytest.mark.parametrize(("building_id", "level"), REAL_FLOORS)
def test_real_swiss_floor_with_the_stair_doors_dropped(building_id, level):
    if not (DATA_DEV / building_id).exists():
        pytest.skip("kit data missing (run scripts/get_data.sh)")
    case = drop_stair_doors(floor_case(building_id, level))
    assert case.dropped_doors > 0
    converted, _ = convert_floors_with_findings(
        [FloorInput(level, case.extraction, case.scale)], building_id, building_id
    )
    row = run(case, converted, f"{building_id}:{level}", "swiss", suggest_stair_doors)
    assert row["suggested"] >= 2
    assert row["real"] >= 0.9 * row["suggested"]
    assert row["judge_after"] >= max(0.9, row["judge_before"] + 0.5)
