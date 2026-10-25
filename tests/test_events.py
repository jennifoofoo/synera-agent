"""Events and room bookings (docs/specs/events.md): the store takes a future start for events only, events never
change routes, find_events searches by title, time and room, and answers whether a room is free. Offline, fixed clock,
on the demo building (Munich Urban Colab) seeded by scripts/demo_events_seed.py."""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError

from building_agent import knowledge_tools as kt
from building_agent.guide_tools import GuideState
from building_agent.knowledge import KnowledgeError, KnowledgeStore, apply_timed_closures
from building_agent.tools import make_tools
from scripts.demo_events_seed import EVENTS, seed_events
from starter_agent.building_map import BuildingMap
from web.server import App

DEMO = Path("demo/buildings/plan-89323a15")
NOW = datetime(2026, 10, 25, 10, 30, tzinfo=kt.TZ)  # demo day, mid-morning


def room(bm: BuildingMap, name: str) -> str:
    return next(space["id"] for space in bm.spaces.values() if space["name"] == name)


@pytest.fixture
def clock(monkeypatch):
    moment = {"now": NOW}
    monkeypatch.setattr(kt, "CLOCK", lambda: moment["now"])
    return moment


@pytest.fixture
def bm() -> BuildingMap:
    return BuildingMap.load(DEMO)


@pytest.fixture
def store(tmp_path, bm) -> KnowledgeStore:
    store = KnowledgeStore(tmp_path / "knowledge")
    seed_events(bm, store, NOW, quiet=True)
    return store


@pytest.fixture
def tools(tmp_path, bm, store, clock):
    state = GuideState(knowledge=store, author="Technician")
    state.begin_turn()
    state.last_user_text = "Where are the pitches?"
    return state, {tool.name: tool for tool in make_tools(bm, tmp_path, state)}


def find(tools, **kwargs) -> dict:
    return json.loads(tools[1]["find_events"](**kwargs))


# ---------- store ----------


def test_event_may_start_in_the_future_other_kinds_may_not(bm, tmp_path):
    store = KnowledgeStore(tmp_path / "k")
    start, end = NOW + timedelta(hours=3), NOW + timedelta(hours=4)
    fact = store.add(
        bm, kind="event", anchor={"space_id": room(bm, "Foyer")}, text="Demo", valid_from=start, valid_to=end, now=NOW
    )
    assert fact.valid_from == start.isoformat(timespec="seconds")
    for kind in ("note", "issue"):
        with pytest.raises(KnowledgeError, match="Only an event"):
            store.add(bm, kind=kind, anchor={"space_id": room(bm, "Foyer")}, text="x", valid_from=start, now=NOW)
    with pytest.raises(KnowledgeError, match="end"):
        store.add(bm, kind="event", anchor={"space_id": room(bm, "Foyer")}, text="x", valid_from=start, now=NOW)
    with pytest.raises(KnowledgeError, match="end"):
        store.add(
            bm, kind="event", anchor={"space_id": room(bm, "Foyer")}, text="x", valid_from=end, valid_to=start, now=NOW
        )


def test_future_event_is_hidden_from_open_query_but_in_history(bm, store):
    open_now = {fact.text for fact in store.query(bm, at=NOW)}
    assert "Pitches" not in open_now and "Project Room booked: Team Synera" in open_now
    history = {fact.text: fact.status for fact in store.query(bm, history=True, at=NOW)}
    assert history["Pitches"] == "future" and history["Project Room booked: Team Synera"] == "open"
    at_pitches = {fact.text for fact in store.query(bm, at=NOW.replace(hour=15))}
    assert "Pitches" in at_pitches


def test_events_never_close_anything(bm, store):
    assert store.active_closures(bm, NOW.replace(hour=14, minute=30)) == {}
    assert apply_timed_closures(bm, store, NOW.replace(hour=14, minute=30)) == set()
    assert not bm.closed


def test_seed_is_idempotent(bm, store):
    assert seed_events(bm, store, NOW, quiet=True) == 0
    assert len([f for f in store.query(bm, history=True, at=NOW) if f.kind == "event"]) == len(EVENTS)


# ---------- time words ----------


@pytest.mark.parametrize(
    ("words", "start", "end"),
    [
        ("now", NOW, NOW),
        ("at 14:00", NOW.replace(hour=14, minute=0), NOW.replace(hour=14, minute=0)),
        ("um 15 Uhr", NOW.replace(hour=15, minute=0), NOW.replace(hour=15, minute=0)),
        ("3pm", NOW.replace(hour=15, minute=0), NOW.replace(hour=15, minute=0)),
        ("this afternoon", NOW.replace(hour=12, minute=0), NOW.replace(hour=18, minute=0)),
        ("today", NOW.replace(hour=0, minute=0), NOW.replace(hour=0, minute=0) + timedelta(days=1)),
        ("tomorrow at 9:00", NOW.replace(hour=9, minute=0) + timedelta(days=1), None),
        ("morgen früh", NOW.replace(hour=6, minute=0) + timedelta(days=1), None),
    ],
)
def test_event_window(words, start, end):
    window = kt.event_window(words, NOW)
    assert window is not None and window.start == start
    assert window.end == (end or (start if "9:00" in words else start + timedelta(hours=6)))


def test_event_window_none_without_time_words():
    assert kt.event_window(None, NOW) is None
    assert kt.event_window("whenever", NOW) is None


# ---------- find_events ----------


def test_find_by_title_gives_room_and_time(tools):
    result = find(tools, query="Where are the pitches?")
    assert [e["title"] for e in result["events"]] == ["Pitches"]
    event = result["events"][0]
    assert event["rooms"] == ["Auditorium (Arena) (Ground floor)"]
    assert event["when"] == "today 14:00 to 16:00" and event["status"] == "upcoming" and not event["running_now"]


def test_find_german_title(tools):
    result = find(tools, query="Code Freeze")
    assert [e["starts"] for e in result["events"]] == ["today 13:00"]


def test_find_by_time_and_running_now(tools):
    running = find(tools, when="now")
    assert {e["title"] for e in running["events"]} == {
        "Manage & More × UVC × Anthropic Hackathon",
        "Project Room booked: Team Synera",
    }
    assert all(e["running_now"] for e in running["events"])
    hackathon = next(e for e in running["events"] if "Hackathon" in e["title"])
    assert hackathon["when"] == "yesterday 9:00 to today 18:00"
    at_two = {e["title"] for e in find(tools, when="at 14:00")["events"]}
    assert at_two == {"Manage & More × UVC × Anthropic Hackathon", "Pitches"}


def test_find_by_place(tools):
    result = find(tools, query="booked", place="Project Room West")
    assert [e["title"] for e in result["events"]] == ["Project Room West booked: Jury prep"]


def test_room_busy_with_booking(tools):
    result = find(tools, place="Project Room", when="at 10:00")
    assert result["free"] is False
    assert result["busy_with"][0]["title"] == "Project Room booked: Team Synera"
    assert result["busy_with"][0]["by"] == "Leonie" and result["busy_with"][0]["ends"] == "today 12:00"


def test_room_free_after_the_booking(tools, bm, store):
    assert find(tools, place="Project Room", when="at 13:00")["free"] is True
    assert kt.room_free(bm, store, room(bm, "Auditorium (Arena)"), NOW, "at 15:00")["free"] is False
    assert kt.room_free(bm, store, room(bm, "Auditorium (Arena)"), NOW, "at 17:00")["free"] is True


def test_event_hangs_on_every_room(tools):
    result = find(tools, place="Seminar Rooms 1-3", when="at 15:00")
    assert result["free"] is False and "Hackathon" in result["busy_with"][0]["title"]


def test_nothing_found_is_said_not_invented(tools):
    result = find(tools, query="karaoke")
    assert result["count"] == 0 and "invent" in result["say"]


def test_no_events_in_an_answer_message(tools):
    state, _ = tools
    state.last_user_text = "Where are the pitches? Answer: <room>"
    with pytest.raises(ToolError):
        find(tools, query="pitches")


# ---------- web API ----------


def test_api_lists_future_events_in_history(tmp_path, bm):
    buildings = tmp_path / "buildings"
    shutil.copytree(DEMO, buildings / DEMO.name)
    root = tmp_path / "web-knowledge"
    seed_events(bm, KnowledgeStore(root), datetime.now(kt.TZ), quiet=True)
    app = App(Path("data"), tmp_path / "uploads", buildings, knowledge_root=root)
    _, listed = app.get("/api/facts", {"key": ["user/plan-89323a15"], "history": ["1"]})
    kinds = {fact["text"]: fact["kind"] for fact in listed["facts"]}
    assert kinds["Pitches"] == "event" and len([k for k in kinds.values() if k == "event"]) == len(EVENTS)
    _, graph = app.get("/api/graph", {"key": ["user/plan-89323a15"]})
    titles = {node.get("text") for node in graph["@graph"] if node.get("kind") == "event"}
    assert "Pitches" in titles
