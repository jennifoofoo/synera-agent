"""Level 4: entrances must sit on the outer wall of the floor (snap, re-attach, drop). Offline."""

import dataclasses
from pathlib import Path

import pytest

from building_agent.level4.convert import FloorInput, convert_floors_with_findings, scale_from_known_length
from building_agent.level4.schema import ExtractedDoor, ExtractedRoom, Extraction, Scale
from building_agent.level4.validate import validate
from scripts.eval_level4 import best_offset, load_cached
from tests.level4_helpers import SAMPLE_FLOORS, floor_case, measure

SCALE = Scale(0.05, "known_length", "test")
FACTORY_FIXTURE = Path("tests/fixtures/level4/factory003_extraction.json")


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def convert(rooms, doors, height=100):
    extraction = Extraction(width_px=400, height_px=height, rooms=rooms, doors=doors)
    building, findings = convert_floors_with_findings([FloorInput(0, extraction, SCALE)], "T", "t1")
    entrances = [o for o in building["openings"] if "outside" in o["space_ids"]]
    return building, entrances, {finding.code for finding in findings.items}


def entrance(room, x, y, width_px=18):
    return ExtractedDoor((room, "outside"), [x, y], kind="entrance", width_px=width_px)


def two_rooms():
    return [ExtractedRoom("a", rect(0, 0, 100, 100)), ExtractedRoom("b", rect(100, 0, 200, 100))]


def test_entrance_on_an_interior_wall_is_dropped_with_a_warning():
    _, entrances, codes = convert(two_rooms(), [entrance("a", 100, 50)])
    assert entrances == [] and "entrance_dropped" in codes


def test_entrance_1_m_off_the_outer_wall_is_snapped_onto_it():
    building, entrances, codes = convert(two_rooms(), [entrance("a", -20, 50)])
    assert len(entrances) == 1 and "entrance_dropped" not in codes
    assert entrances[0]["position"][0] == pytest.approx(0.0, abs=0.01)
    assert "entrance_not_on_outer_wall" not in {f.code for f in validate(building).items}


def test_entrance_attached_to_a_neighbour_is_moved_to_the_room_on_the_outer_wall():
    building, entrances, codes = convert(two_rooms(), [entrance("b", 96, 1)])
    names = {s["id"]: s["name"] for s in building["spaces"]}
    assert len(entrances) == 1 and "entrance_reattached" in codes
    assert names[entrances[0]["space_ids"][0]] == "Room 1"  # room a


def test_entrance_marker_far_from_the_named_room_is_a_guess_and_dropped():
    _, entrances, codes = convert(two_rooms(), [entrance("b", 4, 50)])
    assert entrances == [] and "entrance_dropped" in codes


def test_room_without_any_exterior_wall_gets_no_entrance():
    grid = [
        ExtractedRoom(f"r{i}{j}", rect(i * 100, j * 100, i * 100 + 100, j * 100 + 100))
        for i in range(3)
        for j in range(3)
    ]
    _, entrances, codes = convert(grid, [entrance("r11", 150, 150)], height=300)
    assert entrances == [] and "entrance_dropped" in codes


def test_implausibly_many_entrances_are_cut_to_the_limit():
    doors = [entrance("a", 5 + 9 * i, 0, width_px=8) for i in range(10)]
    _, entrances, codes = convert([ExtractedRoom("a", rect(0, 0, 100, 100))], doors)
    assert len(entrances) == 8 and "entrance_dropped" in codes


def test_validate_flags_an_entrance_that_sits_inside_the_building():
    building, entrances, _ = convert(two_rooms(), [entrance("a", 50, 0)])
    assert "entrance_not_on_outer_wall" not in {f.code for f in validate(building).items}
    entrances[0]["position"] = [5.0, 2.5]  # on the wall between a and b, 2.5 m from the outside
    assert "entrance_not_on_outer_wall" in {f.code for f in validate(building).items}


# ---------- round trips on real floors ----------


def shifted_inwards(case, pixels):
    """Every entrance marker moved towards the centre of the plan, as if the model put it on an interior wall."""
    xs = [x for room in case.extraction.rooms for x, _ in room.polygon_px]
    ys = [y for room in case.extraction.rooms for _, y in room.polygon_px]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    doors = []
    for door in case.extraction.doors:
        if "outside" in door.rooms:
            dx, dy = cx - door.position_px[0], cy - door.position_px[1]
            length = max((dx * dx + dy * dy) ** 0.5, 1e-9)
            moved = [door.position_px[0] + dx / length * pixels, door.position_px[1] + dy / length * pixels]
            door = dataclasses.replace(door, position_px=moved)
        doors.append(door)
    return dataclasses.replace(case, extraction=dataclasses.replace(case.extraction, doors=doors))


def judge_invalid(case):
    converted, _ = convert_floors_with_findings(
        [FloorInput(case.level, case.extraction, case.scale)], "Round trip", "rt1"
    )
    return measure(case, converted)["judge_invalid"]


@pytest.mark.parametrize(("building_id", "level"), SAMPLE_FLOORS)
def test_noisy_extraction_introduces_no_invalid_routes(building_id, level):
    assert judge_invalid(floor_case(building_id, level, noise_px=3, seed=5)) == 0


@pytest.mark.parametrize(("building_id", "level"), SAMPLE_FLOORS)
def test_entrances_shifted_inwards_introduce_no_invalid_routes(building_id, level):
    assert judge_invalid(shifted_inwards(floor_case(building_id, level), 100)) == 0


def test_factory_003_cached_extraction_has_no_invalid_sequences():
    """The extraction invented two lobby entrances; they must be dropped and reported, not used as shortcuts."""
    result = load_cached(FACTORY_FIXTURE)
    case = floor_case("proc-factory-dev-003", 0)
    xs = [x for s in case.truth["spaces"] for x, _ in s["polygon"]]
    scale = scale_from_known_length(result.extraction, max(xs) - min(xs))
    converted, findings = convert_floors_with_findings(
        [FloorInput(0, result.extraction, scale)], "proc-factory-dev-003", "proc-factory-dev-003"
    )
    case = dataclasses.replace(case, extraction=result.extraction, scale=scale)
    case = dataclasses.replace(case, offset=best_offset(case, converted))
    measured = measure(case, converted)
    assert measured["judge_pairs"] > 0
    assert measured["judge_invalid"] == 0
    assert "entrance_dropped" in {f.code for f in findings.items}
    assert len([o for o in converted["openings"] if "outside" in o["space_ids"]]) == 4
