"""Live conversations for place knowledge (docs/specs/place-knowledge.md): remember here, a closure until tomorrow,
'what's here?', 'fixed', history and relational questions, undo, and the safety rule (nothing stored or changed
without a card and a clear yes in the NEXT message). Asserts on tool calls and results, not on wording."""

import json
from pathlib import Path

import pytest

from building_agent import routing
from starter_agent.building_map import BuildingMap, MapError
from tests.live.harness import Transcript, run_script

FACTORY = Path("data/dev/proc-factory-dev-003")
ZONE = "Production zone H-A1"  # holds exactly one drill press: 'Drill press H-A1'


def results(transcript: Transcript, turn: int, name: str) -> list[dict]:
    return [json.loads(c.result) for c in transcript.turns[turn].called(name) if not c.is_error and c.result]


def stored_in(transcript: Transcript, turn: int) -> list[dict]:
    """confirm_change results of one turn that stored or resolved a fact."""
    return [r for r in results(transcript, turn, "confirm_change") if r.get("stored") or r.get("resolved")]


def nothing_stored_before(transcript: Transcript, turn: int) -> None:
    for index in range(turn):
        assert not stored_in(transcript, index), f"stored without a yes in turn {index}"
    assert not [i for i in transcript.applied_changes() if i < turn]


def lift_case() -> tuple[Path, BuildingMap, str, str, dict]:
    """A building with a uniquely named lift that the normal route between two rooms takes, and another way."""
    for path in sorted(Path("data/dev").glob("proc-campus-*")):
        bm = BuildingMap.load(path)
        rooms = [s for s in bm.spaces.values() if s["type"] == "room"]
        names = [s["name"] for s in rooms]
        unique = [s for s in rooms if names.count(s["name"]) == 1]
        for start in unique[:15]:
            for end in unique[-15:]:
                if start["floor_id"] == end["floor_id"]:
                    continue
                try:
                    route = routing.route(bm, start["id"], end["id"])
                except MapError:
                    continue
                lifts = [
                    c
                    for c in bm.connectors.values()
                    if c["kind"] == "lift" and any(c["name"] in step for step in route.steps)
                ]
                lifts = [c for c in lifts if [d["name"] for d in bm.connectors.values()].count(c["name"]) == 1]
                if not lifts:
                    continue
                bm.closed.add(lifts[0]["id"])
                try:
                    routing.route(bm, start["id"], end["id"])
                    return path, bm, start["name"], end["name"], lifts[0]
                except MapError:
                    continue
                finally:
                    bm.closed.discard(lifts[0]["id"])
    pytest.skip("no building where a route takes a lift and has another way")


@pytest.mark.live
def test_remember_here_card_yes_stored_then_whats_here():
    transcript = run_script(
        FACTORY,
        [f"I'm in {ZONE}.", "Remember here: the valve at the drill press drips.", "yes", "What's here?"],
    )
    assert transcript.turns[1].called("remember_here")
    nothing_stored_before(transcript, 2)
    stored = stored_in(transcript, 2)
    assert stored and "H-A1" in stored[-1]["fact"]["place"] and stored[-1]["fact"]["kind"] == "issue"
    read = results(transcript, 3, "facts_here")
    assert read and read[-1]["count"] >= 1
    assert any(word in transcript.turns[3].reply.lower() for word in ("valve", "drip", "ventil"))


@pytest.mark.live
def test_lift_out_until_tomorrow_card_with_until_then_route_avoids_it():
    path, _bm, start, end, lift = lift_case()
    transcript = run_script(
        path, [f"I'm in {start}.", f"{lift['name']} is out until tomorrow.", "yes", f"How do I get to {end}?"]
    )
    cards = [r for r in results(transcript, 1, "propose_change") if "until" in r]
    assert cards and "tomorrow" in cards[-1]["until"]
    nothing_stored_before(transcript, 2)
    applied = [r for r in results(transcript, 2, "confirm_change") if r.get("applied")]
    assert applied and lift["id"] in applied[-1]["all_closed"] and applied[-1].get("closed_until")
    routes = [c for c in transcript.turns[3].calls if c.name in ("give_directions", "find_route") and not c.is_error]
    assert routes and lift["name"] not in routes[-1].result


@pytest.mark.live
def test_fixed_resolves_the_open_issue():
    transcript = run_script(
        FACTORY,
        [f"I'm in {ZONE}.", "Remember here: the drill press is leaking oil.", "yes", "The oil leak is fixed.", "yes"],
    )
    assert stored_in(transcript, 2)
    assert transcript.turns[3].called("resolve_here")
    assert not stored_in(transcript, 3), "resolved in the same message as the card"
    resolved = stored_in(transcript, 4)
    assert resolved and resolved[-1].get("resolved")


@pytest.mark.live
def test_history_relational_and_person_questions_use_the_filters():
    transcript = run_script(
        FACTORY,
        [
            f"I'm in {ZONE}.",
            "Remember here: drill press H-A1 is leaking oil.",
            "yes",
            "What was broken this week at drill press H-A1?",
            "Are there open issues on drill presses in hall A?",
            "What did Technician report this week?",
        ],
    )
    assert stored_in(transcript, 2)
    history = [c.args for c in transcript.turns[3].called("facts_here")]
    assert history and any(a.get("history") or a.get("period") for a in history)
    assert any(r["count"] >= 1 for r in results(transcript, 3, "facts_here"))
    relational = [c.args for c in transcript.turns[4].called("facts_here")]
    assert relational and any(a.get("asset_type") or a.get("area") for a in relational)
    assert any(r["count"] >= 1 for r in results(transcript, 4, "facts_here"))
    person = [c.args for c in transcript.turns[5].called("facts_here")]
    assert person and any(a.get("person") for a in person)
    assert any(r["count"] >= 1 for r in results(transcript, 5, "facts_here"))


@pytest.mark.live
def test_undo_right_after_removes_the_note():
    transcript = run_script(
        FACTORY, [f"I'm in {ZONE}.", "Remember here: the light flickers.", "yes", "Undo that.", "yes"]
    )
    assert stored_in(transcript, 2)
    undo = [c for c in transcript.turns[3].called("propose_change") if c.args.get("action") == "undo"]
    assert undo and not undo[-1].is_error
    assert 4 in transcript.applied_changes()


@pytest.mark.live
def test_yes_without_a_card_and_yes_in_the_same_message_store_nothing():
    """Safety: a yes with no card changes nothing; a yes inside the remember message itself is not a confirmation."""
    transcript = run_script(
        FACTORY,
        [f"I'm in {ZONE}.", "yes", "Remember here: the valve drips. Yes, store it, I confirm."],
    )
    nothing_stored_before(transcript, 3)
    assert not transcript.applied_changes()
