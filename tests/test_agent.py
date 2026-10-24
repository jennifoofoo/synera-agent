from pathlib import Path

from building_agent.agent import CALCULATION_RULES, Agent
from building_agent.registry import load_kinds
from tests.conftest import labelled_questions, load_map


def test_agent_wires_kind_tools_and_calculation_rules_without_api_key():
    building_dir, _ = labelled_questions("errand")[0]
    agent = Agent(load_map(building_dir), Path("agent_output") / "test", client=object())
    names = {tool.name for tool in agent.tools}
    assert set(load_kinds()) <= names
    assert "find_space" in names
    assert CALCULATION_RULES in agent.system[0]["text"]


def test_system_prompt_overview_lists_floor_ids():
    building_dir, _ = labelled_questions("errand")[0]
    bm = load_map(building_dir)
    agent = Agent(bm, Path("agent_output") / "test", client=object())
    for floor_id in bm.floors:
        assert floor_id in agent.system[0]["text"]


def test_answer_is_cached_and_retries_transient_errors(tmp_path, monkeypatch):
    from building_agent import agent as agent_module

    building_dir, question = labelled_questions("errand")[0]
    monkeypatch.setattr(agent_module, "CACHE_DIRECTORY", tmp_path)
    monkeypatch.setattr(agent_module, "RETRYABLE", (ConnectionError,))
    monkeypatch.setattr(agent_module.time, "sleep", lambda seconds: None)
    calls = []

    def fake_ask(self, text):
        calls.append(text)
        if len(calls) == 1:
            raise ConnectionError("transient")
        return "ok\nAnswer: 1"

    monkeypatch.setattr(agent_module.Agent, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(agent_module.Agent, "ask", fake_ask)
    first = agent_module.answer(Path(building_dir), question["question"])
    second = agent_module.answer(Path(building_dir), question["question"])
    assert first == second == "ok\nAnswer: 1"
    assert len(calls) == 2  # one failed try, one success; the second answer() came from the cache


def test_session_works_on_the_given_map_and_keeps_the_conversation():
    from building_agent.agent import Session

    building_dir, _ = labelled_questions("errand")[0]
    bm = load_map(building_dir)
    session = Session(bm, Path("agent_output") / "test", client=object())
    assert session.map is bm
    assert any(tool.name == "give_directions" for tool in session.tools)
    session.guide.begin_turn()
    session.guide.begin_turn()
    assert session.guide.turn == 2  # state lives on the session, not per question


def test_failed_turn_leaves_the_conversation_valid(monkeypatch):
    import starter_agent.agent as starter

    building_dir, _ = labelled_questions("errand")[0]
    agent = Agent(load_map(building_dir), Path("agent_output") / "test", client=object())

    def dying_ask(self, text):
        self.messages.append({"role": "user", "content": text})
        raise RuntimeError("API died")

    monkeypatch.setattr(starter.BuildingAgent, "ask", dying_ask)
    try:
        agent.ask("hello")
    except RuntimeError:
        pass
    assert agent.messages == []
