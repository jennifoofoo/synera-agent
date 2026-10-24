"""Live interaction scripts 4 (wheelchair), 5 (hands full) and 6 (facility manager). See docs/specs/interaction-scripts.md."""

import json
import re
from collections import Counter
from itertools import islice, product

import pytest

from building_agent import routing
from starter_agent.building_map import BuildingMap, MapError
from tests.live.harness import dev_building, run_script

ROUTE_TOOLS = ("find_route", "give_directions")
EFFECT_WORDS = re.compile(
    r"route|detour|longer|no effect|no change|unaffected|not affect|other lift|alternative|step-free|weg", re.IGNORECASE
)
LONGER_WORDS = re.compile(r"longer|detour|further|farther|extra|more than|extends|umweg|länger", re.IGNORECASE)


def rooms_by_floor(bm: BuildingMap) -> dict[str, list[str]]:
    """Real rooms with a unique name, grouped by floor id."""
    names = Counter(space["name"] for space in bm.spaces.values())
    found: dict[str, list[str]] = {}
    for space in bm.spaces.values():
        if space["room_type"] != "corridor" and names[space["name"]] == 1:
            found.setdefault(space["floor_id"], []).append(space["name"])
    return found


def cross_floor_pairs(bm: BuildingMap):
    by_floor = rooms_by_floor(bm)
    floor_ids = sorted(by_floor, key=lambda floor_id: bm.floors[floor_id]["level"])
    for low, high in product(floor_ids, floor_ids):
        if bm.floors[low]["level"] < bm.floors[high]["level"]:
            yield from product(by_floor[low][:6], by_floor[high][:6])


def route_lengths(building, start: str, destination: str) -> tuple[float, float | None]:
    """(plain length, step-free length or None if impossible), computed on a fresh map."""
    bm = BuildingMap.load(building)
    plain = routing.route(bm, start, destination).length_m  # the model the agent answers with
    try:
        return plain, routing.route(bm, start, destination, step_free=True).length_m
    except MapError:
        return plain, None


def wheelchair_case():
    """Building with a lift plus two rooms on different floors; prefer a pair where step-free is a detour."""
    building = dev_building("proc-")
    bm = BuildingMap.load(building)
    assert any(connector["kind"] == "lift" for connector in bm.connectors.values())
    feasible = []
    for start, destination in islice(cross_floor_pairs(bm), 60):
        plain, step_free = route_lengths(building, start, destination)
        if step_free is not None:
            feasible.append((start, destination, plain, step_free))
    detour = [case for case in feasible if case[3] > case[2] + 1]
    start, destination, plain, step_free = (detour or feasible)[0]
    return building, start, destination, plain, step_free


def long_route_case():
    """Two rooms whose directions have more than 3 steps."""
    building = dev_building("proc-")
    bm = BuildingMap.load(building)
    for start, destination in islice(cross_floor_pairs(bm), 60):
        if len(bm.route(start, destination).steps) > 3:
            return building, start, destination
    raise AssertionError("no route with more than 3 steps found")


def lift_case():
    building = dev_building("proc-")
    bm = BuildingMap.load(building)
    lifts = [c["name"] for c in bm.connectors.values() if c["kind"] == "lift"]
    assert lifts
    return building, lifts[0]


def step_lists(transcript, names=("give_directions", "next_steps", "repeat_steps")):
    return [(i, c.name, json.loads(c.result)["steps"]) for n in names for i, c in transcript.calls(n) if not c.is_error]


@pytest.mark.live
def test_script_4_wheelchair_gets_step_free_route_and_honest_reply():
    building, start, destination, plain, step_free = wheelchair_case()
    transcript = run_script(
        building,
        [f"I use a wheelchair. How do I get from {start} to {destination}?"],
    )
    routing = [call for call in transcript.turns[0].calls if call.name in ROUTE_TOOLS]
    assert routing, "no routing call"
    assert routing[0].args.get("step_free") is True
    reply = transcript.turns[0].reply
    assert step_free is not None
    if step_free > plain + 1:
        assert LONGER_WORDS.search(reply) or str(round(step_free)) in reply, f"detour not mentioned: {reply}"
    assert "Answer:" not in reply


@pytest.mark.live
def test_script_5_hands_full_gets_chunks_of_three_next_and_again():
    building, start, destination = long_route_case()
    transcript = run_script(
        building,
        [f"I'm carrying boxes, keep it short. How do I get from {start} to {destination}?", "next", "again"],
    )
    assert transcript.turns[0].called("give_directions"), "give_directions not used in turn 1"
    assert all(len(steps) <= 3 for _, _, steps in step_lists(transcript))
    first = json.loads(transcript.turns[0].called("give_directions")[0].result)["steps"]
    assert 0 < len(first) <= 3
    following = transcript.turns[1].called("next_steps")
    assert following, "next_steps not called after 'next'"
    second = json.loads(following[0].result)["steps"]
    assert second and not set(second) & set(first), "next_steps repeated or returned nothing"
    repeated = transcript.turns[2].called("repeat_steps")
    assert repeated, "repeat_steps not called after 'again'"
    assert json.loads(repeated[0].result)["steps"] == second
    assert not transcript.turns[2].called("next_steps")


@pytest.mark.live
def test_script_6_manager_change_needs_card_then_yes():
    building, lift = lift_case()
    transcript = run_script(building, [f"Please close {lift}, it is being serviced.", "yes, do it"])
    first, second = transcript.turns
    assert first.called("propose_change")
    assert not first.called("confirm_change")
    assert transcript.applied_changes() == [1]
    assert lift.lower() in first.reply.lower() and "?" in first.reply
    confirms = second.called("confirm_change")
    assert confirms and confirms[0].args.get("confirmed") is True
    assert EFFECT_WORDS.search(second.reply), f"no route effect mentioned: {second.reply}"


@pytest.mark.live
def test_script_6_manager_no_leaves_building_unchanged():
    building, lift = lift_case()
    transcript = run_script(building, [f"Please close {lift}, it is being serviced.", "no, leave it"])
    first, second = transcript.turns
    assert first.called("propose_change")
    assert not first.called("confirm_change")
    assert transcript.applied_changes() == []
    assert not any(call.args.get("confirmed") is True for call in second.called("confirm_change"))
