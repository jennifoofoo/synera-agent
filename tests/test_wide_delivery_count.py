import pytest

from building_agent.kinds.wide_delivery_count import wide_delivery_count
from tests.conftest import labelled_questions, load_map

CASES = labelled_questions("wide_delivery_count")


@pytest.mark.parametrize("building_dir,question", CASES, ids=[case[1]["id"] for case in CASES])
def test_wide_delivery_count_matches_expected_count(building_dir, question):
    result = wide_delivery_count(load_map(building_dir), **question["inputs"])
    assert result["count"] == question["answer"]["value"]
    assert len(result["space_ids"]) == result["count"]
