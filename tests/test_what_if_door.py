import pytest

from building_agent.kinds.what_if_door import what_if_door
from tests.conftest import labelled_questions, load_map

CASES = labelled_questions("what_if_door")


@pytest.mark.parametrize("building_dir,question", CASES, ids=[case[1]["id"] for case in CASES])
def test_what_if_door_matches_expected_count(building_dir, question):
    bm = load_map(building_dir)
    openings_before = len(bm.openings)
    result = what_if_door(bm, **question["inputs"])
    assert result["count"] == question["answer"]["value"]
    assert len(result["space_ids"]) == result["count"]
    assert len(bm.openings) == openings_before


def test_gap_between_wall_buffer_and_adjacency_does_not_crash():
    """swiss-1689: rooms 0.42 m apart count as adjacent but miss the 0.35 m wall buffer (was EmptyPartError)."""
    bm = load_map("data/dev/swiss-1689")
    result = what_if_door(bm, "swiss-1689-F-1-S029", "swiss-1689-F-1-S031", "swiss-1689-F-1", "swiss-1689-F3")
    assert "door_position" in result
