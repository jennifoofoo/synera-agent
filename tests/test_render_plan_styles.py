"""Offline tests of the foreign-style plan renderer and the style eval metrics. No API."""

import numpy as np
import pytest
from PIL import Image
from shapely.geometry import Polygon

from building_agent.level4.convert import FloorInput, convert_floors_with_findings
from building_agent.level4.markers import detect_markers
from building_agent.level4.schema import Scale
from building_agent.level4.segment import match_to_extraction, segment_rooms
from scripts.level4_style_eval import perfect_extraction, score, true_width_m
from scripts.render_plan_styles import DATA_DEV, SCAN_ROTATION_DEG, STYLES, _rotation, render

BUILDING = "resplan-439"
CLEAN_STYLES = [s for s in STYLES if s != "scan"]


@pytest.fixture(scope="module")
def renders(tmp_path_factory):
    out = tmp_path_factory.mktemp("styles")
    return {s: render(DATA_DEV / BUILDING / "building.json", 0, s, out / f"{s}.png") for s in STYLES}


def test_all_styles_have_files_and_sizes(renders):
    for style, made in renders.items():
        with Image.open(made.path) as image:
            assert image.size == (made.width_px, made.height_px), style
    assert renders["scan"].path.suffix == ".jpg"
    assert renders["lowres"].width_px < 0.5 * renders["lines"].width_px
    assert renders["dims"].width_px > renders["lines"].width_px  # room for the dimension chains


def test_deterministic(renders, tmp_path):
    for style in ("scan", "hatched"):
        again = render(DATA_DEV / BUILDING / "building.json", 0, style, tmp_path / f"{style}.png")
        assert again.path.read_bytes() == renders[style].path.read_bytes()
        assert np.allclose(again.matrix, renders[style].matrix)


def test_truth_points_lie_inside_the_image(renders):
    for style, made in renders.items():
        for space in made.spaces:
            for x, y in space["polygon_px"]:
                assert 0 <= x <= made.width_px and 0 <= y <= made.height_px, style
        for opening in made.openings:
            x, y = opening["position_px"]
            assert 0 <= x <= made.width_px and 0 <= y <= made.height_px, style


def test_truth_transform_matches_the_drawing(renders):
    """Every true door position lies next to drawn wall ink."""
    made = renders["lines"]
    ink = np.asarray(Image.open(made.path).convert("L")) < 128
    on_wall = 0
    for opening in made.openings:
        x, y = (round(v) for v in opening["position_px"])
        near = ink[max(y - 90, 0) : y + 90, max(x - 90, 0) : x + 90]
        on_wall += int(near.any())
    assert on_wall == len(made.openings)


def test_room_polygon_scale_is_right(renders):
    made = renders["lines"]
    true = {s["id"]: Polygon(s["polygon"]).area for s in made.spaces}
    for space in made.spaces:
        assert Polygon(space["polygon_px"]).area == pytest.approx(true[space["id"]] * made.px_per_m**2, rel=1e-6)


def test_rotation_matrix_matches_pil():
    image = Image.new("L", (200, 100), 255)
    image.putpixel((150, 30), 0)
    rotated = image.rotate(SCAN_ROTATION_DEG, fillcolor=255)
    x, y = np.argwhere(np.asarray(rotated) < 128)[0][::-1]
    px = _rotation(SCAN_ROTATION_DEG, 200, 100) @ np.array([150.5, 30.5, 1.0])
    assert abs(px[0] - (x + 0.5)) < 1.5 and abs(px[1] - (y + 0.5)) < 1.5


@pytest.mark.parametrize("style", CLEAN_STYLES)
def test_line_styles_do_not_fool_segmentation_or_markers(renders, style):
    made = renders[style]
    segment = segment_rooms(made.path)
    assert not segment.usable or len(segment.regions) <= 2
    extraction = perfect_extraction(made)
    merged, notes = match_to_extraction(extraction, segment)
    assert merged.rooms == extraction.rooms
    assert any("segmentation_skipped" in note for note in notes)
    assert len(detect_markers(made.path)) == 0


def test_scan_does_not_fool_segmentation(renders):
    segment = segment_rooms(renders["scan"].path)
    assert not segment.usable or len(segment.regions) <= 2


def test_scan_is_rejected_with_a_plain_note_and_keeps_model_rooms(renders):
    made = renders["scan"]
    segment = segment_rooms(made.path)
    assert not segment.usable and segment.regions == [] and segment.reject_note
    extraction = perfect_extraction(made)
    merged, notes = match_to_extraction(extraction, segment)
    assert merged.rooms == extraction.rooms
    assert notes == [segment.reject_note] and "scan" in notes[0]


def test_scan_has_no_markers(renders):
    assert len(detect_markers(renders["scan"].path)) == 0


@pytest.mark.parametrize("style", ["lines", "lowres", "scan"])
def test_perfect_extraction_scores_one(renders, style):
    made = renders[style]
    extraction = perfect_extraction(made)
    xs = [x for room in extraction.rooms for x, _ in room.polygon_px]
    scale = Scale(true_width_m(made) / (max(xs) - min(xs)), "known_length", "test")
    building, _ = convert_floors_with_findings([FloorInput(0, extraction, scale)], "t", "t")
    result = score(made, extraction, building)
    assert result["recall"] == 1.0 and result["precision"] == 1.0 and result["door_recall"] == 1.0
    assert result["judge"]["full"] == result["judge"]["pairs"] > 0
    assert result["entrances"][0] == result["entrances"][1]


def test_dims_style_records_the_scale_bar(renders):
    length_px, length_m = renders["dims"].scale_bar
    assert length_px / length_m == pytest.approx(renders["dims"].px_per_m)
    assert renders["lines"].scale_bar is None
