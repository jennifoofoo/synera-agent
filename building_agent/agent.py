"""Entry point for the benchmark: answer(building_directory, question_text) -> full reply text.

For now this runs the unchanged starter agent so the pipeline works end to end. Swap in our own
tools (building_agent/tools.py) as the query functions get ready."""

from pathlib import Path

from starter_agent.agent import BuildingAgent
from starter_agent.building_map import BuildingMap

OUTPUT_DIRECTORY = Path("agent_output") / "scratch"


def answer(building_directory: Path, question_text: str) -> str:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    agent = BuildingAgent(BuildingMap.load(building_directory), OUTPUT_DIRECTORY)
    return agent.ask(question_text)
