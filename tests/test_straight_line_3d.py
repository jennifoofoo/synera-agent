import pytest

from building_agent.kinds.straight_line_3d import straight_line_3d
from tests.conftest import labelled_questions, load_map

CASES = labelled_questions("straight_line_3d")


@pytest.mark.parametrize("building_dir,question", CASES, ids=[case[1]["id"] for case in CASES])
def test_straight_line_3d_matches_expected_distance(building_dir, question):
    expected = question["answer"]
    result = straight_line_3d(load_map(building_dir), **question["inputs"])
    tolerance = max(expected["absolute_tolerance"], expected["relative_tolerance"] * expected["value"])
    assert result["distance_m"] == pytest.approx(expected["value"], abs=tolerance)


@pytest.mark.parametrize("building_dir,question", CASES, ids=[case[1]["id"] for case in CASES])
def test_straight_line_3d_matches_closely(building_dir, question):
    # Confirms the rule itself (answers are rounded to 2 decimals), not just the 2% tolerance.
    result = straight_line_3d(load_map(building_dir), **question["inputs"])
    assert result["distance_m"] == pytest.approx(question["answer"]["value"], abs=0.011)
