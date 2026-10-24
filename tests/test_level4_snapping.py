"""Door snapping onto the shared wall (synthetic rooms, 0.05 m per pixel, y flipped, plan height 100 px)."""

import pytest

from building_agent.level4.convert import FloorInput, convert_floors_with_findings
from building_agent.level4.schema import ExtractedDoor, ExtractedRoom, Extraction, Scale

SCALE = Scale(0.05, "known_length", "test")


def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def convert(rooms: list[ExtractedRoom], doors: list[ExtractedDoor]):
    extraction = Extraction(width_px=300, height_px=100, rooms=rooms, doors=doors)
    building, findings = convert_floors_with_findings([FloorInput(0, extraction, SCALE)], "T", "t1")
    return building["openings"], {finding.code for finding in findings.items}


def two_rooms() -> list[ExtractedRoom]:
    return [ExtractedRoom("a", rect(0, 0, 100, 100)), ExtractedRoom("b", rect(100, 0, 200, 100))]


def test_door_0_3_m_off_the_wall_is_snapped_without_warning():
    openings, codes = convert(two_rooms(), [ExtractedDoor(("a", "b"), [106, 20], width_px=18)])
    assert openings[0]["position"] == pytest.approx([5.0, 4.0], abs=0.01)
    assert "door_moved" not in codes


def test_door_a_bit_further_off_is_snapped_and_warned():
    openings, codes = convert(two_rooms(), [ExtractedDoor(("a", "b"), [111, 50], width_px=18)])
    assert openings[0]["position"][0] == pytest.approx(5.0, abs=0.01)
    assert "door_moved" in codes


def test_door_2_m_off_the_wall_is_dropped_as_not_on_a_wall():
    openings, codes = convert(two_rooms(), [ExtractedDoor(("a", "b"), [60, 50], width_px=18)])
    assert openings == [] and "door_not_on_wall" in codes


def test_wall_shorter_than_the_door_keeps_the_door_on_the_wall():
    rooms = [ExtractedRoom("a", rect(0, 0, 100, 100)), ExtractedRoom("b", rect(100, 0, 200, 10))]  # 0.5 m wall
    openings, _ = convert(rooms, [ExtractedDoor(("a", "b"), [102, 5], width_px=18)])
    x, y = openings[0]["position"]
    assert x == pytest.approx(5.0, abs=0.01) and 4.5 - 0.01 <= y <= 5.0 + 0.01


def test_three_rooms_meeting_at_a_corner_get_doors_on_their_own_walls():
    rooms = [
        ExtractedRoom("a", rect(0, 0, 100, 100)),
        ExtractedRoom("b", rect(100, 0, 200, 50)),
        ExtractedRoom("c", rect(100, 50, 200, 100)),
    ]
    doors = [ExtractedDoor(("a", "b"), [104, 50], width_px=18), ExtractedDoor(("a", "c"), [104, 50], width_px=18)]
    openings, _ = convert(rooms, doors)
    ab, ac = openings[0]["position"], openings[1]["position"]
    assert ab[0] == pytest.approx(5.0, abs=0.01) and ac[0] == pytest.approx(5.0, abs=0.01)
    assert ab[1] >= 2.5 - 0.01  # b is the lower wall piece in the image (y 0..50 px = 5 .. 2.5 m)
    assert ac[1] <= 2.5 + 0.01


def test_concave_room_door_goes_to_the_wall_piece_nearest_to_the_model_point():
    notch = [[0, 0], [150, 0], [150, 100], [100, 100], [100, 40], [50, 40], [50, 100], [0, 100]]
    rooms = [ExtractedRoom("a", notch), ExtractedRoom("b", rect(50, 40, 100, 100))]
    openings, _ = convert(rooms, [ExtractedDoor(("a", "b"), [104, 80], width_px=18)])
    assert openings[0]["position"] == pytest.approx([5.0, 1.0], abs=0.02)
    openings, _ = convert(rooms, [ExtractedDoor(("a", "b"), [46, 80], width_px=18)])
    assert openings[0]["position"] == pytest.approx([2.5, 1.0], abs=0.02)


def test_entrance_snaps_to_the_exterior_wall_not_to_a_shared_one():
    rooms = two_rooms()
    openings, _ = convert(rooms, [ExtractedDoor(("b", "outside"), [104, 50], kind="entrance", width_px=18)])
    x, y = openings[0]["position"]
    assert min(abs(y), abs(y - 5.0)) < 0.01 and x > 5.0  # on the top or bottom wall of b, never on the wall to a


def test_entrance_keeps_the_nearest_exterior_wall_point():
    openings, _ = convert(two_rooms(), [ExtractedDoor(("a", "outside"), [-4, 30], kind="entrance", width_px=18)])
    assert openings[0]["position"] == pytest.approx([0.0, 3.5], abs=0.01)
