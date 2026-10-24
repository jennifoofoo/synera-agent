"""Level 4 step 1b: conversion of extractions to building.json. Offline, no API.

Round trip: real dev floors become artificial extractions (known scale, optional noise), get converted and are
measured against the original. Fuzz: odd input yields Findings, only unusable input raises ConvertError."""

import math
import statistics
import time

import pytest

from building_agent.level4.convert import (
    ConvertError,
    FloorInput,
    convert_floors,
    convert_floors_with_findings,
    scale_from_bar,
    scale_from_known_length,
)
from building_agent.level4.schema import ExtractedDoor, ExtractedRoom, Extraction, Scale
from building_agent.level4.validate import validate
from starter_agent.building_map import BuildingMap
from tests.level4_helpers import SAMPLE_FLOORS, floor_case, load_building, measure

SCALE = Scale(0.05, "known_length", "test")


def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def simple_extraction(**changes) -> Extraction:
    """Three rooms in a row (5 m each at 0.05 m/px), doors A-B and B-C, an entrance into A."""
    extraction = Extraction(
        width_px=300,
        height_px=100,
        rooms=[
            ExtractedRoom("a", rect(0, 0, 100, 100), ref="0.01", name="Hall"),
            ExtractedRoom("b", rect(100, 0, 200, 100), ref="0.02", type="corridor"),
            ExtractedRoom("c", rect(200, 0, 300, 100), ref="0.03", room_type="office"),
        ],
        doors=[
            ExtractedDoor(("a", "b"), [100, 50], width_px=18),
            ExtractedDoor(("b", "c"), [200, 50], width_px=18),
            ExtractedDoor(("a", "outside"), [0, 50], kind="entrance"),
        ],
    )
    for key, value in changes.items():
        setattr(extraction, key, value)
    return extraction


def build(extraction: Extraction, scale: Scale = SCALE, level: int = 0):
    return convert_floors_with_findings([FloorInput(level, extraction, scale)], "Test", "t1")


def codes(findings) -> set[str]:
    return {finding.code for finding in findings.items}


# ---------- round trip on real floors ----------


def convert_case(case):
    return convert_floors_with_findings([FloorInput(case.level, case.extraction, case.scale)], "Round trip", "rt1")


@pytest.mark.parametrize(("building_id", "level"), SAMPLE_FLOORS)
def test_round_trip_without_noise_gives_everything_back(building_id, level):
    case = floor_case(building_id, level)
    converted, _ = convert_case(case)
    result = measure(case, converted)
    assert result["rooms_matched"] == result["rooms_true"] == result["rooms_found"]
    assert result["area_err_median"] < 0.01
    assert result["area_err_max"] < 0.025  # one ResPlan room has a self-touching outline that gets repaired
    assert result["route_err_max"] < 0.03
    assert result["door_recall"] >= (0.9 if building_id.startswith("osm") else 1.0)
    BuildingMap(converted)


def test_round_trip_with_noise_of_3_px_keeps_doors_and_routes():
    recalls, medians = [], []
    for building_id, level in SAMPLE_FLOORS:
        case = floor_case(building_id, level, noise_px=3, seed=5)
        converted, _ = convert_case(case)
        result = measure(case, converted)
        assert result["rooms_matched"] == result["rooms_true"]
        assert result["door_recall"] >= 0.8
        assert result["route_err_median"] < 0.05
        recalls.append(result["door_recall"])
        medians.append(result["route_err_median"])
    assert statistics.mean(recalls) >= 0.9
    assert statistics.median(medians) < 0.05


def test_round_trip_with_noise_of_8_px_still_converts_and_reports():
    for building_id, level in SAMPLE_FLOORS[:4]:
        case = floor_case(building_id, level, noise_px=8, seed=5)
        converted, findings = convert_case(case)
        result = measure(case, converted)
        assert result["rooms_matched"] >= 0.9 * result["rooms_true"]
        assert result["door_recall"] > 0.1
        if result["door_recall"] < 0.9:
            assert findings.items or validate(converted).items  # a degraded floor never looks clean


@pytest.mark.parametrize("building_id", ["proc-campus-dev-000", "proc-factory-dev-003", "resplan-439"])
def test_dropped_doors_are_reported_as_unreachable_rooms(building_id):
    case = floor_case(building_id, 0, drop_doors=0.5, seed=2)
    assert case.dropped_doors > 0
    converted, _ = convert_case(case)
    assert "room_unreachable" in codes(validate(converted))


def test_clean_floor_validates_without_errors():
    converted, _ = convert_case(floor_case("proc-factory-dev-003", 0))
    assert validate(converted).ok


def test_multi_floor_building_links_stairs_and_routes_between_floors():
    building = load_building("proc-campus-dev-000")
    floors = []
    for level in (0, 1, 2):
        case = floor_case("proc-campus-dev-000", level)
        floors.append(FloorInput(level, case.extraction, case.scale))
    converted = convert_floors(floors, "Campus", "campus1")
    assert [floor["level"] for floor in converted["floors"]] == [0, 1, 2]
    assert converted["vertical_connectors"]
    assert {len(connector["floor_ids"]) for connector in converted["vertical_connectors"]} == {3}
    assert validate(converted).ok
    bm = BuildingMap(converted)
    top = next(space for space in converted["spaces"] if space["floor_id"].endswith("F2") and space["type"] == "room")
    ground = next(
        space for space in converted["spaces"] if space["floor_id"].endswith("F0") and space["type"] == "room"
    )
    assert bm.route(top["id"], ground["id"]).length_m > 0
    original_connectors = [c for c in building["vertical_connectors"] if len(c["floor_ids"]) >= 3]
    assert len(converted["vertical_connectors"]) >= len(original_connectors) - 1


# ---------- format and conventions ----------


def test_converted_dict_has_kit_format_and_loads():
    building, findings = build(simple_extraction())
    assert not findings.items
    assert set(building) == {"building", "floors", "spaces", "openings", "vertical_connectors", "assets"}
    assert [space["id"] for space in building["spaces"]] == ["t1-F0-S001", "t1-F0-S002", "t1-F0-S003"]
    assert [opening["id"] for opening in building["openings"]] == ["t1-F0-O0001", "t1-F0-O0002", "t1-F0-O0003"]
    bm = BuildingMap(building)
    route = bm.route("0.03", "0.01")
    assert route.space_path == ["t1-F0-S003", "t1-F0-S002", "t1-F0-S001"]
    assert route.length_m == pytest.approx(10.0, abs=0.5)
    assert any("outside" in opening["space_ids"] for opening in bm.openings.values())


def test_y_is_flipped_and_pixels_become_metres():
    extraction = simple_extraction()
    extraction.rooms[0].polygon_px = [[0, 0], [100, 0], [100, 40], [0, 40]]  # top 2 m of the image
    building = convert_floors([FloorInput(0, extraction, SCALE)], "Test", "t1")
    ys = [y for _, y in building["spaces"][0]["polygon"]]
    assert (min(ys), max(ys)) == (3.0, 5.0)
    assert max(x for x, _ in building["spaces"][0]["polygon"]) == 5.0


def test_names_types_and_room_types():
    extraction = simple_extraction()
    extraction.rooms += [
        ExtractedRoom("d", rect(300, 0, 400, 100), ref=None, name=None),
        ExtractedRoom("e", rect(400, 0, 500, 100), name="Main stair", type="stair"),
        ExtractedRoom("f", rect(500, 0, 600, 100), type="weird"),  # type: ignore[arg-type]
    ]
    spaces = {
        space["ref"] or space["name"]: space
        for space in convert_floors([FloorInput(0, extraction, SCALE)], "T", "t1")["spaces"]
    }
    assert spaces["0.01"]["name"] == "Hall"
    assert spaces["0.02"]["name"] == "Room 0.02" and spaces["0.02"]["room_type"] == "corridor"
    assert spaces["0.03"]["room_type"] == "office"
    assert spaces["Room 4"]["room_type"] == "generic_room"
    assert spaces["Main stair"]["room_type"] == "stairwell" and spaces["Main stair"]["type"] == "stair"
    assert spaces["Room 6"]["type"] == "room"


def test_door_width_is_clamped_with_default():
    extraction = simple_extraction()
    extraction.doors[0].width_px = 5000
    extraction.doors[1].width_px = 2
    extraction.doors[2].width_px = None
    widths = [
        opening["width_m"] for opening in convert_floors([FloorInput(0, extraction, SCALE)], "T", "t1")["openings"]
    ]
    assert widths == [2.5, 0.7, 0.9]


def test_entrance_joins_room_and_outside_on_the_wall():
    extraction = simple_extraction()
    extraction.doors[2].position_px = [8, 50]  # a little inside the room, snapped to the wall
    building = convert_floors([FloorInput(0, extraction, SCALE)], "T", "t1")
    entrance = building["openings"][2]
    assert entrance["space_ids"] == ["t1-F0-S001", "outside"] and entrance["kind"] == "entrance"
    assert entrance["position"][0] == pytest.approx(0.0, abs=0.01)


CLEAN_FLOORS = [item for item in SAMPLE_FLOORS if item[0].startswith(("proc-", "resplan-"))]


@pytest.mark.parametrize(("building_id", "level"), CLEAN_FLOORS)
def test_median_route_error_at_3_px_noise_stays_under_3_percent_on_clean_floors(building_id, level):
    case = floor_case(building_id, level, noise_px=3, seed=5)
    converted, _ = convert_case(case)
    assert measure(case, converted)["route_err_median"] < 0.03


def test_door_is_projected_onto_the_shared_wall():
    extraction = simple_extraction()
    extraction.doors[0].position_px = [106, 50]  # 0.3 m beside the wall
    building = convert_floors([FloorInput(0, extraction, SCALE)], "T", "t1")
    assert building["openings"][0]["position"][0] == pytest.approx(5.0, abs=0.01)


def test_tiny_gaps_between_rooms_are_closed():
    extraction = simple_extraction()
    extraction.rooms[1].polygon_px = rect(100.5, 0, 200, 100)  # 0.025 m gap
    building = convert_floors([FloorInput(0, extraction, SCALE)], "T", "t1")
    first, second = building["spaces"][0]["polygon"], building["spaces"][1]["polygon"]
    assert max(x for x, _ in first) == min(x for x, _ in second)


# ---------- stairs and lifts ----------


def stair_floor(level: int, ref: str, name: str | None = None, kind: str = "stair", at: float = 300) -> FloorInput:
    extraction = simple_extraction()
    extraction.rooms.append(ExtractedRoom("s", rect(at, 0, at + 100, 100), ref=ref, name=name, type=kind))
    extraction.doors.append(ExtractedDoor(("c", "s"), [at, 50]))
    return FloorInput(level, extraction, SCALE)


def test_stairs_with_same_name_or_same_position_become_one_connector():
    by_name = convert_floors([stair_floor(1, "1.09", "Stair A"), stair_floor(0, "0.09", "stair a")], "T", "t1")
    by_place = convert_floors([stair_floor(0, "0.09"), stair_floor(1, "1.09")], "T", "t1")
    for building in (by_name, by_place):
        (connector,) = building["vertical_connectors"]
        assert connector["id"] == "t1-V01" and connector["kind"] == "stairs" and not connector["step_free"]
        assert connector["floor_ids"] == ["t1-F0", "t1-F1"]  # ordered by level, also when given reversed
        assert connector["space_ids"] == ["t1-F0-S004", "t1-F1-S004"]
        assert not validate(building).errors


def test_lift_connector_is_step_free_and_unmatched_stairs_stay_rooms_with_a_warning():
    building, findings = convert_floors_with_findings(
        [stair_floor(0, "0.09", kind="lift"), stair_floor(1, "1.09", kind="lift", at=900)], "T", "t1"
    )
    assert len(building["vertical_connectors"]) == 1  # one lift on each floor: linked by order, with a warning
    assert "connector_linked_by_order" in codes(findings)
    first = stair_floor(0, "0.09", kind="lift")
    extra = ExtractedRoom("t", rect(600, 0, 700, 100), ref="0.10", type="lift")
    first.extraction.rooms.append(extra)
    first.extraction.doors.append(ExtractedDoor(("c", "t"), [600, 50]))
    building, findings = convert_floors_with_findings([first, stair_floor(1, "1.09", kind="lift", at=900)], "T", "t1")
    assert not building["vertical_connectors"]
    assert "connector_single_floor" in codes(findings)
    linked, _ = convert_floors_with_findings(
        [stair_floor(0, "0.09", kind="lift"), stair_floor(1, "1.09", kind="lift")], "T", "t1"
    )
    assert linked["vertical_connectors"][0]["kind"] == "lift" and linked["vertical_connectors"][0]["step_free"]


def test_three_floors_give_one_connector_with_three_stops():
    floors = [stair_floor(level, f"{level}.09", "Stair A") for level in (0, 1, 2)]
    (connector,) = convert_floors(floors, "T", "t1")["vertical_connectors"]
    assert connector["floor_ids"] == ["t1-F0", "t1-F1", "t1-F2"]


def test_single_floor_with_a_stair_gives_no_warning():
    _, findings = convert_floors_with_findings([stair_floor(0, "0.09")], "T", "t1")
    assert "connector_single_floor" not in codes(findings)


# ---------- scale ----------


def test_scale_from_known_building_width():
    scale = scale_from_known_length(simple_extraction(), 30.0)
    assert scale.metres_per_px == pytest.approx(0.1) and scale.source == "known_length"


def test_scale_from_room_and_door():
    extraction = simple_extraction()
    assert scale_from_known_length(extraction, 5.0, "room", "0.02").metres_per_px == pytest.approx(0.05)
    assert scale_from_known_length(extraction, 0.9, "door").metres_per_px == pytest.approx(0.05)


@pytest.mark.parametrize(
    "call",
    [
        lambda e: scale_from_known_length(e, 0),
        lambda e: scale_from_known_length(e, -3),
        lambda e: scale_from_known_length(e, float("nan")),
        lambda e: scale_from_known_length(e, 5, "room", "nope"),
        lambda e: scale_from_known_length(e, 5, "diagonal"),
        lambda e: scale_from_known_length(Extraction(10, 10, [], []), 5),
        lambda e: scale_from_known_length(Extraction(10, 10, e.rooms, []), 1, "door"),
    ],
)
def test_scale_from_unusable_length_raises_convert_error(call):
    with pytest.raises(ConvertError):
        call(simple_extraction())


def test_scale_from_bar():
    extraction = simple_extraction(scale_bar_px=200, scale_bar_m=10)
    assert scale_from_bar(extraction).metres_per_px == pytest.approx(0.05)
    assert scale_from_bar(simple_extraction()) is None
    assert scale_from_bar(simple_extraction(scale_bar_px=0, scale_bar_m=10)) is None


# ---------- fuzz: findings instead of crashes ----------


def test_self_intersecting_polygon_is_repaired_with_a_finding():
    extraction = simple_extraction()
    extraction.rooms[2].polygon_px = [[200, 0], [300, 100], [300, 0], [200, 100]]  # bow tie
    building, findings = build(extraction)
    assert "polygon_repaired" in codes(findings)
    assert validate(building).items is not None
    BuildingMap(building)


def test_duplicate_rooms_are_kept_and_flagged_by_validation():
    extraction = simple_extraction()
    extraction.rooms.append(ExtractedRoom("c2", rect(200, 0, 300, 100), ref="0.04"))
    building, _ = build(extraction)
    assert len(building["spaces"]) == 4
    assert "room_overlap" in codes(validate(building))


def test_duplicate_room_id_is_dropped_with_a_finding():
    extraction = simple_extraction()
    extraction.rooms.append(ExtractedRoom("a", rect(300, 0, 400, 100)))
    building, findings = build(extraction)
    assert len(building["spaces"]) == 3 and "room_duplicate_id" in codes(findings)


def test_door_with_missing_room_far_from_wall_or_same_room_is_dropped():
    extraction = simple_extraction()
    extraction.doors += [
        ExtractedDoor(("a", "zzz"), [100, 50]),
        ExtractedDoor(("a", "c"), [100, 50]),  # rooms do not touch
        ExtractedDoor(("a", "b"), [20, 50]),  # 4 m from the wall
        ExtractedDoor(("a", "a"), [50, 50]),
        ExtractedDoor(("outside", "outside"), [0, 0]),
        ExtractedDoor(("a", "b"), [float("nan"), 3]),
        ExtractedDoor(("a",), [100, 50]),  # type: ignore[arg-type]
    ]
    building, findings = build(extraction)
    assert len(building["openings"]) == 3
    assert {"door_unknown_room", "door_not_on_wall", "door_same_room", "door_bad_position"} <= codes(findings)


def test_zero_area_nan_and_garbage_rooms_are_dropped_with_findings():
    extraction = simple_extraction()
    extraction.rooms += [
        ExtractedRoom("z", [[400, 0], [450, 0], [500, 0]]),
        ExtractedRoom("n", [[0, 0], [float("nan"), 1], [3, 3]]),
        ExtractedRoom("i", [[0, 0], [float("inf"), 1], [3, 3]]),
        ExtractedRoom("t", [[0, 0], [1, 1]]),
        ExtractedRoom("g", [["a", "b"], [1, 2], [3, 4]]),  # type: ignore[list-item]
        ExtractedRoom("x", None),  # type: ignore[arg-type]
    ]
    building, findings = build(extraction)
    assert len(building["spaces"]) == 3 and "polygon_dropped" in codes(findings)


def test_missing_entrance_is_reported_by_validation_not_by_conversion():
    extraction = simple_extraction()
    extraction.doors = extraction.doors[:2]
    building, findings = build(extraction)
    assert not findings.items
    assert "no_entrance" in codes(validate(building))


def test_floor_without_rooms_next_to_a_good_one_is_a_finding():
    empty = Extraction(100, 100, [], [])
    building, findings = convert_floors_with_findings(
        [FloorInput(0, simple_extraction(), SCALE), FloorInput(1, empty, SCALE)], "T", "t1"
    )
    assert "floor_empty" in codes(findings) and len(building["floors"]) == 2


@pytest.mark.parametrize("factor", [0, -0.05, float("nan"), float("inf"), "x"])
def test_unusable_scale_raises_convert_error(factor):
    with pytest.raises(ConvertError):
        build(simple_extraction(), Scale(factor, "known_length"))  # type: ignore[arg-type]


def test_unusable_inputs_raise_convert_error():
    with pytest.raises(ConvertError):
        convert_floors([], "T", "t1")
    with pytest.raises(ConvertError):
        build(Extraction(100, 100, [], []))
    with pytest.raises(ConvertError):
        convert_floors([FloorInput(0, simple_extraction(), SCALE)] * 2, "T", "t1")
    with pytest.raises(ConvertError):
        convert_floors([FloorInput(0, simple_extraction(), SCALE)], "T", "")
    with pytest.raises(ConvertError):
        build(Extraction(100, 100, [ExtractedRoom("a", [[0, 0], [1, 1], [2, 2]])], []))


def test_floors_with_different_pixel_sizes_convert():
    small = simple_extraction()
    large = Extraction(
        width_px=2000,
        height_px=700,
        rooms=[ExtractedRoom("a", rect(0, 0, 1000, 700), ref="1.01"), ExtractedRoom("b", rect(1000, 0, 2000, 700))],
        doors=[ExtractedDoor(("a", "b"), [1000, 300], width_px=90)],
    )
    building = convert_floors(
        [FloorInput(0, small, SCALE), FloorInput(1, large, Scale(0.01, "scale_bar", ""))], "T", "t1"
    )
    assert len(building["spaces"]) == 5
    bm = BuildingMap(building)
    assert bm.route("1.01", "t1-F1-S002").length_m > 0


def test_one_floor_only_is_enough():
    building = convert_floors([FloorInput(3, simple_extraction(), SCALE)], "T", "t1")
    assert [floor["level"] for floor in building["floors"]] == [3]
    assert building["floors"][0]["id"] == "t1-F3"


def test_thousands_of_rooms_convert_and_validate_fast():
    size, cell = 50, 40
    rooms = [
        ExtractedRoom(f"r{row}_{col}", rect(col * cell, row * cell, (col + 1) * cell, (row + 1) * cell))
        for row in range(size)
        for col in range(size)
    ]
    doors = [ExtractedDoor(("r0_0", "outside"), [0, 20], kind="entrance")]
    for row in range(size):
        for col in range(size):
            if col + 1 < size:
                doors.append(ExtractedDoor((f"r{row}_{col}", f"r{row}_{col + 1}"), [(col + 1) * cell, row * cell + 20]))
            if row + 1 < size:
                doors.append(ExtractedDoor((f"r{row}_{col}", f"r{row + 1}_{col}"), [col * cell + 20, (row + 1) * cell]))
    start = time.perf_counter()
    building, findings = convert_floors_with_findings(
        [FloorInput(0, Extraction(size * cell, size * cell, rooms, doors), Scale(0.1, "known_length", ""))],
        "Big",
        "big",
    )
    result = validate(building)
    elapsed = time.perf_counter() - start
    assert len(building["spaces"]) == size * size and len(building["openings"]) == len(doors)
    assert not findings.items and result.ok
    assert elapsed < 20


def test_converted_numbers_are_finite_json():
    building, _ = build(simple_extraction())
    for space in building["spaces"]:
        assert all(math.isfinite(value) for point in space["polygon"] for value in point)
