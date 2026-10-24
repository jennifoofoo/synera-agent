"""Live campus conversations: across buildings, wheelchair, a closed walkway, connecting two buildings.

The campus tools are added to a normal Agent here (no change to agent.py or tools.py needed to run these).
Assertions are on tool calls and campus state, not wording. Transcripts are cached like in harness.py."""

import hashlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import pytest

import starter_agent.agent as starter_module
from building_agent import agent as agent_module
from building_agent.campus import entrances, load_maps, make_example_campus
from building_agent.campus_tools import CampusHolder
from tests.live.harness import LIVE_CACHE, LIVE_MODEL, Call, Transcript, Turn, calls_in

DATA = Path("data")
CAMPUS_A, FACTORY, RESPLAN = "proc-campus-dev-000", "proc-factory-dev-003", "resplan-439"

CAMPUS_RULES = agent_module.CAMPUS_RULES


def build_holder(connected: bool = True) -> CampusHolder:
    campus = make_example_campus(DATA)
    if not connected:
        campus.links.pop()
    maps, _ = load_maps(campus)
    return CampusHolder(campus, maps, path=Path("agent_output") / "live_scratch" / "campus.json", bm=maps[CAMPUS_A])


def unique_room(holder: CampusHolder, building_id: str, index: int = 0) -> str:
    """Name of a room that exists only once on the whole campus, so the person can say it without a building."""
    names = Counter(
        space["name"].lower() for bm in holder.maps.values() for space in bm.spaces.values() if bm is not None
    )
    bm = holder.maps[building_id]
    rooms = sorted(
        space["name"]
        for space in bm.spaces.values()
        if space["room_type"] != "corridor" and names[space["name"].lower()] == 1
    )
    return rooms[index]


def building_name(holder: CampusHolder, building_id: str) -> str:
    return holder.router.building_name(building_id)


def run_campus_script(user_turns: list[str], connected: bool = True) -> tuple[Transcript, list[dict]]:
    """(transcript, final links as dicts). Cached on disk by turns, model and prompt text."""
    raw = json.dumps([user_turns, connected, LIVE_MODEL, agent_module.CONVERSATION_RULES, CAMPUS_RULES])
    path = LIVE_CACHE / f"campus-{hashlib.sha256(raw.encode()).hexdigest()}.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        turns = [Turn(t["user"], t["reply"], [Call(**c) for c in t["calls"]]) for t in saved["turns"]]
        return Transcript(turns), saved["links"]
    holder = build_holder(connected)
    previous_model = starter_module.MODEL
    starter_module.MODEL = LIVE_MODEL
    try:
        agent = agent_module.Agent(holder.bm, Path("agent_output") / "live_scratch", campus=holder)
        turns = []
        for user_text in user_turns:
            seen = len(agent.messages)
            reply = agent.ask(user_text)
            turns.append(Turn(user_text, reply, calls_in(agent.messages[seen:])))
    finally:
        starter_module.MODEL = previous_model
    links = [{"id": link.id, "closed": link.closed, "length_m": link.length_m} for link in holder.campus.links]
    LIVE_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"turns": [asdict(turn) for turn in turns], "links": links}, ensure_ascii=False), encoding="utf-8"
    )
    return Transcript(turns), links


def ok_calls(turn: Turn, name: str) -> list[Call]:
    return [call for call in turn.called(name) if not call.is_error]


@pytest.mark.live
def test_across_buildings_gives_three_steps_then_next():
    holder = build_holder()
    start, goal = unique_room(holder, CAMPUS_A), unique_room(holder, FACTORY)
    transcript = run_campus_script(
        [
            f"I am in {start} in {building_name(holder, CAMPUS_A)}. How do I get to {goal} in {building_name(holder, FACTORY)}?",
            "weiter",
        ]
    )[0]
    first, second = transcript.turns
    routes = ok_calls(first, "campus_route")
    assert routes, "campus_route not used"
    assert not first.called("give_directions") and not first.called("find_route")
    result = json.loads(routes[0].result)
    assert result["buildings"] == [building_name(holder, CAMPUS_A), building_name(holder, FACTORY)]
    assert 0 < len(result["steps"]) <= 3 and result["links_used"]
    following = ok_calls(second, "next_steps")
    assert following, "next_steps not called after 'weiter'"
    more = json.loads(following[0].result)["steps"]
    assert more and len(more) <= 3 and not set(more) & set(result["steps"])


@pytest.mark.live
def test_wheelchair_across_three_buildings_is_step_free():
    holder = build_holder()
    start, goal = unique_room(holder, CAMPUS_A), unique_room(holder, RESPLAN)
    transcript = run_campus_script(
        [
            f"I use a wheelchair. How do I get from {start} ({building_name(holder, CAMPUS_A)}) to {goal} ({building_name(holder, RESPLAN)})?"
        ]
    )[0]
    routes = ok_calls(transcript.turns[0], "campus_route")
    assert routes, "campus_route not used"
    assert routes[-1].args.get("step_free") is True
    result = json.loads(routes[-1].result)
    assert result["step_free"] is True and len(result["buildings"]) == 3
    assert result["normal_route_length_m"] is not None


@pytest.mark.live
def test_closed_walkway_question_uses_link_what_changes_and_changes_nothing():
    holder = build_holder()
    transcript, links = run_campus_script(
        [
            (
                f"The covered walkway between {building_name(holder, CAMPUS_A)} and {building_name(holder, FACTORY)} "
                "might be closed next week. What changes for the campus?"
            )
        ]
    )
    turn = transcript.turns[0]
    asked = ok_calls(turn, "link_what_changes")
    assert asked, "link_what_changes not called"
    assert not turn.called("confirm_campus_change")
    assert all(not link["closed"] for link in links)


@pytest.mark.live
def test_connect_two_buildings_card_then_yes():
    holder = build_holder(connected=False)
    factory = holder.maps[FACTORY]
    rooms = Counter(item["room"] for item in entrances(factory))
    gate = next(item["room"] for item in entrances(factory) if rooms[item["room"]] == 1)
    transcript, links = run_campus_script(
        [
            (
                f"Connect {building_name(holder, FACTORY)} (the entrance at {gate}) with {building_name(holder, RESPLAN)} "
                "by a bridge of 40 m."
            ),
            "yes, do it",
        ],
        connected=False,
    )
    first, second = transcript.turns
    assert ok_calls(first, "connect_buildings"), "no card proposed"
    assert not first.called("confirm_campus_change")
    confirms = ok_calls(second, "confirm_campus_change")
    assert confirms and confirms[0].args.get("confirmed") is True
    assert json.loads(confirms[0].result)["applied"] is True
    assert [link["id"] for link in links] == ["L1", "L2"] and links[1]["length_m"] == 40
