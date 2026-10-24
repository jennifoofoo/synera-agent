"""Entry point for the benchmark: answer(building_directory, question_text) -> full reply text.

Reuses the starter agent loop; swaps in our tools (building_agent/tools.py) and a stricter prompt."""

import json
from pathlib import Path

import anthropic

from building_agent.tools import make_tools
from starter_agent.agent import SYSTEM_PROMPT as STARTER_PROMPT
from starter_agent.agent import BuildingAgent as StarterAgent
from starter_agent.building_map import BuildingMap

OUTPUT_DIRECTORY = Path("agent_output") / "scratch"

CALCULATION_RULES = """

Calculation questions (areas, distances, counts, which room is largest or above/below):
- Never calculate or estimate yourself. Resolve every room with find_space (use the floor), look up floor ids \
in the building overview, then call the matching calculation tool and copy its numbers.
- If the question has no person to talk to (it ends with a line like 'Finish with a line Answer: ...'), do not \
ask clarifying questions. Pick the most plausible reading, say it in one line, and answer.
- Finish with exactly one last line 'Answer: <answer>': one number, or the room name and area. No ranges, no \
second number on that line."""


class Agent(StarterAgent):
    def __init__(self, building_map: BuildingMap, output_directory: Path, client: anthropic.Anthropic | None = None) -> None:
        super().__init__(building_map, output_directory, client)
        self.tools = make_tools(building_map, output_directory)
        overview = json.dumps(building_map.overview(), ensure_ascii=False)
        self.system[0]["text"] = STARTER_PROMPT.format(overview=overview) + CALCULATION_RULES


def answer(building_directory: Path, question_text: str) -> str:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    return Agent(BuildingMap.load(building_directory), OUTPUT_DIRECTORY).ask(question_text)
