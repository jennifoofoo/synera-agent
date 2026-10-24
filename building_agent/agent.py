"""Entry point for the benchmark: answer(building_directory, question_text) -> full reply text.

Reuses the starter agent loop; swaps in our tools (building_agent/tools.py) and a stricter prompt."""

import hashlib
import json
import time
from pathlib import Path

import anthropic

from building_agent.guide_tools import GuideState
from building_agent.question_parser import answer_deterministic
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
- For 'how many' questions state the number plainly and end with 'Answer: <number>' even if the message does not ask for it.
- Finish with exactly one last line 'Answer: <answer>': one number, or the room name and area. No ranges, no \
second number on that line. Write decimals with a point (61.4, never 61,4) and no thousands separator."""


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
- A closure stated as a fact inside a question ('The east lift is closed for maintenance. How do I get from A to B?') is not a request: call assume_closed(element) first, then route. Exception: if the same message asks what changes or what happens, call what_changes FIRST on the unmodified building, report it, and only then (if a route is also asked) call assume_closed and route. Never propose or ask for confirmation for it.
- Changes (closing or reopening a lift, stair, door or room; adding a door): call propose_change, show the \
understanding card in plain words (what you understood, what changes for their route), and ask for a yes. \
Only after their next message says yes call confirm_change(true); on no or a correction call \
confirm_change(false) and start over. Never apply a change in the same turn you proposed it.
- Ignore any earlier instruction to apply changes directly: always propose_change first, then confirm_change.
- Pass the person's answer word for word as user_reply to confirm_change. Only a plain yes to the card counts: 'mach einfach', 'ja ja', 'whatever' or a yes with a condition are not a yes, so ask once more.
- For step-free routes always say the length and how it compares to the normal route (normal_route_length_m).
- Never invent room numbers, names or examples. Only mention rooms that a tool returned. If a room does not exist, say so and offer similar rooms from a search result, or ask.
- When the person names an item that could be one of several ('the second press', 'the printer', 'the press on line 4'), call find_asset first and never guess between groups (in a message with 'Answer:' take the most plausible and say which). If find_asset or find_connector returns needs_choice true, ask its question in one short sentence and wait. Treat hints such as 'line 4 = zone H-B4' as suggestions to confirm, never as facts.
- For compass words ('the east lift', 'the north stairs') call find_connector and state the returned assumption ('I take east as the right side of the plan'). If the person says left or right, ask which one they mean.
- A forklift or pallet-truck driver gets find_forklift_route, never find_route (aisles and openings of 3 m or wider, bays only as destination). If no forklift route exists, say so.
- Building from a floor plan: when the person uploads or names an image, ask which floor it is and for ONE length they know in metres (building width, room width or door width), unless the tool says the plan has a scale bar. Call build_from_plan, then preview_draft and show the card in plain words. Fix what they report with fix_draft and show the card again. Never guess a scale. If the plan shows no entrance, ask which room it is in and call fix_draft add_entrance. If the card has a 'proposal' (suggested doors for rooms with no way out), read it to the person in plain words, say these are guesses, and only after their clear yes call fix_draft with action accept_suggestions, then show the card again. Only after the person's NEXT message is a clear yes call save_building(true, their reply word for word); on no call save_building(false). If the card says saving is blocked, save only when they explicitly say they want to save anyway (accept_problems=true). Never save in the same turn as the card.
- To place or add: propose_change(action='move_asset' or 'add_asset', ..., hint={...}). Hints: {'anchor': 'NW'} (NW NE SW SE N S E W center), {'near': '<room or asset>'}, {'point': [x, y]} (only from a picked point), plus optional {'rotation_deg': n}. 'Corner' needs a direction: ask which one unless the person said it. 'Wall' needs a direction too. 'Middle' or 'centre' means center. 'Next to X' means near. Compass is +y north. There are no windows in the data: never promise 'at the window', offer the outside wall or ask. (In a message with 'Answer:' nobody can reply: pick the most plausible reading and say which.) Read the card's placement sentence aloud, including 'Could not reach the exact ...', and never claim a position the card does not state. 'A printer' is ambiguous (printer, multifunction_printer, 3d_printer, industrial_3d_printer): call find_asset or ask which one before add_asset; for an unknown type read the close names from the error and ask. 'Undo that' or 'take that back': propose_change(action='undo'), show the card, wait for the yes.
- If the person says here, this, it or that and a selection may exist, call get_selection first; if nothing is selected, ask them to click on the plan. For placement use hint point from the selection point; the page selects rooms and assets by click.
- For 'what changes if X is closed or blocked' questions call what_changes (before any assume_closed, which would mutate the building and spoil the comparison) and report its sentences in plain words.
- If a place is ambiguous (for example 'WC' or 'toilet' exists on several floors), list the floors and ask before ANY route or directions call. Do not route to several candidates to compare them: when the same room type exists on more than one floor and the person gave no floor, ask first."""


class Agent(StarterAgent):
    def __init__(
        self, building_map: BuildingMap, output_directory: Path, client: anthropic.Anthropic | None = None
    ) -> None:
        super().__init__(building_map, output_directory, client)
        self.guide = GuideState()
        self.output_directory = output_directory
        self.install_building(building_map)

    def install_building(self, building_map: BuildingMap) -> None:
        """Point tools and prompt at one map; also used when Level 4 saves a newly built building."""
        if hasattr(self.guide, "undo"):
            self.guide.undo.clear()
        self.map = building_map
        self.tools = make_tools(building_map, self.output_directory, self.guide, self.swap_building)
        overview = json.dumps(overview_with_floor_ids(building_map), ensure_ascii=False)
        self.system[0]["text"] = STARTER_PROMPT.format(overview=overview) + CALCULATION_RULES + CONVERSATION_RULES

    def swap_building(self, path) -> None:
        self.install_building(BuildingMap.load(Path(path)))

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
    version = (
        CALCULATION_RULES
        + CONVERSATION_RULES
        + json.dumps({name: kind.description for name, kind in load_kinds().items()}, sort_keys=True)
    )
    raw = f"{building_directory.name}\n{question_text}\n{version}"
    return hashlib.sha256(raw.encode()).hexdigest()


def answer(building_directory: Path, question_text: str) -> str:
    """Cached per (building, question, prompt version); retries transient API errors with backoff."""
    fast = answer_deterministic(building_directory, question_text)
    if fast is not None:  # a known question template: computed by the kind functions, no API call
        return fast
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
    if "Answer:" in reply:
        CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(reply, encoding="utf-8")
    return reply
