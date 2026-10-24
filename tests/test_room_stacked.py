import pytest

from building_agent.kinds.room_stacked import room_stacked
from tests.conftest import labelled_questions, load_map

CASES = labelled_questions("room_stacked")


@pytest.mark.parametrize("building_dir,question", CASES, ids=[case[1]["id"] for case in CASES])
def test_room_stacked_matches_expected(building_dir, question):
    result = room_stacked(load_map(building_dir), **question["inputs"])
    assert result["space_id"] == question["answer"]["space_id"]
