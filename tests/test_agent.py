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

    building_dir, _question = labelled_questions("errand")[0]
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
    first = agent_module.answer(Path(building_dir), "Please describe this building in one sentence.")
    second = agent_module.answer(Path(building_dir), "Please describe this building in one sentence.")
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


def test_known_question_template_is_answered_without_the_llm(monkeypatch):
    from building_agent import agent as agent_module

    building_dir, question = labelled_questions("errand")[0]

    def must_not_run(self, text):
        raise AssertionError("the LLM agent must not run for a parsed template question")

    monkeypatch.setattr(agent_module.Agent, "ask", must_not_run)
    reply = agent_module.answer(Path(building_dir), question["question"])
    assert "Answer:" in reply


def test_saved_building_swaps_the_map_tools_and_prompt():
    building_dir, _question = labelled_questions("errand")[0]
    other_dir = next(path for path in sorted(Path("data/dev").iterdir()) if path.name != Path(building_dir).name)
    agent = Agent(load_map(building_dir), Path("agent_output") / "test", client=object())
    agent.swap_building(other_dir / "building.json")
    assert agent.map.data["building"]["id"] == other_dir.name
    assert other_dir.name in agent.system[0]["text"] or agent.map.data["building"]["name"] in agent.system[0]["text"]
    assert {"build_from_plan", "save_building", "find_route"} <= {tool.name for tool in agent.tools}


def test_campus_holder_adds_campus_tools_and_rules_only_when_given(tmp_path):
    from pathlib import Path as P

    from building_agent.agent import CAMPUS_RULES
    from building_agent.campus import make_example_campus
    from building_agent.campus_tools import CampusHolder, load_maps

    building_dir, _question = labelled_questions("errand")[0]
    plain = Agent(load_map(building_dir), P("agent_output") / "test", client=object())
    assert "campus_route" not in {tool.name for tool in plain.tools}
    assert CAMPUS_RULES not in plain.system[0]["text"]

    campus = make_example_campus(P("data"))
    maps, _ = load_maps(campus)
    first = next(iter(maps.values()))
    holder = CampusHolder(campus, maps, path=tmp_path / "campus.json", bm=first)
    multi = Agent(first, P("agent_output") / "test", client=object(), campus=holder)
    assert {"campus_route", "list_buildings", "connect_buildings"} <= {tool.name for tool in multi.tools}
    assert CAMPUS_RULES in multi.system[0]["text"]
