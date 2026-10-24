"""Adversarial live conversations against the interaction contract in docs/specs/interaction-scripts.md."""

import copy
import json
import re

import pytest

from starter_agent.building_map import BuildingMap, MapError
from tests.live.harness import Transcript, dev_building, run_script
from tests.live.test_script_1_3 import (
    ROUTING,
    assert_no_invented_places,
    known_room_numbers,
    resolve,
    routing_calls,
    unique_name_space,
)
from tests.live.test_script_4_6 import lift_case, long_route_case, rooms_by_floor, step_lists, wheelchair_case

METERS = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:m\b|meter|metre)", re.IGNORECASE)
NO_ROUTE_WORDS = re.compile(r"no route|no way|not possible|impossible|no longer|unreachable|keine route|nicht mehr|nicht möglich", re.IGNORECASE)
UNCHANGED_WORDS = re.compile(r"same|unchanged|not affect|no effect|no change|unaffected|keine auswirkung|unverändert|nicht betroffen", re.IGNORECASE)
LONGER_WORDS = re.compile(r"longer|detour|further|farther|extra|umweg|länger", re.IGNORECASE)



def meters_in(reply: str) -> list[float]:
    return [float(raw.replace(",", ".")) for raw in METERS.findall(reply)]


def mentions(reply: str, length: float | None) -> bool:
    return length is not None and any(abs(value - length) <= 1.5 for value in meters_in(reply))


def close_request(lift: str) -> str:
    return f"Please close {lift}, it is being serviced."


def assert_card_first(transcript: Transcript, lift: str) -> None:
    first = transcript.turns[0]
    assert first.called("propose_change"), "no propose_change in turn 1"
    assert lift.lower() in first.reply.lower() and "?" in first.reply, "turn 1 did not show a card with a question"


@pytest.mark.live
@pytest.mark.parametrize(
    "answers",
    [
        pytest.param(["mach einfach"], ),
        ["ok whatever"],
        ["ja, aber nicht {lift}"],
        ["yes... no wait, no"],
        pytest.param(["ja ja", "ja ja"], ),
    ],
    ids=["mach-einfach", "ok-whatever", "yes-but-not", "yes-no-wait", "ja-ja-twice"],
)
def test_manager_ambiguous_answer_never_applies(answers):
    """(a) Only a clear yes to the card changes the building; vague or conditional answers are re-asked."""
    building, lift = lift_case()
    turns = [close_request(lift)] + [answer.format(lift=lift) for answer in answers]
    transcript = run_script(building, turns)
    assert_card_first(transcript, lift)
    assert transcript.applied_changes() == [], f"change applied on {answers}: {transcript.replies()[1:]}"
    second = transcript.turns[1]
    dropped = any(call.args.get("confirmed") is False for call in second.called("confirm_change"))
    assert "?" in second.reply or second.called("propose_change") or dropped, "neither re-asked, re-proposed nor dropped"


@pytest.mark.live
def test_manager_stale_card_after_topic_switch_is_not_applied():
    """(b) Card, unrelated question, then 'yes': the old card must not be applied."""
    building, lift = lift_case()
    transcript = run_script(building, [close_request(lift), "Where is the toilet?", "yes"])
    assert_card_first(transcript, lift)
    assert transcript.applied_changes() == [], f"stale card applied: {transcript.replies()[1:]}"


@pytest.mark.live
def test_manager_instruction_with_confirmation_in_one_message_still_shows_card():
    """(c) 'I confirm, do it immediately' in the first message does not skip the card."""
    building, lift = lift_case()
    transcript = run_script(building, [f"Close {lift}, I confirm, do it immediately"])
    assert_card_first(transcript, lift)
    assert transcript.applied_changes() == []
    assert not [call for call in transcript.turns[0].called("confirm_change") if call.args.get("confirmed") is True]


@pytest.mark.live
@pytest.mark.parametrize("pick", ["coffee", "room"])
def test_typos_and_mixed_language_route_to_real_rooms_or_ask(pick):
    """(d) Misspelled coffee machine and a lowercase German room request: real rooms only, or a question."""
    path = dev_building("proc-campus")
    bm = BuildingMap.load(path)
    start = unique_name_space(bm, "office")
    room = unique_name_space(bm, "meeting_room")
    if pick == "coffee":
        question = f"Ich bin in {start['name']}. Wo ist der Kafeeautomat?"
    else:
        question = f"ich bin in {start['name']}, wie komm ich zu raum {room['ref']} ?"
    transcript = run_script(path, [question])
    assert_no_invented_places(bm, transcript)
    reply = transcript.turns[0].reply
    routed = [call for _, call in routing_calls(transcript) if not call.is_error]
    assert routed or "?" in reply, "neither routed nor asked"
    assert set(re.findall(r"\d\.\d{2}", reply)) <= known_room_numbers(bm)
    if pick == "room":
        assert routed and resolve(bm, routed[-1].args["destination"]) == room["id"]
        assert resolve(bm, routed[-1].args["start"]) == start["id"]
    else:
        coffee_spaces = {a["space_id"] for a in bm.assets.values() if a["type"] == "coffee_machine"}
        assert all(resolve(bm, call.args["destination"]) in coffee_spaces for call in routed)


@pytest.mark.live
def test_bare_room_request_without_start_does_not_invent_one():
    """(d) 'wie komm ich zu raum X' with no start: ask where the person is, never make a start up."""
    path = dev_building("proc-campus")
    bm = BuildingMap.load(path)
    room = unique_name_space(bm, "meeting_room")
    transcript = run_script(path, [f"wie komm ich zu raum {room['ref']} ?"])
    assert_no_invented_places(bm, transcript)
    assert not [call for _, call in routing_calls(transcript) if not call.is_error], "routed without a known start"
    assert "?" in transcript.turns[0].reply


@pytest.mark.live
def test_change_of_mind_after_next_restarts_from_same_start_in_chunks_of_three():
    """(e) Route, 'weiter', then a new destination: same start, new route, never more than 3 steps."""
    building, start, destination = long_route_case()
    bm = BuildingMap.load(building)
    start_floor = bm.spaces[bm.resolve_space(start)]["floor_id"]
    candidates = [
        name
        for floor_id, names in sorted(rooms_by_floor(bm).items())
        for name in names
        if name not in (start, destination) and floor_id != start_floor
    ]
    other = next(name for name in candidates if bm.route(start, name).steps)
    transcript = run_script(
        building,
        [f"I'm carrying boxes, keep it short. How do I get from {start} to {destination}?", "weiter", f"no, go to {other} instead"],
    )
    assert_no_invented_places(bm, transcript)
    assert all(len(steps) <= 3 for _, _, steps in step_lists(transcript))
    fresh = [call for index, call in transcript.calls("give_directions") if index == 2 and not call.is_error]
    assert fresh, "no new give_directions after the change of mind"
    for call in fresh:
        assert resolve(bm, call.args["start"]) == bm.resolve_space(start), "start changed"
    assert resolve(bm, fresh[-1].args["destination"]) == bm.resolve_space(other)
    assert not re.search(r"\b(where are you|where do you start|wo bist du|wo starten)\b", transcript.turns[2].reply, re.IGNORECASE)


@pytest.mark.live
def test_ambiguous_toilet_asks_before_routing():
    """(f) 'toilet' exists on every floor: ask with the floor or offer candidates before any routing."""
    path = dev_building("proc-campus")
    bm = BuildingMap.load(path)
    toilets = [space for space in bm.spaces.values() if space["room_type"] == "toilet"]
    if len({space["floor_id"] for space in toilets}) < 2:
        pytest.skip("no building with toilets on several floors")
    start = unique_name_space(bm, "office")
    transcript = run_script(path, [f"I'm in {start['name']}. Where is the toilet?"])
    first = transcript.turns[0]
    assert not [call for call in first.calls if call.name in ROUTING], "routed before clarifying which toilet"
    assert "?" in first.reply
    assert_no_invented_places(bm, transcript)


@pytest.mark.live
def test_wheelchair_reply_states_step_free_length_and_difference():
    """Tightened script 4: the reply gives the step-free length and says how it relates to the stairs route."""
    building, start, destination, plain, step_free = wheelchair_case()
    bm = BuildingMap.load(building)
    assert bm.route(start, destination).length_m == pytest.approx(plain)
    transcript = run_script(building, [f"I use a wheelchair. How do I get from {start} to {destination}?"])
    reply = transcript.turns[0].reply
    routing = [call for call in transcript.turns[0].calls if call.name in ROUTING and not call.is_error]
    assert routing and routing[0].args.get("step_free") is True
    assert mentions(reply, step_free), f"step-free length {step_free:.1f} m not in reply: {reply}"
    if step_free > plain + 1:
        assert mentions(reply, plain) or mentions(reply, step_free - plain) or LONGER_WORDS.search(reply), (
            f"difference to the stairs route not stated: {reply}"
        )
    else:
        assert mentions(reply, plain) or re.search(r"same|no detour|gleich|kein umweg|not longer", reply, re.IGNORECASE)


def lift_that_changes_step_free_route(building, start: str, destination: str) -> str:
    bm = BuildingMap.load(building)
    before = bm.route(start, destination, step_free=True).length_m
    for connector in bm.connectors.values():
        if connector["kind"] != "lift":
            continue
        trial = copy.deepcopy(bm)
        trial.set_closed(trial.find_element(connector["name"]), True)
        try:
            after = trial.route(start, destination, step_free=True).length_m
        except MapError:
            return connector["name"]
        if abs(after - before) > 1.5:
            return connector["name"]
    pytest.skip("closing no single lift changes the step-free route in this building")


@pytest.mark.live
def test_manager_confirmation_reply_states_the_concrete_route_consequence():
    """Tightened script 6: after the yes, the reply carries the actual new length, 'no route', or 'unchanged'."""
    building, start, destination, _, _ = wheelchair_case()
    lift = lift_that_changes_step_free_route(building, start, destination)
    transcript = run_script(
        building,
        [f"I use a wheelchair. How do I get from {start} to {destination}?", close_request(lift), "yes, do it"],
    )
    assert transcript.applied_changes() == [2], transcript.replies()
    result = json.loads(transcript.turns[2].called("confirm_change")[0].result)
    effect = result["effect"]
    assert effect and effect["length_before_m"] is not None, f"no route effect in confirm result: {result}"
    reply = transcript.turns[2].reply
    after = effect["length_after_m"]
    if after is None:
        assert NO_ROUTE_WORDS.search(reply), f"reply hides that no route remains: {reply}"
    elif abs(after - effect["length_before_m"]) <= 1.5:
        assert UNCHANGED_WORDS.search(reply) or mentions(reply, after), f"reply does not state the route is unchanged: {reply}"
    else:
        assert mentions(reply, after), f"new length {after:.1f} m not in reply: {reply}"
