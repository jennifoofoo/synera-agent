import pytest

from building_agent.kinds.shared_walls_count import shared_walls_count
from tests.conftest import labelled_questions, load_map

CASES = labelled_questions("shared_walls_count")


@pytest.mark.parametrize("building_dir,question", CASES, ids=[case[1]["id"] for case in CASES])
def test_shared_walls_count_matches_expected(building_dir, question):
    expected = question["answer"]
    result = shared_walls_count(load_map(building_dir), **question["inputs"])
    assert result["count"] == expected["value"]
    assert len(result["space_ids"]) == result["count"]
