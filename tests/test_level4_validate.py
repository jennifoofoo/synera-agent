"""Level 4 step 1b: validation findings on a converted building. Offline, no API."""

import copy

import pytest

from building_agent.level4.convert import FloorInput, convert_floors
from building_agent.level4.schema import Finding, Findings, Scale
from building_agent.level4.validate import describe, validate
from tests.test_level4_convert import SCALE, simple_extraction, stair_floor


@pytest.fixture
def building() -> dict:
    return convert_floors([FloorInput(0, simple_extraction(), SCALE)], "Test", "t1")


def codes(building: dict) -> set[str]:
    return {finding.code for finding in validate(building).items}


def test_clean_building_has_no_findings(building):
    findings = validate(building)
    assert not findings.items and findings.ok
    assert findings.summary() == "No problems found."
    assert describe(findings) == "No problems found."


def test_invalid_polygon(building):
    building["spaces"][2]["polygon"] = [[0, 0], [5, 5], [5, 0], [0, 5]]
    assert "polygon_invalid" in codes(building)


def test_non_finite_polygon_is_invalid_not_a_crash(building):
    building["spaces"][2]["polygon"][0] = [float("nan"), 0]
    building["spaces"][1]["polygon"] = [[0, 0], [1, 1]]
    assert "polygon_invalid" in codes(building)


def test_tiny_room(building):
    building["spaces"][2]["polygon"] = [[10, 0], [10.5, 0], [10.5, 0.5], [10, 0.5]]
    assert "polygon_tiny" in codes(building)


def test_strong_overlap_but_not_touching_rooms(building):
    assert "room_overlap" not in codes(building)
    duplicate = copy.deepcopy(building["spaces"][2])
    duplicate["id"] = "t1-F0-S099"
    building["spaces"].append(duplicate)
    assert "room_overlap" in codes(building)


def test_door_not_on_shared_wall(building):
    building["openings"][0]["position"] = [2.0, 2.5]
    finding = next(item for item in validate(building).items if item.code == "door_not_on_wall")
    assert finding.items == ["0.01/0.02"] and finding.level == "error"


def test_door_between_rooms_that_do_not_touch(building):
    building["openings"][0]["space_ids"] = ["t1-F0-S001", "t1-F0-S003"]
    assert "door_not_on_wall" in codes(building)


def test_door_joining_the_same_room_twice_and_unknown_room(building):
    building["openings"][0]["space_ids"] = ["t1-F0-S001", "t1-F0-S001"]
    building["openings"][1]["space_ids"] = ["t1-F0-S002", "t1-F0-S777"]
    assert {"door_same_room", "door_unknown_room"} <= codes(building)


def test_no_entrance(building):
    building["openings"] = building["openings"][:2]
    findings = validate(building)
    assert "no_entrance" in {item.code for item in findings.items} and not findings.ok


def test_unreachable_rooms_use_refs(building):
    building["openings"] = [building["openings"][0], building["openings"][2]]
    finding = next(item for item in validate(building).items if item.code == "room_unreachable")
    assert finding.items == ["0.03"] and "no way out" in finding.message


def test_implausible_sizes_are_warnings(building):
    building["spaces"][2]["polygon"] = [[10, 0], [10.5, 0], [10.5, 5], [10, 5]]  # 2.5 m2 is fine
    assert "area_implausible" not in codes(building)
    building["spaces"][2]["polygon"] = [[10, 0], [40, 0], [40, 20], [10, 20]]  # 600 m2
    building["openings"][0]["width_m"] = 3.4
    findings = validate(building)
    by_code = {item.code: item for item in findings.items}
    assert by_code["area_implausible"].level == "warning" and by_code["door_width_implausible"].level == "warning"


def test_large_halls_and_corridors_may_exceed_300_m2(building):
    building["spaces"][2]["polygon"] = [[10, 0], [40, 0], [40, 20], [10, 20]]
    building["spaces"][2]["type"] = "hall"
    assert "area_implausible" not in codes(building)


def test_connector_without_stop_on_a_floor_in_between():
    floors = [stair_floor(level, f"{level}.09", "Stair A") for level in (0, 1, 2)]
    building = convert_floors(floors, "T", "t1")
    assert validate(building).ok
    connector = building["vertical_connectors"][0]
    connector["floor_ids"], connector["space_ids"] = (
        [connector["floor_ids"][0], connector["floor_ids"][2]],
        [
            connector["space_ids"][0],
            connector["space_ids"][2],
        ],
    )
    assert "connector_missing_stop" in codes(building)
    connector["space_ids"][1] = "t1-F0-S001"  # stop room on the wrong floor
    assert "connector_missing_stop" in codes(building)


@pytest.mark.parametrize("metres_per_px", [0.005, 2.0])
def test_scale_sanity(metres_per_px):
    scaled = convert_floors([FloorInput(0, simple_extraction(), Scale(metres_per_px, "known_length", ""))], "T", "t1")
    assert "scale_implausible" in codes(scaled)


def test_scale_in_range_is_fine(building):
    assert "scale_implausible" not in codes(building)


@pytest.mark.parametrize("broken", [{}, {"spaces": None}])
def test_incomplete_building_is_a_finding_not_a_crash(broken):
    findings = validate(broken)
    assert [item.code for item in findings.items] == ["building_invalid"] and not findings.ok


def test_space_without_outline_is_a_finding_not_a_crash():
    broken = {"floors": [], "spaces": [{"id": "x"}], "openings": [], "vertical_connectors": [], "assets": []}
    assert not validate(broken).ok


def test_describe_groups_by_code_with_counts_and_refs():
    findings = Findings(
        [
            Finding("error", "room_unreachable", "x", [f"0.{n:02d}" for n in range(15)]),
            Finding("error", "room_unreachable", "x", ["9.99"]),
            Finding("error", "no_entrance", "The building has no entrance to the outside."),
        ]
    )
    text = describe(findings)
    assert text.startswith("16 rooms have no way out, doors are probably missing: 0.00, 0.01")
    assert "..." in text and text.count("have no way out") == 1
    assert "The building has no entrance to the outside." in text
    assert chr(0x2014) not in text


def test_describe_singular_and_summary(building):
    building["openings"] = [building["openings"][0], building["openings"][2]]
    findings = validate(building)
    assert describe(findings) == "1 room has no way out, doors are probably missing: 0.03."
    assert findings.summary() == "1 room has no way out, doors are probably missing."
