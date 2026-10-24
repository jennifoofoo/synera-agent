import pytest

from building_agent.kinds.floor_area_total import floor_area_total
from tests.conftest import labelled_questions, load_map

CASES = labelled_questions("floor_area_total")


@pytest.mark.parametrize("building_dir,question", CASES, ids=[case[1]["id"] for case in CASES])
def test_floor_area_total_within_tolerance(building_dir, question):
    expected = question["answer"]
    result = floor_area_total(load_map(building_dir), **question["inputs"])
    tolerance = max(expected["absolute_tolerance"], expected["relative_tolerance"] * expected["value"])
    assert result["total_m2"] == pytest.approx(expected["value"], abs=tolerance)


@pytest.mark.parametrize("building_dir,question", CASES, ids=[case[1]["id"] for case in CASES])
def test_floor_area_total_exact(building_dir, question):
    result = floor_area_total(load_map(building_dir), **question["inputs"])
    assert result["total_m2"] == pytest.approx(question["answer"]["value"], abs=0.02)
