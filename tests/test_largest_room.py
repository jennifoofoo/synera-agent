import pytest

from building_agent.kinds.largest_room import largest_room
from tests.conftest import labelled_questions, load_map

CASES = labelled_questions("largest_room")


@pytest.mark.parametrize("building_dir,question", CASES, ids=[case[1]["id"] for case in CASES])
def test_largest_room_matches_expected(building_dir, question):
    expected = question["answer"]
    result = largest_room(load_map(building_dir), **question["inputs"])
    assert result["space_id"] == expected["space_id"]
    area = expected["area"]
    tolerance = max(area["absolute_tolerance"], area["relative_tolerance"] * area["value"])
    assert result["area_m2"] == pytest.approx(area["value"], abs=tolerance)
