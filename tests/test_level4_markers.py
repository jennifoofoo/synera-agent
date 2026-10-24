"""Marker detection and merge, offline. Synthetic plans drawn with PIL plus a regression on real dev images."""

import math

import numpy as np
import pytest
from PIL import Image, ImageDraw

from building_agent.level4.markers import (
    DOOR_RGB,
    ENTRANCE_RGB,
    OPENING_RGB,
    Marker,
    Markers,
    detect_markers,
    merge_markers,
)
from building_agent.level4.schema import ExtractedDoor, ExtractedRoom, Extraction
from tests.marker_helpers import DATA_DEV, drawn_markers, score

ROOM_FILL = (243, 239, 230)
GREEN_FILL = (207, 232, 196)
WALL = (83, 82, 82)
SIZE = (400, 300)
DOORS = [(100, 60), (200, 150), (300, 90), (60, 200), (250, 240), (340, 200)]
OPENINGS = [(150, 100), (120, 250), (320, 40)]
ENTRANCES = [(20, 60), (380, 150)]


def draw_plan(supersample: int = 1, noise: float = 0.0, seed: int = 0, markers: bool = True) -> Image.Image:
    """Two coloured rooms with wall lines, kit-coloured dots and red triangles. supersample > 1 gives soft edges."""
    k = supersample
    image = Image.new("RGB", (SIZE[0] * k, SIZE[1] * k), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([10 * k, 10 * k, 200 * k, 280 * k], fill=ROOM_FILL, outline=WALL, width=k)
    draw.rectangle([200 * k, 10 * k, 390 * k, 280 * k], fill=GREEN_FILL, outline=WALL, width=k)
    if markers:
        for x, y in DOORS:
            draw.ellipse([(x - 2.6) * k, (y - 2.6) * k, (x + 2.6) * k, (y + 2.6) * k], fill=DOOR_RGB)
        for x, y in OPENINGS:
            draw.ellipse([(x - 2.6) * k, (y - 2.6) * k, (x + 2.6) * k, (y + 2.6) * k], fill=OPENING_RGB)
        for x, y in ENTRANCES:
            draw.polygon(
                [(x * k, (y - 5) * k), ((x - 5) * k, (y + 5) * k), ((x + 5) * k, (y + 5) * k)], fill=ENTRANCE_RGB
            )
    if k > 1:
        image = image.resize(SIZE, Image.BOX)
    if noise:
        rng = np.random.default_rng(seed)
        data = np.array(image).astype(float) + rng.normal(0, noise, (SIZE[1], SIZE[0], 3))
        image = Image.fromarray(np.clip(data, 0, 255).astype("uint8"))
    return image


def detect(image: Image.Image, tmp_path) -> Markers:
    path = tmp_path / "plan.png"
    image.save(path)
    return detect_markers(path)


def assert_found(found: list[Marker], expected: list[tuple[float, float]], tolerance: float = 1.5) -> None:
    assert len(found) == len(expected)
    for x, y in expected:
        assert any(math.hypot(m.x - x, m.y - y) <= tolerance for m in found), (x, y)


def test_hard_edged_plan_is_found_completely(tmp_path):
    found = detect(draw_plan(), tmp_path)
    assert_found(found.doors, DOORS)
    assert_found(found.openings, OPENINGS)
    assert_found(found.entrances, ENTRANCES, tolerance=2.0)
    assert all(0.5 <= marker.confidence <= 1.0 for marker in found.doors)
    assert all(4 <= marker.size_px <= 7 for marker in found.doors)


def test_anti_aliased_plan(tmp_path):
    found = detect(draw_plan(supersample=4), tmp_path)
    assert_found(found.doors, DOORS)
    assert_found(found.openings, OPENINGS)
    assert_found(found.entrances, ENTRANCES, tolerance=2.0)


def test_noisy_plan(tmp_path):
    found = detect(draw_plan(supersample=4, noise=2.0), tmp_path)
    assert_found(found.doors, DOORS)
    assert_found(found.openings, OPENINGS)
    assert_found(found.entrances, ENTRANCES, tolerance=2.0)


def test_plan_without_markers_has_none(tmp_path):
    found = detect(draw_plan(markers=False), tmp_path)
    assert len(found) == 0


def test_same_colour_pixels_of_wrong_size_are_ignored(tmp_path):
    image = draw_plan(markers=False)
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 120, 80, 170], fill=DOOR_RGB)  # a furniture-sized brown block
    draw.rectangle([300, 120, 330, 130], fill=OPENING_RGB)  # a grey bar
    draw.line([(30, 20), (180, 20)], fill=OPENING_RGB, width=1)  # a thin grey line, like an anti-aliased wall
    draw.line([(30, 270), (180, 270)], fill=DOOR_RGB, width=2)  # a thin brown line
    draw.point([(150, 150), (151, 150)], fill=ENTRANCE_RGB)  # a speck of red
    draw.rectangle([250, 200, 275, 225], fill=ENTRANCE_RGB)  # a red block
    assert len(detect(image, tmp_path)) == 0


def test_room_fill_colours_are_not_markers(tmp_path):
    image = Image.new("RGB", SIZE, "white")
    draw = ImageDraw.Draw(image)
    for index, fill in enumerate([(244, 177, 131), (180, 167, 214), (255, 242, 179), (220, 220, 220), (127, 106, 79)]):
        draw.rectangle([20 + index * 70, 20, 70 + index * 70, 70], fill=fill)
    assert len(detect(image, tmp_path)) == 0


def test_touching_dots_are_counted_separately(tmp_path):
    image = draw_plan(markers=False)
    draw = ImageDraw.Draw(image)
    for x in (100, 105):
        draw.ellipse([x - 2.6, 60 - 2.6, x + 2.6, 60 + 2.6], fill=DOOR_RGB)
    found = detect(image, tmp_path)
    assert len(found.doors) == 2


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        detect_markers(tmp_path / "nope.png")


def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def two_rooms(*doors: ExtractedDoor) -> Extraction:
    rooms = [ExtractedRoom("a", rect(0, 0, 100, 100)), ExtractedRoom("b", rect(100, 0, 200, 100))]
    return Extraction(200, 100, rooms, list(doors))


def marker(x: float, y: float) -> Marker:
    return Marker(x, y, 5.2, 1.0)


def test_merge_marker_equal_to_model_door_keeps_one_door_at_marker_position():
    extraction = two_rooms(ExtractedDoor(("a", "b"), [102, 48], "door", width_px=9.0))
    merged, warnings = merge_markers(extraction, Markers(doors=[marker(100, 50)]))
    assert len(merged.doors) == 1
    door = merged.doors[0]
    assert door.position_px == [100, 50] and set(door.rooms) == {"a", "b"} and door.width_px == 9.0
    assert warnings == []


def test_merge_marker_only_adds_a_door_without_width():
    merged, warnings = merge_markers(two_rooms(), Markers(openings=[marker(101, 30)]))
    assert len(merged.doors) == 1
    assert set(merged.doors[0].rooms) == {"a", "b"} and merged.doors[0].kind == "opening"
    assert merged.doors[0].width_px is None and warnings == []


def test_merge_model_door_only_is_kept():
    door = ExtractedDoor(("a", "b"), [100, 80], "door", width_px=9.0)
    merged, _ = merge_markers(two_rooms(door), Markers(doors=[marker(100, 20)]))
    assert door in merged.doors and len(merged.doors) == 2


def test_merge_marker_near_three_rooms_takes_the_touching_pair_and_warns():
    rooms = [
        ExtractedRoom("a", rect(0, 0, 100, 100)),
        ExtractedRoom("b", rect(100, 0, 200, 100)),
        ExtractedRoom("c", rect(100, 106, 200, 200)),  # 6 px below b, not touching a
    ]
    extraction = Extraction(200, 200, rooms, [])
    merged, warnings = merge_markers(extraction, Markers(doors=[marker(100, 99)]))
    assert len(merged.doors) == 1 and set(merged.doors[0].rooms) == {"a", "b"}
    assert any("near 3 rooms" in warning for warning in warnings)


def test_merge_marker_off_walls_is_dropped_with_warning():
    merged, warnings = merge_markers(two_rooms(), Markers(doors=[marker(50, 50)]))
    assert merged.doors == [] and len(warnings) == 1 and "Dropped" in warnings[0]


def test_merge_disagreement_prefers_the_outline_pair_and_says_so():
    rooms = [
        ExtractedRoom("a", rect(0, 0, 100, 100)),
        ExtractedRoom("b", rect(100, 0, 200, 100)),
        ExtractedRoom("c", rect(0, 150, 100, 250)),
    ]
    extraction = Extraction(200, 250, rooms, [ExtractedDoor(("a", "c"), [101, 50], "door")])
    merged, warnings = merge_markers(extraction, Markers(doors=[marker(100, 50)]))
    assert len(merged.doors) == 1 and set(merged.doors[0].rooms) == {"a", "b"}
    assert len(warnings) == 1 and "outline" in warnings[0]


def test_merge_marker_colour_fixes_the_kind():
    extraction = two_rooms(ExtractedDoor(("a", "b"), [100, 50], "door"))
    merged, warnings = merge_markers(extraction, Markers(openings=[marker(100, 50)]))
    assert merged.doors[0].kind == "opening" and len(warnings) == 1


def test_merge_entrance_on_outer_wall_joins_room_and_outside():
    merged, warnings = merge_markers(two_rooms(), Markers(entrances=[marker(0, 50)]))
    assert merged.doors[0].kind == "entrance" and set(merged.doors[0].rooms) == {"a", "outside"} and warnings == []


def test_merge_entrance_between_two_rooms_or_floating_is_dropped():
    merged, warnings = merge_markers(two_rooms(), Markers(entrances=[marker(100, 50), marker(300, 50)]))
    assert merged.doors == [] and len(warnings) == 2


def test_merge_survives_broken_polygons():
    rooms = [ExtractedRoom("a", [[0, 0], [1, 1]]), ExtractedRoom("b", rect(0, 0, 100, 100))]
    merged, warnings = merge_markers(Extraction(100, 100, rooms, []), Markers(doors=[marker(100, 50)]))
    assert merged.doors == [] and len(warnings) == 1


def test_merge_does_not_change_the_input():
    extraction = two_rooms(ExtractedDoor(("a", "b"), [102, 48], "door"))
    merge_markers(extraction, Markers(doors=[marker(100, 50)]))
    assert extraction.doors[0].position_px == [102, 48]


# Measured on the full dev set (117 floors): doors 0.98-1.00 recall, everything else 0.92-1.00, precision 1.00.
# The thresholds sit a little below the measured per-image numbers.
REAL = [
    ("proc-campus-dev-000", 0, 0.95),
    ("resplan-439", 0, 0.95),
    ("swiss-31", 0, 0.75),  # 3 of 20 doors lie under red entrance triangles
    ("osm-way27326387", 0, 0.95),
]


@pytest.mark.parametrize(("building_id", "level", "min_door_recall"), REAL)
def test_real_dev_images(building_id, level, min_door_recall):
    image = DATA_DEV / building_id / f"floor_{level}_plain.png"
    if not image.exists() or not (DATA_DEV / building_id / f"floor_{level}.svg").exists():
        pytest.skip(f"dev data for {building_id} is missing (run scripts/get_data.sh)")
    result = score(detect_markers(image), drawn_markers(building_id, level))
    assert result["door"]["recall"] >= min_door_recall
    for kind, numbers in result.items():
        assert numbers["precision"] >= 0.95, kind
        assert numbers["recall"] >= 0.9 or kind == "door", kind


def test_real_image_with_furniture_still_shows_markers():
    plain = DATA_DEV / "resplan-439" / "floor_0_plain.png"
    furnished = DATA_DEV / "resplan-439" / "floor_0.png"
    if not (plain.exists() and furnished.exists()):
        pytest.skip("dev data for resplan-439 is missing (run scripts/get_data.sh)")
    result = score(detect_markers(furnished), drawn_markers("resplan-439", 0))
    assert result["door"]["recall"] >= 0.9 and result["door"]["precision"] >= 0.95


def test_real_image_saved_as_jpeg_quality_95(tmp_path):
    source = DATA_DEV / "proc-factory-dev-003" / "floor_0_plain.png"
    if not source.exists():
        pytest.skip("dev data for proc-factory-dev-003 is missing (run scripts/get_data.sh)")
    path = tmp_path / "plan.jpg"
    Image.open(source).convert("RGB").save(path, quality=95)
    result = score(detect_markers(path), drawn_markers("proc-factory-dev-003", 0))
    # measured: door 1.00, entrance 1.00, opening 0.88 (grey is matched tightly); JPEG 80 and below fails
    assert result["door"]["recall"] >= 0.95 and result["entrance"]["recall"] >= 0.95
    assert result["opening"]["recall"] >= 0.8 and all(numbers["precision"] >= 0.95 for numbers in result.values())
