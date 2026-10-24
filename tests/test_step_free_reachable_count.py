import pytest

from building_agent.kinds.step_free_reachable_count import step_free_reachable_count
from tests.conftest import labelled_questions, load_map

CASES = labelled_questions("step_free_reachable_count")


@pytest.mark.parametrize("building_dir,question", CASES, ids=[question["id"] for _, question in CASES])
def test_matches_labelled_answer(building_dir, question):
    result = step_free_reachable_count(load_map(building_dir), **question["inputs"])
    assert result["count"] == question["answer"]["value"]


def test_does_not_leave_the_element_closed():
    building_dir, question = CASES[0]
    bm = load_map(building_dir)
    before = set(bm.closed)
    step_free_reachable_count(bm, **question["inputs"])
    assert bm.closed == before
