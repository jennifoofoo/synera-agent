"""Place knowledge on the agent side (docs/specs/place-knowledge.md): which place is meant, note or issue, until when,
the card-and-yes guard for remember/resolve, query filters, timed closures, undo, and the walk note once per walk.
Offline, no API calls; the clock is fixed."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError

from building_agent import knowledge_tools as kt
from building_agent import routing
from building_agent import walk as walking
from building_agent.guide_tools import GuideState
from building_agent.knowledge import KnowledgeStore, apply_timed_closures
from building_agent.position import make_position
from building_agent.tools import make_tools
from starter_agent.building_map import BuildingMap, MapError

FACTORY = Path("data/dev/proc-factory-dev-003")
NOW = datetime(2026, 10, 25, 9, 0, tzinfo=kt.TZ)  # a Sunday morning


@pytest.fixture
def clock(monkeypatch):
    moment = {"now": NOW}
    monkeypatch.setattr(kt, "CLOCK", lambda: moment["now"])
    return moment


@pytest.fixture
def setup(tmp_path, clock):
    if not FACTORY.exists():
        pytest.skip("dev data missing")
    bm = BuildingMap.load(FACTORY)
    state = GuideState(knowledge=KnowledgeStore(tmp_path / "knowledge"), author="Technician A")
    tools = {tool.name: tool for tool in make_tools(bm, tmp_path, state)}
    return bm, state, tools


def say(state: GuideState, text: str) -> None:
    """One person message, as Agent.ask records it."""
    state.begin_turn()
    state.last_user_text = text


def call(tools, name, **kwargs) -> dict:
    return json.loads(tools[name](**kwargs))


def asset_named(bm: BuildingMap, name: str) -> dict:
    return next(asset for asset in bm.assets.values() if asset["name"] == name)


def lift(bm: BuildingMap) -> dict:
    return next(c for c in bm.connectors.values() if c["kind"] == "lift")


# ---------- time words ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Aufzug 1 ist bis morgen kaputt", datetime(2026, 10, 26, 18, 0, tzinfo=kt.TZ)),
        ("lift 1 is out until tomorrow", datetime(2026, 10, 26, 18, 0, tzinfo=kt.TZ)),
        ("gesperrt bis 14 Uhr", datetime(2026, 10, 25, 14, 0, tzinfo=kt.TZ)),
        ("closed for 2 hours", NOW + timedelta(hours=2)),
        ("für zwei Stunden zu", NOW + timedelta(hours=2)),
        ("bis Freitag gesperrt", datetime(2026, 10, 30, 18, 0, tzinfo=kt.TZ)),
        ("out until the end of the shift", datetime(2026, 10, 25, 18, 0, tzinfo=kt.TZ)),
    ],
)
def test_until_words_resolve_with_the_shift_end_rules(text, expected):
    found = kt.parse_until(text, NOW)
    assert found is not None and not found.unclear and found.at == expected


@pytest.mark.parametrize("text", ["out until next week", "bis später kaputt", "closed for a while"])
def test_unclear_until_is_asked_back(text):
    found = kt.parse_until(text, NOW)
    assert found is not None and found.unclear and found.at is None


def test_no_until_and_open_end():
    assert kt.parse_until("Lift 1 is broken", NOW) is None
    open_end = kt.parse_until("closed until further notice", NOW)
    assert open_end is not None and open_end.at is None and not open_end.unclear


def test_closure_time_allows_now_until_but_refuses_later():
    assert kt.closure_time("lift 1 is out until tomorrow", None, None, NOW).at == datetime(
        2026, 10, 26, 18, 0, tzinfo=kt.TZ
    )
    assert kt.closure_time("close lift 1 tomorrow", None, None, NOW).scheduled
    assert kt.closure_time("from Monday until Friday the lift is out", None, None, NOW).scheduled
    assert kt.closure_time("lift is broken", None, "next week", NOW).scheduled
    assert kt.closure_time("lift out until tomorrow", None, "until tomorrow", NOW).at is not None
    assert kt.closure_time("bis später zu", None, None, NOW).unclear
    plain = kt.closure_time("lift 1 is broken", None, None, NOW)
    assert not plain.scheduled and not plain.unclear and plain.at is None


def test_period_bounds():
    since, until = kt.period_bounds("this week", NOW)
    assert since == datetime(2026, 10, 19, 0, 0, tzinfo=kt.TZ) and until == NOW
    assert kt.period_bounds("heute", NOW)[0] == datetime(2026, 10, 25, 0, 0, tzinfo=kt.TZ)
    assert kt.period_bounds("whenever", NOW) is None


# ---------- note or issue ----------


@pytest.mark.parametrize("text", ["Ventil tropft", "valve leaks", "door is stuck", "Pumpe ist kaputt", "error 42"])
def test_problem_words_make_an_issue(text):
    assert kt.detect_kind(text) == "issue"
    assert kt.detect_kind(text, "note") == "issue"


@pytest.mark.parametrize("text", ["always use the left lever first", "Schlüssel liegt im Schrank"])
def test_knowledge_is_a_note(text):
    assert kt.detect_kind(text) == "note"
    assert kt.detect_kind(text, "issue") == "issue"  # the model may say it is a problem


# ---------- which place ----------


def test_anchor_here_needs_a_position(setup):
    bm, state, _ = setup
    with pytest.raises(kt.NeedsAnswer) as asked:
        kt.resolve_anchor(bm, state, "hier")
    assert asked.value.payload["where_are_you"]
    room = next(iter(bm.spaces))
    state.position = make_position(bm, room, None, "said", 0)
    for place in (None, "", "here", "hier"):
        assert kt.resolve_anchor(bm, state, place).space_id == room


def test_anchor_names_an_asset_a_lift_or_a_room(setup):
    bm, state, _ = setup
    press = asset_named(bm, "Drill press H-A1")
    found = kt.resolve_anchor(bm, state, "Drill press H-A1")
    assert found.asset_id == press["id"] and found.space_id == press["space_id"]
    assert kt.resolve_anchor(bm, state, press["id"]).asset_id == press["id"]
    the_lift = lift(bm)
    assert kt.resolve_anchor(bm, state, the_lift["name"]).element_id == the_lift["id"]
    room = kt.resolve_anchor(bm, state, "Kitchen 0.28")
    assert room.asset_id is None and bm.spaces[room.space_id]["name"] == "Kitchen 0.28"


def test_an_ambiguous_place_is_asked_never_guessed(setup):
    bm, state, _ = setup
    with pytest.raises(kt.NeedsAnswer) as asked:
        kt.resolve_anchor(bm, state, "drill press")
    assert asked.value.payload["needs_choice"] and "?" in asked.value.payload["question"]
    with pytest.raises(kt.NeedsAnswer):
        kt.resolve_anchor(bm, state, "Kitchen")


# ---------- the card guard for remember and resolve ----------


def remember_card(bm, state, tools, text="the valve drips"):
    say(state, f"remember here: {text}")
    return call(tools, "remember_here", text=text, place="Drill press H-A1")


def test_remember_needs_a_card_and_a_yes_in_the_next_message(setup):
    bm, state, tools = setup
    card = remember_card(bm, state, tools)
    assert "waiting" in card["status"] and "Drill press H-A1" in card["I understood"]
    assert "Problem" in card["I understood"] and not state.knowledge.query(bm, at=NOW)
    with pytest.raises(ToolError):  # same message: refused
        tools["confirm_change"](confirmed=True, user_reply="yes")
    say(state, "yes")
    done = call(tools, "confirm_change", confirmed=True, user_reply="yes")
    assert done["applied"] and done["stored"]
    facts = state.knowledge.query(bm, at=NOW)
    assert len(facts) == 1 and facts[0].kind == "issue" and facts[0].author == "Technician A"
    assert facts[0].anchor["asset_id"] == asset_named(bm, "Drill press H-A1")["id"]


@pytest.mark.parametrize("reply", ["ja ja", "whatever", "yes but not now", "where is the toilet?"])
def test_a_vague_yes_or_a_topic_change_stores_nothing(setup, reply):
    bm, state, tools = setup
    remember_card(bm, state, tools)
    say(state, reply)
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply=reply)
    assert state.pending is None and not state.knowledge.query(bm, at=NOW, history=True)


def test_a_stale_card_stores_nothing(setup):
    bm, state, tools = setup
    remember_card(bm, state, tools)
    say(state, "where is the kitchen?")
    say(state, "yes")
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="yes")
    assert not state.knowledge.query(bm, at=NOW, history=True)


def test_yes_without_any_card_changes_nothing(setup):
    bm, state, tools = setup
    say(state, "yes")
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="yes")
    assert not state.knowledge.query(bm, at=NOW, history=True) and not bm.closed


def test_propose_change_does_not_take_remember_or_resolve(setup):
    _bm, state, tools = setup
    say(state, "remember this")
    for action in ("remember", "resolve"):
        with pytest.raises(ToolError):
            tools["propose_change"](action=action, element="x")


def test_a_message_with_answer_never_remembers(setup):
    _bm, state, tools = setup
    say(state, "The valve at Drill press H-A1 drips. How far is it? Answer: <number>")
    with pytest.raises(ToolError):
        tools["remember_here"](text="valve drips", place="Drill press H-A1")
    assert state.pending is None


def test_resolve_has_the_same_guard_and_ends_the_fact(setup, clock):
    bm, state, tools = setup
    remember_card(bm, state, tools)
    say(state, "yes")
    call(tools, "confirm_change", confirmed=True, user_reply="yes")
    clock["now"] = NOW + timedelta(hours=3)
    say(state, "valve at drill press H-A1 is fixed")
    card = call(tools, "resolve_here", place="Drill press H-A1", text="valve fixed")
    assert "Mark as fixed" in card["I understood"] and "since 9:00" in card["I understood"]
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="yes")
    say(state, "whatever")
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="whatever")
    assert len(state.knowledge.query(bm, at=clock["now"])) == 1
    say(state, "fixed")
    call(tools, "resolve_here", place="Drill press H-A1", text="fixed")
    say(state, "ja")
    assert call(tools, "confirm_change", confirmed=True, user_reply="ja")["resolved"]
    assert not state.knowledge.query(bm, at=clock["now"])
    history = state.knowledge.query(bm, at=clock["now"], history=True)
    assert {fact.status for fact in history} == {"resolved"}


def test_resolve_with_nothing_open_says_so(setup):
    _bm, state, tools = setup
    say(state, "fixed")
    assert call(tools, "resolve_here", place="Drill press H-A1")["nothing_open"]
    assert state.pending is None


# ---------- timed closures ----------


def test_out_until_tomorrow_is_a_card_with_until_then_a_closure_that_ends(setup, clock):
    bm, state, tools = setup
    the_lift = lift(bm)
    say(state, f"{the_lift['name']} is out until tomorrow")
    card = call(tools, "propose_change", action="close", element=the_lift["id"], reason="broken")
    assert card["until"] == "until tomorrow 18:00" and "waiting" in card["status"]
    assert the_lift["id"] not in bm.closed
    say(state, "yes")
    done = call(tools, "confirm_change", confirmed=True, user_reply="yes")
    assert done["applied"] and the_lift["id"] in bm.closed and done["closed_until"].startswith("2026-10-26T18:00")
    shown = call(tools, "facts_here", closed_now=True)
    assert shown["count"] == 1 and shown["closed"][0]["until"] == "until tomorrow 18:00"
    apply_timed_closures(bm, state.knowledge, NOW + timedelta(hours=1))
    assert the_lift["id"] in bm.closed  # still within the window
    apply_timed_closures(bm, state.knowledge, datetime(2026, 10, 26, 18, 1, tzinfo=kt.TZ))
    assert the_lift["id"] not in bm.closed  # opens again by itself


def test_a_closure_for_later_is_still_refused(setup):
    bm, state, tools = setup
    say(state, "close the lift tomorrow")
    answer = call(tools, "propose_change", action="close", element=lift(bm)["id"])
    assert answer["scheduled"] is False and state.pending is None and not bm.closed


def test_an_unclear_until_is_asked(setup):
    bm, state, tools = setup
    say(state, "the lift is out until later")
    answer = call(tools, "propose_change", action="close", element=lift(bm)["id"])
    assert answer["needs_time"] and state.pending is None and not bm.closed


def test_reopen_ends_the_closure_fact(setup, clock):
    bm, state, tools = setup
    the_lift = lift(bm)
    say(state, "lift is out until tomorrow")
    call(tools, "propose_change", action="close", element=the_lift["id"])
    say(state, "yes")
    call(tools, "confirm_change", confirmed=True, user_reply="yes")
    say(state, "reopen the lift")
    call(tools, "propose_change", action="reopen", element=the_lift["id"])
    say(state, "yes")
    call(tools, "confirm_change", confirmed=True, user_reply="yes")
    apply_timed_closures(bm, state.knowledge, NOW + timedelta(minutes=5))
    assert the_lift["id"] not in bm.closed


def test_without_a_store_the_old_rule_stays(tmp_path):
    bm = BuildingMap.load(FACTORY)
    state = GuideState()
    tools = {tool.name: tool for tool in make_tools(bm, tmp_path, state)}
    assert not {"remember_here", "resolve_here", "facts_here"} & set(tools)
    say(state, "lift is out until tomorrow")
    assert call(tools, "propose_change", action="close", element=lift(bm)["id"])["scheduled"] is False


# ---------- undo ----------


def test_undo_right_after_removes_the_note_later_it_is_refused(setup, clock):
    bm, state, tools = setup
    remember_card(bm, state, tools)
    say(state, "yes")
    call(tools, "confirm_change", confirmed=True, user_reply="yes")
    say(state, "undo that")
    assert "remove the note" in call(tools, "propose_change", action="undo")["I understood"]
    say(state, "yes")
    call(tools, "confirm_change", confirmed=True, user_reply="yes")
    assert not state.knowledge.query(bm, at=NOW, history=True)
    remember_card(bm, state, tools)
    say(state, "yes")
    call(tools, "confirm_change", confirmed=True, user_reply="yes")
    clock["now"] = NOW + timedelta(minutes=3)
    say(state, "undo that")
    with pytest.raises(ToolError):
        tools["propose_change"](action="undo")
    assert len(state.knowledge.query(bm, at=clock["now"])) == 1


# ---------- reading ----------


def test_facts_here_builds_the_filters(setup, monkeypatch):
    bm, state, tools = setup
    seen = {}

    def query(_bm, **filters):
        seen.clear()
        seen.update(filters)
        return []

    monkeypatch.setattr(state.knowledge, "query", query)
    say(state, "open issues on pumps in hall A this week")
    result = call(tools, "facts_here", status="open", asset_type="Pumps", area="hall A", period="this week")
    assert result["count"] == 0 and "Nothing" in result["say"]
    assert seen["status"] == "open" and seen["asset_type"] == "pumps" and seen["area"] == "hall A"
    assert seen["since"] == datetime(2026, 10, 19, 0, 0, tzinfo=kt.TZ) and seen["history"] is False
    call(tools, "facts_here", place="Drill press H-A1", history=True, period="this week")
    assert seen["asset_id"] == asset_named(bm, "Drill press H-A1")["id"] and seen["history"] is True
    call(tools, "facts_here", person="Technician A", period="diese Woche")
    assert seen["person"] == "Technician A" and "space_id" not in seen
    room = next(iter(bm.spaces))
    state.position = make_position(bm, room, None, "said", 0)
    call(tools, "facts_here")
    assert seen["space_id"] == room  # 'what's here' with a position


def test_what_is_here_reads_age_and_author_and_marks_the_page(setup):
    bm, state, tools = setup
    remember_card(bm, state, tools)
    say(state, "yes")
    call(tools, "confirm_change", confirmed=True, user_reply="yes")
    say(state, "notes for drill press H-A1?")
    result = call(tools, "facts_here", place="Drill press H-A1")
    fact = result["facts"][0]
    assert fact["since"] == "since 9:00" and fact["by"] == "Technician A" and fact["text"] == "the valve drips"
    assert bm.found_facts and bm.located_asset_ids == [asset_named(bm, "Drill press H-A1")["id"]]


# ---------- guiding ----------


def test_a_walk_reads_a_rooms_note_once(setup):
    bm, state, tools = setup
    press = asset_named(bm, "Drill press H-A1")
    remember_card(bm, state, tools)
    say(state, "yes")
    call(tools, "confirm_change", confirmed=True, user_reply="yes")
    start = next(
        s
        for s, space in bm.spaces.items()
        if s != press["space_id"] and space["type"] == "room" and _routes(bm, s, press["space_id"])
    )
    say(state, "guide me to the drill press")
    seen, step = [], call(tools, "give_directions", start=start, destination=press["space_id"], guided=True)
    for _ in range(len(state.walk.steps) + 2):
        if step.get("fact"):
            seen.append(step["fact"])
        if step.get("arrived"):
            break
        step = call(tools, "next_steps")
    assert len(seen) == 1 and "the valve drips" in seen[0] and "Technician A" in seen[0]
    state.walk.index = 0
    replay = [walking.step_payload(bm, state.walk) for _ in range(2)]
    assert not any(item.get("fact") for item in replay)  # never twice on one walk


def _routes(bm, start, end) -> bool:
    try:
        return len(walking.build_walk(bm, routing.route(bm, start, end)).steps) >= walking.MIN_STEPS_FOR_OVERVIEW
    except MapError:
        return False


def test_here_with_a_named_machine_of_the_room_anchors_on_the_machine(setup):
    bm, state, tools = setup
    press = asset_named(bm, "Drill press H-A1")
    state.position = make_position(bm, press["space_id"], None, "said", 0)
    say(state, "remember here: the drill press is leaking oil")
    call(tools, "remember_here", text="the drill press is leaking oil")
    assert state.pending.extra["anchor"]["asset_id"] == press["id"]
    say(state, "remember here: the floor is wet")
    state.pending = None
    call(tools, "remember_here", text="the floor is wet")
    assert state.pending.extra["anchor"]["asset_id"] is None  # nothing named: the note stays on the room
