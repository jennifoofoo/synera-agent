import pytest

from building_agent.find_space import find_space
from starter_agent.building_map import MapError
from tests.conftest import labelled_questions, load_map


def errand_start():
    building_dir, question = labelled_questions("errand")[0]
    return load_map(building_dir), question["inputs"]["start"]


def test_resolves_exact_id():
    bm, start = errand_start()
    assert find_space(bm, start)["match"]["id"] == start


def test_resolves_exact_name_on_its_floor():
    bm, start = errand_start()
    space = bm.spaces[start]
    level = bm.floors[space["floor_id"]]["level"]
    assert find_space(bm, space["name"], level)["match"]["id"] == start


def test_wrong_floor_is_not_a_match():
    bm, start = errand_start()
    space = bm.spaces[start]
    level = bm.floors[space["floor_id"]]["level"]
    with pytest.raises(MapError):
        find_space(bm, space["name"], level + 50)


def test_unknown_name_raises():
    bm, _ = errand_start()
    with pytest.raises(MapError):
        find_space(bm, "no such room anywhere")


def test_ambiguous_word_returns_candidates():
    bm, _ = errand_start()
    result = find_space(bm, "room")
    assert "match" not in result
    assert len(result["candidates"]) >= 1
