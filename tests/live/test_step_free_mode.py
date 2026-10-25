"""Live conversations for step-free mode (docs/specs/step-free-mode.md). Assert on tool calls and route results,
and only loosely on wording (a lift, metres, a comparison)."""

import json
import re
from functools import cache
from pathlib import Path

import pytest

from building_agent import routing
from starter_agent.building_map import BuildingMap, MapError
from tests.live.harness import Transcript, run_script

ROUTING = ("find_route", "give_directions")
COMPARISON = re.compile(
    r"normal|longer|shorter|than|compared|detour|extra|more|instead|länger|statt|normale|mehr", re.IGNORECASE
)
METRES = re.compile(r"\d+\s*(m\b|metres|meters|Meter)", re.IGNORECASE)


def connector_kinds(bm: BuildingMap, space_path: list[str]) -> set[str]:
    return {c["kind"] for c in bm.connectors.values() if set(c["space_ids"]) & set(space_path)}


@cache
def stairs_case() -> tuple[Path, str, str]:
    """Two uniquely named rooms, ground floor and level 1: normal route by stairs, step-free route by lift."""
    paths = sorted(Path("data/dev").glob("*/building.json"), key=lambda p: (not p.parent.name.startswith("proc-"), p))
    for path in paths:
        bm = BuildingMap.load(path.parent)
        names = [space["name"] for space in bm.spaces.values()]
        by_level = {floor["level"]: floor["id"] for floor in bm.floors.values()}
        if 0 not in by_level or 1 not in by_level:
            continue
        rooms = [s for s in bm.spaces.values() if s["type"] == "room" and names.count(s["name"]) == 1]
        for start in [s for s in rooms if s["floor_id"] == by_level[0]][:8]:
            for end in [s for s in rooms if s["floor_id"] == by_level[1]][:8]:
                try:
                    normal = routing.route(bm, start["id"], end["id"])
                    step_free = routing.route(bm, start["id"], end["id"], True)
                except MapError:
                    continue
                if "stairs" in connector_kinds(bm, normal.space_path) and connector_kinds(bm, step_free.space_path) == {
                    "lift"
                }:
                    return path.parent, start["name"], end["name"]
    pytest.skip("no dev building where the step-free route swaps stairs for a lift")


def routes(transcript: Transcript, turn: int) -> list[dict]:
    return [
        json.loads(call.result)
        for call in transcript.turns[turn].calls
        if call.name in ROUTING and not call.is_error and "length_m" in json.loads(call.result)
    ]


def step_free_calls(transcript: Transcript, turn: int) -> list[bool]:
    return [call.args.get("enabled") for call in transcript.turns[turn].called("set_step_free") if not call.is_error]


@pytest.mark.live
def test_wheelchair_turns_step_free_on_and_stairs_again_turns_it_off():
    path, start, end = stairs_case()
    question = f"How do I get from {start} to {end}?"
    transcript = run_script(path, ["I'm in a wheelchair.", question, "I can take stairs again.", question])
    assert step_free_calls(transcript, 0) == [True], transcript.replies()[0]

    on = routes(transcript, 1)
    assert on and all(result["step_free"] for result in on), transcript.turns[1].calls
    reply = transcript.replies()[1]
    assert re.search(r"lift|elevator", reply, re.IGNORECASE), reply
    assert METRES.search(reply) and COMPARISON.search(reply), reply

    assert step_free_calls(transcript, 2) == [False], transcript.replies()[2]
    off = routes(transcript, 3)
    assert off and not any(result["step_free"] for result in off), transcript.turns[3].calls
    assert off[-1]["length_m"] <= on[-1]["length_m"]


@pytest.mark.live
def test_rollator_in_german_turns_step_free_on():
    path, start, end = stairs_case()
    transcript = run_script(path, ["Ich bin mit dem Rollator unterwegs.", f"Wie komme ich von {start} zu {end}?"])
    assert step_free_calls(transcript, 0) == [True], transcript.replies()[0]
    found = routes(transcript, 1)
    assert found and all(result["step_free"] for result in found), transcript.turns[1].calls
    reply = transcript.replies()[1]
    assert re.search(r"aufzug|lift|fahrstuhl", reply, re.IGNORECASE), reply
    assert METRES.search(reply), reply


@pytest.mark.live
def test_benchmark_wheelchair_question_does_not_switch_the_mode():
    """A one-off question that mentions a wheelchair is not the person talking about themselves."""
    path, start, end = stairs_case()
    transcript = run_script(
        path, [f"What is the shortest wheelchair-accessible route length in metres from {start} to {end}? Answer:"]
    )
    assert not transcript.turns[0].called("set_step_free"), transcript.turns[0].calls
    assert any(result["step_free"] for result in routes(transcript, 0))
    assert transcript.replies()[0].strip().splitlines()[-1].startswith("Answer:")
