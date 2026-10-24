"""Time words in the person's message never change the building, and the benchmark never gets asked 'where are you'.
Offline."""

import json
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError

from building_agent.guide_tools import GuideState
from building_agent.position import BENCHMARK_START, NO_POSITION, make_position
from building_agent.time_words import names_a_time, when_is_later
from building_agent.tools import make_tools
from tests.conftest import labelled_questions

LATER = [
    "The lift will be closed tomorrow",
    "close it from Monday",
    "please close Lift 1 next week",
    "on Friday the lift is out",
    "morgen ist der Aufzug gesperrt",
    "übermorgen sperren wir den Lift",
    "nächste Woche ist er kaputt",
    "ab Montag gesperrt",
    "am Freitag bitte schließen",
    "um 8 Uhr schließen",
    "tonight the door is locked",
    "heute Abend ist der Lift aus",
    "close it at 8pm",
    "in 2 hours it is closed",
    "in 3 Tagen ist er zu",
    "Next Monday please close the stairs",
]
NOW = [
    "close Lift 1 now",
    "close it right now please",
    "the lift is broken today",
    "der Aufzug ist jetzt kaputt",
    "heute ist der Aufzug kaputt",
    "Guten Morgen, der Aufzug ist kaputt",
    "the next lift is closed",
    "Lift 1 is broken",
]


@pytest.mark.parametrize("text", LATER)
def test_time_words_are_found(text):
    assert names_a_time(text) is True


@pytest.mark.parametrize("text", NOW)
def test_now_words_are_not_time_words(text):
    assert names_a_time(text) is False


def test_the_model_argument_when_only_blocks_for_later():
    assert when_is_later("tomorrow") and when_is_later("from Monday") and when_is_later("irgendwann")
    for now in ("", None, "now", "Right now", "today", "jetzt", "heute"):
        assert when_is_later(now) is False


def test_a_forged_long_message_with_a_time_word_in_it_is_still_caught():
    long = "please " * 4000 + "close the lift, but only from Monday " + "thanks " * 4000
    assert names_a_time(long) is True
    assert names_a_time("x" * 100000) is False


@pytest.fixture
def setup(tmp_path):
    building_dir, _ = labelled_questions("errand")[0]
    from starter_agent.building_map import BuildingMap

    bm = BuildingMap.load(Path(building_dir))
    state = GuideState()
    tools = {tool.name: tool for tool in make_tools(bm, tmp_path, state)}
    element = next(iter(bm.connectors), None) or next(iter(bm.openings))
    return bm, state, tools, element


@pytest.mark.parametrize("text", LATER[:6])
def test_a_time_word_in_the_message_blocks_every_closure_even_without_when(setup, text):
    bm, state, tools, element = setup
    state.begin_turn()
    state.last_user_text = text  # what Agent.ask records from the person's message
    for answer in (
        json.loads(tools["propose_change"](action="close", element=element)),
        json.loads(tools["assume_closed"](element=element)),
        json.loads(tools["propose_change"](action="close", element=element, when="now")),
    ):
        assert answer["scheduled"] is False and "only be changed now" in answer["note"]
    assert state.pending is None and not bm.closed


@pytest.mark.parametrize("text", NOW)
def test_now_or_today_closures_go_through(setup, text):
    _bm, state, tools, element = setup
    state.begin_turn()
    state.last_user_text = text
    card = json.loads(tools["propose_change"](action="close", element=element, when="now"))
    assert "waiting" in card["status"] and state.pending is not None


def test_the_agent_records_the_latest_message(tmp_path):
    from building_agent.agent import Agent
    from starter_agent.building_map import BuildingMap

    building_dir, _ = labelled_questions("errand")[0]
    agent = Agent(BuildingMap.load(Path(building_dir)), tmp_path, client=object())

    def fake_ask(self, text):
        return "ok"

    import starter_agent.agent as starter

    original = starter.BuildingAgent.ask
    starter.BuildingAgent.ask = fake_ask
    try:
        agent.ask("close it from Monday")
    finally:
        starter.BuildingAgent.ask = original
    assert agent.guide.last_user_text == "close it from Monday"


def test_a_benchmark_message_never_asks_where_the_person_is(setup):
    bm, state, tools, _ = setup
    rooms = [s for s, space in bm.spaces.items() if space["type"] == "room"][:2]
    state.last_user_text = "How far is it from A to B? Finish with 'Answer: <number>'."
    for name in ("find_route", "give_directions"):
        with pytest.raises(ToolError) as error:
            tools[name](destination=rooms[1])
        assert str(error.value) == BENCHMARK_START and "never ask" in str(error.value).lower()
    state.last_user_text = "How do I get to the lab?"
    with pytest.raises(ToolError) as error:
        tools["find_route"](destination=rooms[1])
    assert str(error.value) == NO_POSITION
    state.last_user_text = "answer: 5"
    assert json.loads(tools["find_route"](start=rooms[0], destination=rooms[1]))["start_space_id"] == rooms[0]
    state.position = make_position(bm, rooms[0], None, "said", 0)
    assert json.loads(tools["find_route"](destination=rooms[1]))["start_space_id"] == rooms[0]
