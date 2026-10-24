"""Synera-style route scoring (building_agent/judge_score.py), offline."""

import json
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

import pytest

from building_agent import judge_score, routing
from building_agent.judge_score import FULL_MARKS, ROUTE_KINDS, score_route
from building_agent.structured import route_entry
from starter_agent.building_map import MapError
from tests.conftest import LABELLED_SPLITS, load_map

DATA = Path("data")
SMALL = "data/train/swiss-3355"
START, END = "swiss-3355-F1-S003", "swiss-3355-F2-S020"
SEED = 7
SAMPLE = 150
PER_BUILDING = 6
# routing.route runs on the kit model that computed the labels, so every labelled question gets full marks.
MIN_SHARE_FULL_MARKS = 1.0


def route_question(**answer) -> dict:
    return {"kind": answer.pop("kind", "route"), "answer": {"from_space_id": START, "to_space_id": END, **answer}}


def entry(path: list[str]) -> dict:
    return {"space_path": path}


def best_entry(step_free: bool = False, closed: str | None = None) -> dict:
    bm = load_map(SMALL)
    bm.closed = {closed} if closed else set()
    try:
        routing.route(bm, START, END, step_free)
        return route_entry(bm)
    finally:
        bm.closed = set()


def test_best_route_scores_one():
    result = score_route(load_map(SMALL), best_entry(), route_question())
    assert result.valid and result.score == pytest.approx(1.0)


def test_detour_scores_below_one():
    detour = best_entry(closed="swiss-3355-V01")
    result = score_route(load_map(SMALL), detour, route_question())
    assert result.valid and 0.5 < result.score < FULL_MARKS


def test_jump_between_unjoined_spaces_is_invalid():
    path = best_entry()["space_path"]
    result = score_route(load_map(SMALL), entry([path[0], *path[2:]]), route_question())
    assert not result.valid and result.score == 0.0


def test_wrong_end_is_invalid():
    path = best_entry()["space_path"]
    assert not score_route(load_map(SMALL), entry(path[:-1]), route_question()).valid


def test_stairs_break_step_free():
    question = route_question(kind="route_step_free")
    result = score_route(load_map(SMALL), best_entry(), question)
    assert not result.valid and result.score == 0.0


def test_closed_element_used_is_invalid():
    question = route_question(kind="route_with_closure", closed_element_id="swiss-3355-V01")
    result = score_route(load_map(SMALL), best_entry(), question)  # best route without closure climbs V01
    assert not result.valid
    assert score_route(load_map(SMALL), best_entry(closed="swiss-3355-V01"), question).score == pytest.approx(1.0)


def test_closed_space_is_invalid():
    path = best_entry()["space_path"]
    question = route_question(kind="route_with_closure", closed_element_id=path[2])
    assert not score_route(load_map(SMALL), entry(path), question).valid


def test_tour_order_checked():
    bm = load_map(SMALL)
    stops = ["swiss-3355-F0-S023", "swiss-3355-F2-S023", "swiss-3355-F2-S004"]
    question = {"kind": "tour", "answer": {"stops": stops}}
    bm.closed = set()
    routing.route(bm, stops[0], stops[-1], via=stops[1:-1])
    good = route_entry(bm)
    result = score_route(bm, good, question)
    assert result.valid and result.score > 0.9
    routing.route(bm, stops[0], stops[-1])
    skipped = route_entry(bm)
    assert not score_route(bm, {"space_path": [s for s in skipped["space_path"] if s != stops[1]]}, question).valid
    swapped = {"kind": "tour", "answer": {"stops": [stops[0], stops[2], stops[1]]}}
    assert not score_route(bm, good, swapped).valid


def test_unreachable_needs_no_route():
    question = route_question(reachable=False)
    bm = load_map(SMALL)
    assert score_route(bm, None, question).score == 1.0
    assert not score_route(bm, best_entry(), question).valid
    assert score_route(bm, None, route_question()).score == 0.0


def load_sample() -> list[tuple[str, dict]]:
    by_building: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for split in LABELLED_SPLITS:
        for path in sorted((DATA / split).glob("*/questions_basic.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                question = json.loads(line)
                if question["kind"] in ROUTE_KINDS:
                    by_building[question["building_id"]].append((str(path.parent), question))
    buildings = sorted(by_building)
    random.Random(SEED).shuffle(buildings)
    sample: list[tuple[str, dict]] = []
    for building in buildings:
        sample += by_building[building][:PER_BUILDING]
        if len(sample) >= SAMPLE:
            break
    return sample[:SAMPLE]


def agent_entry(directory: str, question: dict) -> dict | None:
    """What the agent would hand in: routing.route with the question's closure and constraints."""
    bm = load_map(directory)
    answer = question["answer"]
    bm.closed = {answer["closed_element_id"]} if answer.get("closed_element_id") else set()
    try:
        if question["kind"] == "tour":
            stops = answer["stops"]
            routing.route(bm, stops[0], stops[-1], via=stops[1:-1])
        else:
            routing.route(bm, answer["from_space_id"], answer["to_space_id"], question["kind"] == "route_step_free")
    except MapError:
        return None
    finally:
        bm.closed = set()
    return route_entry(bm)


def test_agreement_on_labelled_questions():
    sample = load_sample()
    assert len(sample) == SAMPLE
    started = time.time()
    results = []
    for directory, question in sample:
        results.append(score_route(load_map(directory), agent_entry(directory, question), question))
    share = sum(r.valid and r.score >= FULL_MARKS for r in results) / len(results)
    valid = sum(r.valid for r in results) / len(results)
    print(
        f"judge agreement n={len(results)} valid={valid:.3f} share>={FULL_MARKS}={share:.4f} "
        f"median={statistics.median(r.score for r in results):.3f} worst={min(r.score for r in results):.3f} "
        f"seconds={time.time() - started:.1f}"
    )
    assert valid == 1.0
    assert share >= MIN_SHARE_FULL_MARKS


def test_recomputed_best_matches_the_label():
    """The judge's own best length (used when a question has no label) agrees with the labelled optimum."""
    checked = 0
    for directory, question in load_sample():
        answer = question["answer"]
        if answer.get("reachable") is False or answer.get("legs") is None and question["kind"] == "tour":
            continue
        bm = load_map(directory)
        closed = {answer["closed_element_id"]} if answer.get("closed_element_id") else set()
        model = judge_score._model(bm, closed, question["kind"] == "route_step_free")
        stops = answer["stops"] if question["kind"] == "tour" else [answer["from_space_id"], answer["to_space_id"]]
        best = judge_score.best_length(model, stops)
        assert best == pytest.approx(answer["optimal_length_m"], rel=0.001, abs=0.02), question["id"]
        checked += 1
    assert checked >= 50


def test_route_through_the_outside_is_invalid():
    path = best_entry()["space_path"]
    assert not score_route(load_map(SMALL), entry([path[0], "outside", *path[1:]]), route_question()).valid
