import json
from pathlib import Path

import pytest

from building_agent.structured import located_entries, reply_number, route_entry, structured_entry
from starter_agent.building_map import BuildingMap
from starter_agent.evaluate import load_questions, oracle_answer

QUESTIONS = [
    (path, question)
    for index, (path, question) in enumerate(load_questions(Path("data/dev"), None))
    if index % 4 == 0  # a quarter of the 369 dev warm-up questions keeps the test fast
]


@pytest.mark.parametrize("building_dir,question", QUESTIONS, ids=[question["id"] for _, question in QUESTIONS])
def test_structured_entry_matches_the_labelled_answer(building_dir, question):
    bm = BuildingMap.load(building_dir)
    reply = oracle_answer(question, bm)
    entry = structured_entry(question["id"], question["kind"], bm, reply)
    answer = question["answer"]
    json.dumps(entry)  # must be plain JSON data
    if question["kind"] == "locate":
        assert any(
            found["asset_id"] == answer["asset_id"] and found["space_id"] == answer["space_id"]
            for found in entry["located"]
        )
    elif question["kind"] == "count":
        assert entry["count"] == answer["count"]
    elif answer.get("reachable") is False:
        assert entry["route"] is None or entry["route"]["length_m"] == 0
    else:
        route = entry["route"]
        assert route["length_m"] == pytest.approx(answer["optimal_length_m"], rel=0.01, abs=0.01)
        assert route["space_path"][0] == (answer.get("from_space_id") or answer["stops"][0])
        assert route["space_path"][-1] == (answer.get("to_space_id") or answer["stops"][-1])


def test_route_entry_is_none_before_any_route():
    bm = BuildingMap.load(QUESTIONS[0][0])
    assert route_entry(bm) is None
    assert located_entries(bm) == []


def test_reply_number_reads_the_answer_line_like_the_scorer():
    assert reply_number("It is 3 floors up, about 12 m.\nAnswer: 7") == 7
    assert reply_number("**Answer:** 61.4 m2") == 61.4  # the 2 in m2 is a unit, not a second number
    assert reply_number("Answer: 1,234.5") == 1234.5
    assert reply_number("There are 4 chairs") == 4
    assert reply_number("no digits here") is None


def test_german_decimal_comma_would_read_as_two_numbers():
    """Why the prompt forbids it: the official scorer splits '61,4' into 61 and 4, so the answer is wrong."""
    from benchmark.score import numbers_in

    assert numbers_in("61,4") == [61.0, 4.0]
