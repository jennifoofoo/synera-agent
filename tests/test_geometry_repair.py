from shapely.geometry import Polygon

from building_agent.geometry import repaired, space_polygon
from tests.conftest import labelled_questions, load_map

BOWTIE = [(0, 0), (4, 4), (4, 0), (0, 4)]


def test_valid_polygon_is_returned_unchanged():
    square = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    assert repaired(square) is square


def test_self_intersecting_polygon_becomes_a_usable_polygon():
    fixed = repaired(Polygon(BOWTIE))
    assert fixed.is_valid and fixed.area > 0 and fixed.exterior is not None


def test_space_polygon_survives_a_broken_space_in_the_building():
    building_dir, question = labelled_questions("errand")[0]
    bm = load_map(building_dir)
    space_id = question["inputs"]["start"]
    original = bm.spaces[space_id]["polygon"]
    bm.spaces[space_id]["polygon"] = BOWTIE
    try:
        assert space_polygon(bm, space_id).is_valid
    finally:
        bm.spaces[space_id]["polygon"] = original
