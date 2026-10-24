"""Live interaction scripts 1 (vague), 2 (wrong room) and 3 (change of mind) from docs/specs/interaction-scripts.md."""

import re
from pathlib import Path

import pytest

from starter_agent.building_map import BuildingMap, MapError
from tests.live.harness import Call, Transcript, dev_building, effective_start, run_script

ROUTING = ("find_route", "give_directions")
SEARCHING = ("search_building", "find_space", "find_for_task")
COFFEE_WORDS = ("coffee", "kaffee")
ROOM_NUMBER = re.compile(r"-?\d+\.\d{2}")


def coffee_space_ids(bm: BuildingMap) -> set[str]:
    """Spaces that are a coffee machine's room or a kitchen/canteen: where coffee can plausibly be had."""
    ids = {
        asset["space_id"]
        for asset in bm.assets.values()
        if any(word in f"{asset['type']} {asset['name']}".lower() for word in COFFEE_WORDS)
        and "table" not in asset["type"]
    }
    return ids | {space["id"] for space in bm.spaces.values() if space["room_type"] in ("kitchen", "canteen")}


def coffee_asset_space_ids(bm: BuildingMap) -> set[str]:
    return {asset["space_id"] for asset in bm.assets.values() if asset["type"] == "coffee_machine"}


def building_with_one_coffee_machine() -> tuple[Path, BuildingMap]:
    for path in sorted(Path("data/dev").glob("resplan-*")):
        bm = BuildingMap.load(path)
        if len(coffee_asset_space_ids(bm)) == 1:
            return path, bm
    raise LookupError("no dev building with exactly one coffee machine")


def building_with_several_coffee_machines() -> tuple[Path, BuildingMap]:
    path = dev_building("proc-campus")
    bm = BuildingMap.load(path)
    assert len(coffee_asset_space_ids(bm)) > 1
    return path, bm


def unique_name_space(bm: BuildingMap, room_type: str, floor_level: int = 0, skip: int = 0) -> dict:
    """A space of one type on one floor whose name is unique, so the user can name it unambiguously."""
    names = [space["name"].lower() for space in bm.spaces.values()]
    matches = [
        space
        for space in bm.spaces.values()
        if space["room_type"] == room_type
        and bm.floors[space["floor_id"]]["level"] == floor_level
        and names.count(space["name"].lower()) == 1
    ]
    return sorted(matches, key=lambda space: space["id"])[skip]


def resolve(bm: BuildingMap, reference) -> str | None:
    """The space id a routing argument points to, or None if it points to nothing in this building."""
    if not isinstance(reference, str):
        return None
    try:
        return bm.resolve_space(reference)
    except MapError:
        return None


def routing_calls(transcript: Transcript) -> list[tuple[int, Call]]:
    return sorted((pair for name in ROUTING for pair in transcript.calls(name)), key=lambda pair: pair[0])


def first_index(transcript: Transcript, names: tuple[str, ...]) -> int | None:
    """Position of the first call to any of `names` in the flat call order, or None."""
    flat = [call.name for turn in transcript.turns for call in turn.calls]
    positions = [flat.index(name) for name in names if name in flat]
    return min(positions) if positions else None


def assert_searched_before_routing(transcript: Transcript) -> None:
    route_at = first_index(transcript, ROUTING)
    if route_at is None:
        return
    search_at = first_index(transcript, SEARCHING)
    assert search_at is not None and search_at < route_at, "routed before searching the building"


def assert_no_invented_places(bm: BuildingMap, transcript: Transcript) -> None:
    for index, call in routing_calls(transcript):
        if call.is_error:
            continue
        assert effective_start(bm, transcript, index, call) is not None, f"{call.name} has no valid start"
        assert resolve(bm, call.args.get("destination")) is not None, (
            f"{call.name} destination={call.args.get('destination')!r} is not in the building"
        )
        for place in call.args.get("via") or []:
            assert resolve(bm, place) is not None, f"via {place!r} is not in the building"


def asks_something(reply: str) -> bool:
    return "?" in reply


def known_room_numbers(bm: BuildingMap) -> set[str]:
    text = " ".join(f"{space['name']} {space.get('ref') or ''}" for space in bm.spaces.values())
    return set(ROOM_NUMBER.findall(text))


@pytest.mark.live
@pytest.mark.parametrize("pick", [building_with_one_coffee_machine, building_with_several_coffee_machines])
def test_script_1_vague_coffee_searches_then_routes_or_asks(pick):
    """Script 1 (vague): 'where can I get coffee' searches first, routes on a clear hit, asks briefly otherwise."""
    path, bm = pick()
    start = unique_name_space(
        bm, "office" if any(s["room_type"] == "office" for s in bm.spaces.values()) else "living_room"
    )
    plausible = coffee_space_ids(bm)
    transcript = run_script(path, [f"I'm in {start['name']}. Where can I get coffee around here?"])
    turn = transcript.turns[0]

    assert any(call.name in SEARCHING for call in turn.calls), "agent never searched"
    assert_searched_before_routing(transcript)
    assert_no_invented_places(bm, transcript)

    routed = [call for _, call in routing_calls(transcript) if not call.is_error]
    for call in routed:
        assert resolve(bm, call.args["destination"]) in plausible, "routed to a place that is not a coffee spot"
    if len(coffee_asset_space_ids(bm)) == 1:
        assert routed, "one clear coffee spot exists but the agent did not route"
    else:
        assert routed or asks_something(turn.reply), "neither routed nor asked which coffee spot"


@pytest.mark.live
def test_script_2_wrong_room_is_not_guessed():
    """Script 2 (wrong room): a room that does not exist is never routed to; similar real rooms are offered."""
    path = dev_building("proc-campus")
    bm = BuildingMap.load(path)
    start = unique_name_space(bm, "office")
    known = known_room_numbers(bm)
    missing = next(f"9.{number:02d}" for number in range(99, 0, -1) if f"9.{number:02d}" not in known)
    transcript = run_script(path, [f"I'm in {start['name']}. How do I get to room {missing}?"])
    turn = transcript.turns[0]

    for _, call in routing_calls(transcript):
        assert call.is_error, f"{call.name} succeeded for a room that does not exist: {call.args}"
        assert missing not in str(call.args) or call.is_error
    assert_no_invented_places(bm, transcript)

    mentioned = set(ROOM_NUMBER.findall(turn.reply)) - {missing}
    assert mentioned <= known, f"reply names rooms that do not exist: {sorted(mentioned - known)}"
    assert asks_something(turn.reply) or mentioned, "reply neither asks nor offers an existing room"


@pytest.mark.live
def test_script_3_change_of_mind_keeps_the_start():
    """Script 3 (change of mind): after 'actually B instead' the route starts where it did, ends at B, no new start question."""
    path = dev_building("proc-campus")
    bm = BuildingMap.load(path)
    start = unique_name_space(bm, "office")
    first = unique_name_space(bm, "meeting_room")
    second = unique_name_space(bm, "makerspace")
    for target in (first, second):
        bm.route(start["id"], target["id"])

    transcript = run_script(
        path,
        [
            f"I'm in {start['name']}. How do I get to {first['name']}?",
            f"Actually, I want to go to {second['name']} instead.",
        ],
    )
    assert_no_invented_places(bm, transcript)

    before = [call for index, call in routing_calls(transcript) if index == 0 and not call.is_error]
    after = [call for index, call in routing_calls(transcript) if index == 1 and not call.is_error]
    assert before and after, "expected a successful route in both turns"
    assert effective_start(bm, transcript, 0, before[-1]) == start["id"]
    for call in after:
        assert effective_start(bm, transcript, 1, call) == start["id"], "start changed after the change of mind"
    assert resolve(bm, after[-1].args["destination"]) == second["id"]

    asks_for_start = [
        sentence
        for sentence in re.split(r"(?<=[?.!])\s+", transcript.turns[1].reply)
        if sentence.endswith("?")
        and re.search(r"\b(where|start|located|currently|position)\b", sentence, re.IGNORECASE)
    ]
    assert not asks_for_start, f"asked for the start again: {asks_for_start}"
