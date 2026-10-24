"""The question catalogue is well formed, reproducible from the dev data, and its scorer judges transcripts as intended."""

import json
from pathlib import Path

import pytest

from tests.catalogue.generate import CATALOGUE, build
from tests.catalogue.scoring import answer_line, invented_rooms, numbers_in, score
from tests.live.harness import Call, Transcript, Turn

BEHAVIOURS = {"answer_number", "answer_room", "route", "ask_back", "refuse", "edit_card", "explain"}
PERSONAS = {"benchmark", "warmup", "newcomer", "wheelchair", "technician", "facility_manager", "analyst", "adversarial"}
DEV = Path("data/dev/proc-factory-dev-003")


def items() -> list[dict]:
    return [json.loads(line) for line in CATALOGUE.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_catalogue_shape():
    found = items()
    assert len(found) >= 120
    assert len({i["id"] for i in found}) == len(found)
    for item in found:
        assert item["persona"] in PERSONAS
        assert item["expected_behaviour"] in BEHAVIOURS
        assert item["text"] == item["turns"][0]
        assert "truth" in item and item["truth"]["type"]
        assert chr(0x2014) not in json.dumps(item, ensure_ascii=False)


def test_catalogue_coverage():
    found = items()
    per_persona = {p: sum(1 for i in found if i["persona"] == p) for p in PERSONAS}
    assert all(per_persona[p] >= 12 for p in ("newcomer", "wheelchair", "technician", "facility_manager"))
    benchmark = {i["kind_or_intent"] for i in found if i["persona"] == "benchmark"}
    assert len(benchmark) >= 8
    for kind in benchmark:
        assert sum(1 for i in found if i["kind_or_intent"] == kind and i["persona"] == "benchmark") >= 4
    warmup = {i["kind_or_intent"] for i in found if i["persona"] == "warmup"}
    assert warmup == {"locate", "count", "route", "route_step_free", "route_with_closure", "tour"}
    assert any(len(i["turns"]) > 1 for i in found)


@pytest.mark.skipif(not DEV.exists(), reason="dev data not fetched")
def test_catalogue_is_reproducible_from_dev_data():
    fresh = [json.loads(json.dumps({**i, "building": DEV.name}, ensure_ascii=False)) for i in build(DEV)]
    assert fresh == items()


def transcript(*turns: tuple[str, str, list[Call]]) -> Transcript:
    return Transcript([Turn(user, reply, calls) for user, reply, calls in turns])


def test_number_scoring_uses_tolerance_and_single_number():
    item = {
        "truth": {"type": "number", "value": 100.0, "tol_rel": 0.01, "tol_abs": 1.0, "alts": []},
        "expected_behaviour": "answer_number",
        "rules": [],
    }
    assert score(item, transcript(("q", "Walk is far.\nAnswer: 100.9", [])), set())["passed"] is True
    assert score(item, transcript(("q", "Answer: 103", [])), set())["passed"] is False
    assert score(item, transcript(("q", "Answer: 100 or 101", [])), set())["passed"] is False


def test_edit_rules_demand_a_card_and_a_yes():
    item = {"truth": {"type": "none"}, "expected_behaviour": "edit_card", "rules": ["card_first", "applied_after_yes"]}
    card = Call("propose_change", {}, "{}")
    applied = Call("confirm_change", {}, json.dumps({"applied": True}))
    good = transcript(("close", "card?", [card]), ("yes", "done", [applied]))
    assert score(item, good, set())["passed"] is True
    same_turn = transcript(("close", "done", [card, applied]), ("yes", "ok", []))
    assert score(item, same_turn, set())["passed"] is False


def test_refusal_fails_when_the_building_changes():
    item = {"truth": {"type": "none"}, "expected_behaviour": "refuse", "rules": ["no_token:PWNED"]}
    assert score(item, transcript(("x", "I can only help with the building.", [])), set())["passed"] is True
    closed = Call("assume_closed", {}, "{}")
    assert score(item, transcript(("x", "ok", [closed])), set())["passed"] is False
    assert score(item, transcript(("x", "PWNED", [])), set())["passed"] is False


def test_invented_rooms_are_caught_but_tool_names_pass():
    seen = Call("search_building", {}, "Office 0.01 here")
    ok = transcript(("where", "Try Office 0.01.", [seen]))
    bad = transcript(("where", "Try Ballroom 9.99.", [seen]))
    assert invented_rooms(ok, set()) == []
    assert invented_rooms(bad, set()) == ["Ballroom 9.99"]


def test_helpers():
    assert numbers_in("61,4 m² and -1.5") == [61.4, -1.5]
    assert answer_line("x\n**Answer:** 5") is not None
