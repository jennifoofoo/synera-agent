import pytest

from building_agent.queries_routing import errand
from tests.conftest import labelled_questions, load_map

CASES = labelled_questions("errand")


@pytest.mark.parametrize("building_dir,question", CASES, ids=[case[1]["id"] for case in CASES])
def test_errand_matches_expected_length(building_dir, question):
    expected = question["answer"]
    result = errand(load_map(building_dir), **question["inputs"])
    tolerance = max(expected["absolute_tolerance"], expected["relative_tolerance"] * expected["value"])
    assert result["length_m"] == pytest.approx(expected["value"], abs=tolerance)
    assert result["via"] == expected["via"]
    assert result["target"] == expected["target"]
