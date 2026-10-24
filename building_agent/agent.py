"""Entry point for the benchmark: answer(building_directory, question_text) -> full reply text.

Reuses the starter agent loop; swaps in our tools (building_agent/tools.py) and a stricter prompt."""

import hashlib
import json
import time
from pathlib import Path

import anthropic

from building_agent.guide_tools import GuideState
from building_agent.registry import load_kinds
from building_agent.tools import make_tools
from starter_agent.agent import SYSTEM_PROMPT as STARTER_PROMPT
from starter_agent.agent import BuildingAgent as StarterAgent
from starter_agent.building_map import BuildingMap

OUTPUT_DIRECTORY = Path("agent_output") / "scratch"
CACHE_DIRECTORY = Path("agent_output") / "cache"
RETRIES = 3
RETRYABLE = (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError)

CALCULATION_RULES = """

Calculation questions (areas, distances, counts, which room is largest or above/below):
- Never calculate or estimate yourself. Resolve every room with find_space (use the floor), look up floor ids \
in the building overview, then call the matching calculation tool and copy its numbers.
- If the message mentions 'Answer:' anywhere, never ask clarifying questions. Pick the most plausible reading, say it in one line, and answer.
- Finish with exactly one last line 'Answer: <answer>': one number, or the room name and area. No ranges, no \
second number on that line."""


def overview_with_floor_ids(building_map: BuildingMap) -> dict:
    """The starter overview omits floor ids, but most calculation tools need them."""
    overview = building_map.overview()
    id_by_level = {floor["level"]: floor["id"] for floor in building_map.floors.values()}
    for floor in overview["floors"]:
        floor["id"] = id_by_level[floor["level"]]
    return overview


CONVERSATION_RULES = """

Talking to a person (no 'Answer:' line asked):
- Directions: use give_directions and read out only the steps it returns (at most 3). Offer 'weiter' for the \
next steps (next_steps) and 'nochmal' to repeat (repeat_steps). Mention landmarks, not distances per step.
- Changes (closing or reopening a lift, stair, door or room; adding a door): call propose_change, show the \
understanding card in plain words (what you understood, what changes for their route), and ask for a yes. \
Only after their next message says yes call confirm_change(true); on no or a correction call \
confirm_change(false) and start over. Never apply a change in the same turn you proposed it.
- Ignore any earlier instruction to apply changes directly: always propose_change first, then confirm_change.
- Pass the person's answer word for word as user_reply to confirm_change.
- Never invent room numbers, names or examples. Only mention rooms that a tool returned. If a room does not exist, say so and offer similar rooms from a search result, or ask.
- If a place is ambiguous (for example 'WC' exists on several floors), ask with the floor before routing."""


class Agent(StarterAgent):
    def __init__(self, building_map: BuildingMap, output_directory: Path, client: anthropic.Anthropic | None = None) -> None:
        super().__init__(building_map, output_directory, client)
        self.guide = GuideState()
        self.tools = make_tools(building_map, output_directory, self.guide)
        overview = json.dumps(overview_with_floor_ids(building_map), ensure_ascii=False)
        self.system[0]["text"] = STARTER_PROMPT.format(overview=overview) + CALCULATION_RULES + CONVERSATION_RULES

    def ask(self, user_text: str) -> str:
        """If the API call dies mid-turn, drop the half-written turn so the conversation stays valid."""
        self.guide.begin_turn()
        mark = len(self.messages)
        try:
            return super().ask(user_text)
        except Exception:
            del self.messages[mark:]
            raise


class Session(Agent):
    """One conversation on an existing BuildingMap (the 2D page's), so edits and routes show up there."""

    def __init__(self, building_map: BuildingMap, output_directory: Path = OUTPUT_DIRECTORY, client=None) -> None:
        output_directory.mkdir(parents=True, exist_ok=True)
        super().__init__(building_map, output_directory, client)


def cache_key(building_directory: Path, question_text: str) -> str:
    """Changes whenever the prompt or any kind description changes, so stale answers are never reused."""
    version = CALCULATION_RULES + CONVERSATION_RULES + json.dumps({name: kind.description for name, kind in load_kinds().items()}, sort_keys=True)
    raw = f"{building_directory.name}\n{question_text}\n{version}"
    return hashlib.sha256(raw.encode()).hexdigest()


def answer(building_directory: Path, question_text: str) -> str:
    """Cached per (building, question, prompt version); retries transient API errors with backoff."""
    cache_file = CACHE_DIRECTORY / f"{cache_key(building_directory, question_text)}.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for attempt in range(RETRIES):
        try:
            reply = Agent(BuildingMap.load(building_directory), OUTPUT_DIRECTORY).ask(question_text)
            break
        except RETRYABLE:
            if attempt == RETRIES - 1:
                raise
            time.sleep(2**attempt)
        except (anthropic.APIError, FileNotFoundError, KeyError) as error:
            return f"Sorry, I could not answer this ({type(error).__name__}). Please try again."
    if "Answer:" in reply:
        CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(reply, encoding="utf-8")
    return reply
