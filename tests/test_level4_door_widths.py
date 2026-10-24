from building_agent.level4 import door_widths
from building_agent.level4.door_widths import (
    DEFAULT_WIDTH_M,
    OPENING_WIDTH_M,
    WIDE_DOOR_WIDTH_M,
    apply_estimates,
    estimate,
    side_labels,
    table_key,
)

ROOM = {"id": "r", "type": "room", "room_type": "generic_room"}
OFFICE = {"id": "o", "type": "room", "room_type": "office"}
LAB = {"id": "l", "type": "room", "room_type": "lab"}
CORRIDOR = {"id": "c", "type": "corridor", "room_type": "corridor"}
STAIR = {"id": "s", "type": "stair", "room_type": "stairwell"}
TABLE = {table_key("door", "corridor", "office"): 0.9, table_key("door", "corridor", "lab"): 1.2}


def test_deterministic():
    first = estimate("door", [ROOM, CORRIDOR], TABLE)
    assert all(estimate("door", [ROOM, CORRIDOR], TABLE) == first for _ in range(5))


def test_unknown_kind_and_missing_sides_get_default():
    assert estimate("trapdoor", [ROOM, CORRIDOR], TABLE).width_m == DEFAULT_WIDTH_M
    assert estimate(None, [ROOM, CORRIDOR], TABLE).rule == "default"
    assert estimate("door", [], TABLE).width_m == DEFAULT_WIDTH_M
    assert estimate("door", [ROOM], TABLE).width_m == DEFAULT_WIDTH_M
    assert estimate("door", [{}, {}], TABLE).width_m == DEFAULT_WIDTH_M
    assert estimate("entrance", [ROOM, None], TABLE).width_m == DEFAULT_WIDTH_M


def test_room_types_use_the_table_only_when_both_are_specific():
    assert estimate("door", [CORRIDOR, LAB], TABLE).width_m == 1.2
    assert estimate("door", [LAB, CORRIDOR], TABLE).rule == "room_types"
    assert estimate("door", [CORRIDOR, ROOM], TABLE).rule == "default"  # generic room counts as unknown


def test_class_rule_without_table():
    assert estimate("opening", [ROOM, ROOM], {}).width_m == OPENING_WIDTH_M
    assert estimate("door", [STAIR, ROOM], {}).width_m == WIDE_DOOR_WIDTH_M
    assert estimate("door", [ROOM, CORRIDOR], {}).width_m == DEFAULT_WIDTH_M


def test_side_labels_outside_and_missing_room_type():
    assert side_labels(None) == ("outside", "outside")
    assert side_labels({"type": "room"}) == ("room", None)


def test_missing_table_file_is_an_empty_table(tmp_path):
    assert door_widths.load_table(tmp_path / "none.json") == {}


def test_apply_keeps_measured_widths_and_notes_the_rule():
    spaces = [ROOM | {"id": "a"}, ROOM | {"id": "b"}, STAIR | {"id": "st"}]
    openings = [
        {"id": "m", "kind": "door", "space_ids": ["a", "st"], "width_m": 1.05},
        {"id": "e", "kind": "door", "space_ids": ["a", "st"], "width_m": 0.9},
        {"id": "p", "kind": "door", "space_ids": ["a", "b"], "width_m": 0.9},
    ]
    notes: list[tuple[str, str]] = []
    apply_estimates(openings, spaces, {"e", "p"}, lambda code, item: notes.append((code, item)))
    assert [o["width_m"] for o in openings] == [1.05, WIDE_DOOR_WIDTH_M, 0.9]
    assert notes == [("door_widths_estimated", "1 by rule class")]
