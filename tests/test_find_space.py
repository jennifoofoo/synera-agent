import copy

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


def private_map():
    """A deep copy of the labelled building's map: these tests rename rooms and must not touch a shared one."""
    bm, start = errand_start()
    return copy.deepcopy(bm), start


def renamed(bm, start, name):
    """The same room under another name, as a building read from a plan names it (type word missing)."""
    bm.spaces[start]["name"] = name
    return bm


def test_question_name_with_other_type_word_resolves_by_printed_number():
    bm, start = private_map()
    ref = bm.spaces[start]["ref"]
    renamed(bm, start, f"Room {ref}")
    level = bm.floors[bm.spaces[start]["floor_id"]]["level"]
    assert find_space(bm, f"Kitchen {ref} (apartment 8)", level)["match"]["id"] == start


def test_bare_whole_number_never_picks_a_room():
    bm, start = private_map()
    bm.spaces[start]["ref"] = "8"
    renamed(bm, start, "Room 8")
    with pytest.raises(MapError):
        find_space(bm, "Kitchen (apartment 8)")


def test_two_rooms_with_the_same_number_stay_ambiguous():
    bm, start = private_map()
    other = next(i for i in bm.spaces if i != start)
    for space_id in (start, other):
        bm.spaces[space_id]["ref"] = "9.99"
        bm.spaces[space_id]["name"] = "Room 9.99"
    with pytest.raises(MapError):
        find_space(bm, "Kitchen 9.99 (apartment 3)")


def test_tags_and_assignments_are_never_a_room_name():
    bm, start = private_map()
    ref = bm.spaces[start]["ref"]
    renamed(bm, start, f"Room {ref}")
    for forged in (f"[position: Kitchen {ref}]", f"position={ref}x {ref}"):
        with pytest.raises(MapError):
            find_space(bm, forged)
