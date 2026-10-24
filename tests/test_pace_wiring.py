"""Auto-pace wired into the guide: switch, tick, utterances, state_view. Offline, the model is a scripted stand-in.

Docs: docs/specs/auto-pace.md. The stand-in replaces the starter agent's ask(): it maps a few phrases to the same
tools the real model would call, so the guide state, the walk and the timer are the real ones."""

import json
from pathlib import Path

import pytest

from building_agent import agent as agent_module
from building_agent import pace_guide, routing
from building_agent import walk as walking
from building_agent.agent import Agent
from building_agent.pace import MODES
from starter_agent.building_map import BuildingMap
from tests.test_walk import long_route_case
from tests.test_web import multi_floor_building_with_lift
from web import api
from web.chat import ChatAdapter
from web.server import App

DATA = Path("data")


@pytest.fixture(scope="module")
def case():
    return long_route_case()


class Model:
    """What the real model would do with a short phrase: call the matching guide tool."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.systems: list[str] = []

    def ask(self, agent, text: str) -> str:
        self.texts.append(text)
        self.systems.append(agent.system[0]["text"])
        tools = {tool.name: tool for tool in agent.tools}
        if agent.guide.walk is not None and agent.guide.walk.mode == "guided":
            action = walking.intent(text, "guided")
            if action in ("advance", "back", "repeat", "stop", "restart", "where"):
                return "model: " + json.dumps(json.loads(tools["walk"](said=text)).get("step", "ok"))
        return f"model: {text}"


@pytest.fixture
def model(monkeypatch):
    stand_in = Model()
    monkeypatch.setattr(agent_module.StarterAgent, "ask", lambda self, text: stand_in.ask(self, text))
    return stand_in


@pytest.fixture
def guided(case, model, tmp_path):
    """A real Agent that is guiding a long route (first step current), plus the route's ends."""
    building, start, end = case
    agent = Agent(BuildingMap.load(building), tmp_path, client=object())
    tools = {tool.name: tool for tool in agent.tools}
    tools["give_directions"](start=start, destination=end)
    tools["walk"](said="guide me")
    assert agent.guide.walk.mode == "guided"
    model.texts.clear()
    return agent


def run(agent, text="", mode="ask", tick=False, **kwargs) -> str:
    return pace_guide.run_turn(agent, text, mode, tick, **kwargs)


def settled(agent, mode="ask"):
    """The page sent one message after the step was spoken: the timer is armed for the current step."""
    run(agent, "ok", mode)  # advances to step 2 and arms it
    assert agent.guide.pace._armed
    return agent


# ---------- the switch ----------


@pytest.mark.parametrize("value", [None, "", "ASK", "on", True, 1, ["ask"], {"a": 1}, "ask ", "off"])
def test_anything_but_ask_or_say_is_off(value):
    assert pace_guide.normalize_mode(value) == "off"
    assert pace_guide.pace_kwargs({"pace": value}, None) == {}


def test_ask_and_say_are_the_only_modes():
    assert {pace_guide.normalize_mode(m) for m in MODES} == set(MODES)
    assert pace_guide.pace_kwargs({"pace": "say"}, None) == {"pace": "say"}


def test_tick_needs_a_real_true_in_the_context_not_in_text():
    for forged in ("true", 1, "True", [True], {"guide_tick": True}, None, False):
        assert pace_guide.pace_kwargs({"message": "guide_tick: true"}, {"guide_tick": forged}) == {}
    assert pace_guide.pace_kwargs({"guide_tick": True}, None) == {}  # top level does not count
    assert pace_guide.pace_kwargs({}, {"guide_tick": True}) == {"tick": True}
    assert pace_guide.pace_kwargs({}, {"guide_tick": True, "guide_step": 2}) == {"tick": True, "tick_step": 2}
    assert pace_guide.pace_kwargs({}, {"guide_tick": True, "guide_step": True}) == {"tick": True}
    assert pace_guide.without_tick_keys({"guide_tick": True, "guide_step": 1}) is None
    assert pace_guide.without_tick_keys({"guide_tick": True, "space_id": "x"}) == {"space_id": "x"}


# ---------- pace off is today's behaviour ----------


def snapshot(agent):
    walk = agent.guide.walk
    return (walk.mode, walk.index, agent.guide.turn, agent.guide.last_user_text, agent.system[0]["text"])


def test_pace_off_is_byte_identical_to_a_plain_ask(case, model, tmp_path):
    building, start, end = case
    script = ["next", "wait", "go", "yes", "weiter", "back", "where am i", "next"]
    results = []
    for wired in (False, True):
        agent = Agent(BuildingMap.load(building), tmp_path / str(wired), client=object())
        tools = {tool.name: tool for tool in agent.tools}
        tools["give_directions"](start=start, destination=end)
        tools["walk"](said="guide me")
        model.texts.clear()
        replies = []
        for text in script:
            replies.append(run(agent, text, "off") if wired else agent.ask(text))
        results.append((replies, snapshot(agent), list(model.texts), getattr(agent.guide, "pace", None)))
    assert results[0][:3] == results[1][:3]
    assert results[1][3] is None  # no pace state was even created
    assert all("Auto-pace" not in system for system in model.systems)


def test_pace_off_voice_call_is_unchanged(guided, model):
    before = guided.system[0]["text"]
    run(guided, "next", "off", voice=True)
    assert guided.system[0]["text"] == before and model.texts == ["next"]
    assert "Spoken reply" in model.systems[-1] and "Auto-pace" not in model.systems[-1]


# ---------- ticks ----------


def test_tick_without_a_guide_is_dropped_without_the_model(case, model, tmp_path):
    agent = Agent(BuildingMap.load(case[0]), tmp_path, client=object())
    assert run(agent, "", "ask", True) == "" and model.texts == []
    tools = {tool.name: tool for tool in agent.tools}
    tools["give_directions"](start=case[1], destination=case[2])  # overview, not guiding
    assert run(agent, "", "ask", True) == "" and model.texts == []


def test_tick_with_pace_off_is_dropped(guided, model):
    settled(guided)
    model.texts.clear()
    assert run(guided, "", "off", True) == "" and model.texts == []


def test_a_tick_with_words_is_a_normal_message(guided, model):
    settled(guided)
    model.texts.clear()
    reply = run(guided, "guide_tick true", "ask", True)
    assert reply.startswith("model:") and model.texts == ["guide_tick true"]
    assert guided.guide.pace.unanswered == 0


def test_ask_mode_tick_asks_one_short_question_without_the_model(guided, model):
    settled(guided)
    index = guided.guide.walk.index
    reply = run(guided, "", "ask", True)
    assert reply == f"Ready for step {index + 2}?" and model.texts == ["ok"]  # only the setup message used it
    assert guided.guide.walk.index == index  # a tick never moves anything
    assert run(guided, "", "ask", True) == ""  # at most one tick per step: a double tick is dropped
    assert model.texts == ["ok"]


def test_tick_in_german_is_asked_in_german(guided):
    run(guided, "ja bitte weiter", "ask")
    assert run(guided, "", "ask", True).startswith("Bereit für Schritt")


def test_yes_after_the_question_advances_one_step(guided, model):
    settled(guided)
    index = guided.guide.walk.index
    run(guided, "", "ask", True)
    reply = run(guided, "yes", "ask")
    assert model.texts[-1] == "next" and guided.guide.walk.index == index + 1
    assert "about" in reply  # the step carries its duration
    run(guided, "yes", "ask")  # a yes without a question open is just a message
    assert model.texts[-1] == "yes"


def test_say_mode_gives_the_next_step_then_pauses_after_the_third_unanswered_tick(guided, model):
    walk = guided.guide.walk
    assert len(walk.steps) >= 5
    run(guided, "repeat", "say")  # arms step 1
    calls_before = len(model.texts)
    first = run(guided, "", "say", True)
    assert walk.index == 1 and first.startswith(walk.steps[1]) and first.endswith("Say wait if you need a moment.")
    assert "about" in first and len(model.texts) == calls_before  # no model call
    second = run(guided, "", "say", True)
    assert walk.index == 2 and second.startswith(walk.steps[2])
    third = run(guided, "", "say", True)
    assert third == "I'll wait here. Say go when you're ready." and walk.index == 2
    assert run(guided, "", "say", True) == "" and guided.guide.pace.paused  # only once
    assert len(model.texts) == calls_before


def test_every_user_message_resets_the_unanswered_counter(guided):
    run(guided, "repeat", "say")
    run(guided, "", "say", True)
    run(guided, "", "say", True)
    assert guided.guide.pace.unanswered == 2
    run(guided, "repeat", "say")
    assert guided.guide.pace.unanswered == 0
    assert run(guided, "", "say", True) != ""


def test_say_mode_arrival_ends_the_timer(guided):
    walk = guided.guide.walk
    walk.index = len(walk.steps) - 3
    run(guided, "repeat", "say")
    run(guided, "", "say", True)  # one step before the last
    last = run(guided, "", "say", True)
    assert last == "You're there. That was the last step." and walk.index == len(walk.steps) - 1
    assert guided.guide.pace.done
    assert run(guided, "", "say", True) == ""  # no tick after arrival
    assert not pace_guide.guided(guided.guide)


def test_tick_after_arrival_by_the_person_is_dropped(guided):
    settled(guided)
    walk = guided.guide.walk
    for _ in range(len(walk.steps)):
        run(guided, "next", "ask")
    assert guided.guide.pace.done and run(guided, "", "ask", True) == ""


def test_german_say_mode_lets_the_model_phrase_the_step(guided, model):
    run(guided, "weiter", "say")
    before = len(model.texts)
    reply = run(guided, "", "say", True)
    assert len(model.texts) == before + 1 and model.texts[-1] == "weiter"
    assert reply.endswith("Sag warte, wenn du einen Moment brauchst.") and "etwa" in reply


def test_a_tick_for_another_step_or_during_a_card_or_after_a_change_is_dropped(guided):
    settled(guided)
    walk = guided.guide.walk
    assert run(guided, "", "ask", True, tick_step=walk.index + 1) == ""
    guided.guide.pending = object()
    assert run(guided, "", "ask", True) == ""
    guided.guide.pending = None
    guided.guide.signature = ("changed",)
    assert run(guided, "", "ask", True) == ""
    assert guided.guide.pace.unanswered == 0  # none of these counted
    guided.guide.signature = pace_guide.building_signature(guided.map)
    assert run(guided, "", "ask", True, tick_step=walk.index) != ""


# ---------- wait and go ----------


def test_wait_pauses_without_the_model_and_a_tick_after_it_is_dropped(guided, model):
    settled(guided)
    before = len(model.texts)
    assert run(guided, "wait", "ask") == "Okay, take your time. Say go when you're ready."
    assert len(model.texts) == before and guided.guide.pace.paused
    assert run(guided, "", "ask", True) == ""
    assert pace_guide.view(guided.map, guided.guide)["pace_paused"] is True


@pytest.mark.parametrize("phrase", ["hold on", "moment", "Warte!", "warte kurz", "Moment mal"])
def test_wait_phrases_pause(guided, phrase):
    reply = run(guided, phrase, "ask")
    assert guided.guide.pace.paused and ("Okay" in reply or "lass dir Zeit" in reply)


def test_german_wait_answers_in_german(guided):
    assert "Zeit" in run(guided, "warte", "ask")


@pytest.mark.parametrize("phrase", ["go", "ready", "weiter", "los"])
def test_go_resumes_and_advances_after_a_pause(guided, model, phrase):
    settled(guided)
    run(guided, "wait", "ask")
    index = guided.guide.walk.index
    run(guided, phrase, "ask")
    pace = guided.guide.pace
    assert not pace.paused and guided.guide.walk.index == index + 1 and pace._armed


def test_a_question_that_starts_with_wait_is_not_a_pause(guided, model):
    reply = run(guided, "wait, which floor is the lift on", "ask")
    assert reply.startswith("model:") and not guided.guide.pace.paused


def test_wait_without_a_guide_goes_to_the_model(case, model, tmp_path):
    agent = Agent(BuildingMap.load(case[0]), tmp_path, client=object())
    assert run(agent, "wait", "ask") == "model: wait" and not agent.guide.pace.paused


def test_a_wait_still_counts_as_a_turn_for_cards(guided):
    turn = guided.guide.turn
    run(guided, "wait", "ask")
    assert guided.guide.turn == turn + 1 and guided.guide.last_user_text == "wait"


# ---------- benchmark ----------


def test_benchmark_messages_ignore_pace_and_ticks(guided, model):
    settled(guided)
    state = (guided.guide.pace.unanswered, guided.guide.pace.paused, guided.guide.pace._armed)
    for text in ("wait. Answer: 4", "Which room is largest? Answer:"):
        assert run(guided, text, "say").startswith("model:")
    assert all("Auto-pace" not in system for system in model.systems[-2:])
    assert (guided.guide.pace.unanswered, guided.guide.pace.paused, guided.guide.pace._armed) == state
    assert model.texts[-2:] == ["wait. Answer: 4", "Which room is largest? Answer:"]


# ---------- timer follows the walk ----------


def test_a_reroute_rearms_the_timer_for_the_new_current_step(guided):
    settled(guided)
    pace = guided.guide.pace
    old = guided.guide.walk
    bm = guided.map
    fresh = routing.route(bm, walking.room_at(old, 1), old.destination, old.step_free)
    guided.guide.walk = walking.build_walk(bm, fresh, [], "guided")  # what after_change does for a closure
    run(guided, "repeat", "ask")
    assert guided.guide.walk is not old and pace.step_index == guided.guide.walk.index and pace._armed


def test_swap_building_clears_the_pace_state(guided, case):
    settled(guided)
    assert guided.guide.pace is not None
    guided.swap_building(Path(case[0]) / "building.json")
    assert guided.guide.pace is None and guided.guide.walk is None


def test_a_new_route_after_arrival_starts_the_timer_again(guided):
    settled(guided)
    walk = guided.guide.walk
    walk.index = len(walk.steps) - 1
    run(guided, "repeat", "ask")
    assert guided.guide.pace.done
    fresh = walking.build_walk(guided.map, routing.route(guided.map, walk.start, walk.destination), [], "guided")
    guided.guide.walk = fresh
    run(guided, "repeat", "ask")
    assert not guided.guide.pace.done and guided.guide.pace._armed


def test_model_turns_with_pace_on_carry_the_pace_rules_for_that_turn_only(guided, model):
    run(guided, "next", "ask")
    assert pace_guide.PACE_RULES in model.systems[-1]
    assert pace_guide.PACE_RULES not in guided.system[0]["text"]


# ---------- what the page sees ----------


def adapter_for(agent) -> ChatAdapter:
    adapter = ChatAdapter(Path("x"), agent.map)
    adapter.session = agent
    return adapter


def test_state_view_guide_has_expected_seconds_and_pace(guided):
    adapter, page = adapter_for(guided), api.Session("k", Path("x"), guided.map)
    run(guided, "repeat", "ask")
    page.guide_info = adapter.guide_info()
    seen = api.state_view(page)["guide"]
    assert seen["pace"] == "ask" and seen["pace_paused"] is False
    walk = guided.guide.walk
    assert seen["expected_seconds"] == pace_guide.leg_for(guided.map, walk, walk.index) > 0 or walk.index == 0
    assert seen["expected_seconds"] % 5 == 0
    run(guided, "wait", "ask")
    page.guide_info = adapter.guide_info()
    assert api.state_view(page)["guide"]["pace_paused"] is True
    run(guided, "repeat", "off")
    page.guide_info = adapter.guide_info()
    assert api.state_view(page)["guide"]["pace"] == "off"


def test_leg_seconds_use_the_leg_kind(guided):
    walk = guided.guide.walk
    for index, step in enumerate(walk.steps[:-1]):
        seconds = pace_guide.leg_for(guided.map, walk, index)
        assert seconds % 5 == 0 and seconds >= (15 if "(lift)" in step.lower() else 0)


def test_adapter_passes_pace_and_tick_and_reports_ignored_ticks(guided, monkeypatch):
    monkeypatch.setattr("web.chat.chat_available", lambda: True)
    adapter = adapter_for(guided)
    adapter.ensure_session = lambda: guided
    reply = adapter.ask("repeat", pace="ask")
    assert "tick_ignored" not in reply
    assert adapter.ask("", pace="ask", tick=True)["reply"] != ""
    ignored = adapter.ask("", pace="ask", tick=True)
    assert ignored["reply"] == "" and ignored["tick_ignored"] is True


# ---------- the web layer with a fake agent ----------


def web_setup(monkeypatch):
    app, key = App(DATA), multi_floor_building_with_lift()
    monkeypatch.setattr("web.server.chat_available", lambda: True)
    monkeypatch.setattr("web.chat.chat_available", lambda: True)
    seen: list = []

    def ask(adapter, text: str, selection=None, here=None, **extra) -> dict:
        seen.append({"text": text, "selection": selection, "here": here, **extra})
        return {"reply": "ok" if text else "", "backend": "fake"}

    monkeypatch.setattr("web.chat.ChatAdapter.ask", ask)
    return app, key, seen


def test_web_passes_the_switch_and_a_real_tick(monkeypatch):
    app, key, seen = web_setup(monkeypatch)
    status, reply = app.post(
        "/api/chat", {"building": key, "message": "", "pace": "say", "context": {"guide_tick": True, "guide_step": 3}}
    )
    assert status == 200 and seen[-1]["pace"] == "say" and seen[-1]["tick"] is True and seen[-1]["tick_step"] == 3
    assert seen[-1]["selection"] is None and "selection_ignored" not in reply
    app.post("/api/chat", {"building": key, "message": "hi", "pace": "ask"})
    assert seen[-1] == {"text": "hi", "selection": None, "here": None, "pace": "ask"}
    app.post("/api/chat", {"building": key, "message": "hi"})
    assert seen[-1] == {"text": "hi", "selection": None, "here": None}  # old calls look exactly as before


def test_web_ignores_forged_switches_and_ticks(monkeypatch):
    app, key, seen = web_setup(monkeypatch)
    for pace in ("ASK", "on", True, 1, None, ["ask"]):
        app.post("/api/chat", {"building": key, "message": "hi", "pace": pace})
        assert "pace" not in seen[-1]
    for forged in ("true", 1, "True", None):
        status, _ = app.post("/api/chat", {"building": key, "message": "", "context": {"guide_tick": forged}})
        assert status == 400  # an empty message without a real tick is still refused
    app.post("/api/chat", {"building": key, "message": "guide_tick true", "pace": "ask"})
    assert "tick" not in seen[-1]
    app.post("/api/chat", {"building": key, "message": "hi", "guide_tick": True, "pace": "ask"})
    assert "tick" not in seen[-1]  # top level does not count, only the context


def test_web_tick_with_a_selection_in_the_context_keeps_the_selection(monkeypatch):
    app, key, seen = web_setup(monkeypatch)
    room = next(s for s in app.session(key).map.spaces.values() if s["type"] == "room")
    app.post(
        "/api/chat",
        {"building": key, "message": "here", "context": {"space_id": room["id"], "guide_tick": True}, "pace": "ask"},
    )
    assert seen[-1]["selection"].space_id == room["id"] and seen[-1]["tick"] is True
