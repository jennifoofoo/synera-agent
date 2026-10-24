"""Offline tests of the room segmentation: synthetic plans with exact expected polygons, matching cases, and
regression thresholds on real kit images (skipped when data/ is missing)."""

import math

import pytest
from PIL import Image, ImageDraw
from shapely.geometry import Polygon

from building_agent.level4.schema import ExtractedDoor, ExtractedRoom, Extraction
from building_agent.level4.segment import (
    NOISE_NOTE,
    SCAN_NOTE,
    check_region_count,
    match_to_extraction,
    segment_rooms,
)
from tests.level4_helpers import DATA_DEV
from tests.level4_segment_eval import measure_segment
from tests.level4_segment_truth import image_path, truth_in_image

BEIGE, GREY, GREEN = (243, 239, 230), (220, 220, 220), (207, 232, 196)
WALL, BROWN, RED = (69, 68, 68), (139, 69, 19), (211, 47, 47)


def plan(tmp_path, rooms, size=(300, 200), dots=(), text=(), triangles=()):
    """rooms: (box, fill); walls are drawn as 1 px outlines, as in the kit images."""
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for box, fill in rooms:
        draw.rectangle(box, fill=fill, outline=WALL)
    for x, y in dots:
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=BROWN)
    for x, y in triangles:
        draw.polygon([(x, y), (x + 6, y), (x + 3, y - 6)], fill=RED)
    for x, y in text:
        for k in range(4):
            draw.text((x + 6 * k, y), "08"[k % 2], fill=(20, 20, 20))
    path = tmp_path / "plan.png"
    image.save(path)
    return path


def areas(result):
    return sorted(round(region.shape.area) for region in result.regions)


def test_flat_rooms_exact_corners(tmp_path):
    result = segment_rooms(plan(tmp_path, [((20, 20, 100, 100), BEIGE), ((100, 20, 200, 100), GREY)]))
    assert len(result.regions) == 2
    beige = next(r for r in result.regions if r.colour_name == "beige")
    assert Polygon(beige.polygon).symmetric_difference(Polygon([(20, 20), (101, 20), (101, 101), (20, 101)])).area < 250
    assert len(beige.polygon) == 4
    assert not beige.touches_border


def test_same_colour_rooms_separated_by_wall(tmp_path):
    result = segment_rooms(plan(tmp_path, [((20, 20, 100, 100), BEIGE), ((100, 20, 180, 100), BEIGE)]))
    assert len(result.regions) == 2


def test_text_and_door_dots_do_not_split_or_punch_holes(tmp_path):
    path = plan(
        tmp_path, [((20, 20, 140, 120), BEIGE), ((140, 20, 240, 120), BEIGE)], dots=[(140, 60)], text=[(40, 60)]
    )
    result = segment_rooms(path)
    assert len(result.regions) == 2
    assert all(not region.holes for region in result.regions)
    assert all(len(region.polygon) == 4 for region in result.regions)
    assert abs(result.regions[0].shape.area - 120 * 100) < 600


def test_entrance_triangle_outside_is_not_a_room(tmp_path):
    result = segment_rooms(plan(tmp_path, [((20, 20, 100, 100), BEIGE)], triangles=[(60, 18)]))
    assert len(result.regions) == 1


def test_tiny_room_is_found(tmp_path):
    result = segment_rooms(plan(tmp_path, [((20, 20, 100, 100), BEIGE), ((130, 40, 146, 56), GREEN)]))
    assert len(result.regions) == 2
    assert min(areas(result)) > 180


def test_room_with_a_hole(tmp_path):
    image = Image.new("RGB", (200, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 180, 140), fill=BEIGE, outline=WALL)
    draw.rectangle((80, 60, 120, 100), fill=GREY, outline=WALL)  # a shaft of another type inside
    path = tmp_path / "hole.png"
    image.save(path)
    result = segment_rooms(path)
    beige = next(r for r in result.regions if r.colour_name == "beige")
    assert len(beige.holes) == 1
    assert len(result.regions) == 2


def test_rotated_plan(tmp_path):
    path = plan(tmp_path, [((60, 60, 200, 140), BEIGE), ((200, 60, 260, 140), GREY)], size=(320, 200))
    image = Image.open(path).rotate(20, expand=True, resample=Image.BICUBIC, fillcolor="white")
    rotated = tmp_path / "rotated.png"
    image.save(rotated)
    result = segment_rooms(rotated)
    assert len(result.regions) == 2
    big = max(result.regions, key=lambda r: r.area_px)
    assert abs(big.area_px - 141 * 81) < 0.08 * 141 * 81


def test_touches_border(tmp_path):
    result = segment_rooms(plan(tmp_path, [((0, 0, 100, 100), BEIGE)]))
    assert result.regions[0].touches_border


def test_non_plan_image_is_skipped(tmp_path):
    noise = Image.effect_noise((120, 120), 60).convert("RGB")
    path = tmp_path / "noise.png"
    noise.save(path)
    result = segment_rooms(path)
    extraction = Extraction(120, 120, [ExtractedRoom("r1", [[0, 0], [50, 0], [50, 50]])], [])
    same, warnings = match_to_extraction(extraction, result)
    assert same is extraction and warnings == [SCAN_NOTE]


def segmented(tmp_path):
    return segment_rooms(plan(tmp_path, [((20, 20, 100, 100), BEIGE), ((100, 20, 200, 100), GREY)]))


def room(room_id, box, **kwargs):
    x0, y0, x1, y1 = box
    return ExtractedRoom(room_id, [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], **kwargs)


def test_match_refines_polygons_and_keeps_doors(tmp_path):
    door = ExtractedDoor(("a", "b"), [100.0, 60.0])
    extraction = Extraction(
        300, 200, [room("a", (25, 25, 95, 95), ref="1"), room("b", (105, 25, 195, 95), ref="2")], [door]
    )
    result, warnings = match_to_extraction(extraction, segmented(tmp_path))
    assert warnings == []
    assert [r.id for r in result.rooms] == ["a", "b"]
    assert result.rooms[0].ref == "1"
    assert abs(Polygon(result.rooms[0].polygon_px).area - 81 * 81) < 200  # was 70 * 70
    assert result.doors == [door]


def test_match_model_lost_a_room(tmp_path):
    extraction = Extraction(300, 200, [room("a", (20, 20, 100, 100))], [])
    result, warnings = match_to_extraction(extraction, segmented(tmp_path))
    assert len(result.rooms) == 2
    added = result.rooms[1]
    assert added.type == "corridor" and added.id == "seg1"
    assert any(w.startswith("room_added_from_image") for w in warnings)


def test_match_model_merged_two_rooms(tmp_path):
    extraction = Extraction(300, 200, [room("a", (20, 20, 200, 100))], [])
    result, warnings = match_to_extraction(extraction, segmented(tmp_path))
    assert len(result.rooms) == 2
    assert Polygon(result.rooms[0].polygon_px).area > 7000  # the larger region
    assert sum(w.startswith("room_added_from_image") for w in warnings) == 1


def test_match_region_claimed_by_two_model_rooms(tmp_path):
    extraction = Extraction(
        300, 200, [room("a", (20, 20, 100, 100)), room("b", (30, 30, 60, 60)), room("c", (110, 30, 190, 90))], []
    )
    result, warnings = match_to_extraction(extraction, segmented(tmp_path))
    assert len(result.rooms) == 3
    assert any(w.startswith("room_region_shared") and "b" in w for w in warnings)
    assert result.rooms[1].polygon_px == extraction.rooms[1].polygon_px


def test_match_model_room_without_region_keeps_polygon(tmp_path):
    extraction = Extraction(300, 200, [room("a", (20, 20, 100, 100)), room("z", (210, 120, 290, 190))], [])
    result, warnings = match_to_extraction(extraction, segmented(tmp_path))
    assert any(w.startswith("room_without_region") and "z" in w for w in warnings)
    assert result.rooms[1].polygon_px == extraction.rooms[1].polygon_px


def test_match_no_regions(tmp_path):
    empty = segment_rooms(plan(tmp_path, []))
    extraction = Extraction(300, 200, [room("a", (20, 20, 100, 100))], [])
    same, warnings = match_to_extraction(extraction, empty)
    assert same is extraction and warnings[0].startswith("segmentation_skipped")


# (building, level, min recall, min IoU median, max regions merging two true rooms)
REAL = [
    ("swiss-31", 0, 0.99, 0.9, 0),
    ("osm-way27326387", 0, 0.99, 0.9, 0),
    ("resplan-439", 0, 1.0, 0.9, 0),
    ("proc-factory-dev-003", 0, 1.0, 0.95, 0),
]


@pytest.mark.parametrize(("building", "level", "recall", "iou", "merges"), REAL)
def test_real_images(building, level, recall, iou, merges):
    if not (DATA_DEV / building).exists():
        pytest.skip(f"kit data missing: {DATA_DEV / building} (run scripts/get_data.sh)")
    truth = truth_in_image(building, level)
    assert truth is not None, "floor svg does not line up with building.json"
    result = measure_segment(truth, segment_rooms(image_path(building, level)))
    ious = sorted(result["ious"])
    assert result["recall"] >= recall
    assert ious[len(ious) // 2] >= iou
    assert result["merges"] <= merges
    assert result["precision"] >= 0.95
    assert not math.isnan(result["seconds"]) and result["seconds"] < 5


def test_build_from_plan_runs_segmentation_before_markers(tmp_path, monkeypatch):
    from building_agent.level4 import tools as level4_tools
    from tests.test_level4_tools import Rig

    rig = Rig(tmp_path, monkeypatch)
    order = []

    def fake_match(extraction, segment):
        order.append("segment")
        return extraction, ["room_added_from_image: seg1 (beige, 99 px)"]

    def fake_merge(extraction, markers):
        order.append("markers")
        return extraction, ["door marker dropped"]

    monkeypatch.setattr(level4_tools, "segment_rooms", lambda path: "segmented")
    monkeypatch.setattr(level4_tools, "match_to_extraction", fake_match)
    monkeypatch.setattr(level4_tools, "detect_markers", lambda path: "markers")
    monkeypatch.setattr(level4_tools, "merge_markers", fake_merge)
    rig.build()
    assert order == ["segment", "markers"]
    assert rig.draft.marker_notes[0].startswith("room_added_from_image")
    assert "door marker dropped" in rig.draft.marker_notes


def test_build_from_plan_survives_unreadable_image(tmp_path, monkeypatch):
    from tests.test_level4_tools import Rig

    rig = Rig(tmp_path, monkeypatch)  # the uploaded file is not a real png
    rig.build()
    assert rig.draft.building["spaces"]


# ---------- scan guard ----------


def test_paper_tone_page_is_rejected(tmp_path):
    """A grey sheet with a few dark lines: the paper tone must not become one giant room."""
    image = Image.new("RGB", (300, 200), (236, 236, 236))
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, 280, 180], outline=(60, 60, 60), width=2)
    draw.line([150, 20, 150, 180], fill=(60, 60, 60), width=2)
    path = tmp_path / "paper.png"
    image.save(path)
    result = segment_rooms(path)
    assert not result.usable and result.regions == [] and result.reject_note == SCAN_NOTE


def test_one_palette_colour_over_the_whole_image_is_rejected(tmp_path):
    path = tmp_path / "flat.png"
    Image.new("RGB", (200, 200), (243, 239, 230)).save(path)
    assert segment_rooms(path).reject_note == SCAN_NOTE


def test_kit_style_plan_is_not_rejected(tmp_path):
    result = segment_rooms(
        plan(tmp_path, [([10, 10, 140, 190], (243, 239, 230)), ([150, 10, 290, 190], (220, 220, 220))])
    )
    assert result.usable and not result.reject_note and len(result.regions) == 2


def test_implausible_region_count_is_rejected(tmp_path):
    result = segment_rooms(plan(tmp_path, [([10 + 20 * i, 10, 25 + 20 * i, 190], (243, 239, 230)) for i in range(14)]))
    assert len(result.regions) == 14
    model = Extraction(300, 200, [ExtractedRoom("r1", [[0, 0], [50, 0], [50, 50]])] * 3, [])
    assert check_region_count(result, 3).reject_note  # 14 regions > max(12, 3 * 3)
    assert not check_region_count(result, 6).reject_note  # 14 <= 3 * 6
    assert not check_region_count(result, 0).reject_note  # the model found nothing: the regions are all we have
    same, warnings = match_to_extraction(model, check_region_count(result, 3))
    assert same is model and warnings == [NOISE_NOTE]
