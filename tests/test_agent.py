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
