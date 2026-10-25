"""Live conversations about events and room bookings (docs/specs/events.md) on the demo building, the Munich Urban
Colab, seeded with today's hackathon events (scripts/demo_events_seed.py). The clock is fixed at 10:30 today, so the
pitches are upcoming and the Project Room booking runs. Asserts on tool calls and results, plus the facts in the reply."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from building_agent import knowledge_tools
from scripts.demo_events_seed import seed_events
from tests.live.harness import Transcript, run_script

DEMO = Path("demo/buildings/plan-89323a15")


def demo_events(bm, store) -> None:
    seed_events(bm, store, knowledge_tools.now(), quiet=True)


@pytest.fixture(autouse=True)
def mid_morning(monkeypatch):
    moment = datetime.now(knowledge_tools.TZ).replace(hour=10, minute=30, second=0, microsecond=0)
    monkeypatch.setattr(knowledge_tools, "CLOCK", lambda: moment)


def found(transcript: Transcript, turn: int) -> list[dict]:
    calls = transcript.turns[turn].called("find_events")
    return [json.loads(call.result) for call in calls if not call.is_error and call.result]


@pytest.mark.live
def test_where_are_the_pitches_names_room_time_and_offers_the_way():
    transcript = run_script(DEMO, ["Where are the pitches?"], seed=demo_events)
    results = found(transcript, 0)
    assert results and any(e["title"] == "Pitches" for r in results for e in r["events"])
    reply = transcript.turns[0].reply
    assert "Auditorium" in reply and "14:00" in reply
    offered = transcript.turns[0].called("give_directions") or any(
        word in reply.lower() for word in ("guide", "show you the way", "way there", "directions", "take you", "route")
    )
    assert offered, reply


@pytest.mark.live
def test_project_room_is_not_free_at_ten():
    transcript = run_script(DEMO, ["Is the Project Room free at 10:00?"], seed=demo_events)
    results = found(transcript, 0)
    assert results and results[-1].get("free") is False
    reply = transcript.turns[0].reply
    assert "Synera" in reply


@pytest.mark.live
def test_german_code_freeze_time():
    transcript = run_script(DEMO, ["Wann ist der Code Freeze?"], seed=demo_events)
    results = found(transcript, 0)
    assert results and any(e["starts"] == "today 13:00" for r in results for e in r["events"])
    assert "13:00" in transcript.turns[0].reply or "13 Uhr" in transcript.turns[0].reply
