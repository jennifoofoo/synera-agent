"""Live: people say what they want to DO (or half remember a device). Asserts on tool calls and the building, not wording.

The task tools are injected here (tools.py and agent.py are not edited by this feature): the same tool list and
rule text that the integration adds, so this test also checks the proposed prompt sentences."""

import re
from pathlib import Path

import pytest

from building_agent import agent as agent_module
from building_agent.task_tools import make_task_tools
from starter_agent.building_map import BuildingMap
from tests.live.harness import Transcript, run_script

pytestmark = pytest.mark.live

SEARCH_TOOLS = ("search_building", "find_space", "find_asset")
TASK_TOOLS = ("find_for_task", "describe_asset")
SPEC_WORDS = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:kw|kg|bar|rpm|mm/min|°c|kn|tons?|tonnes?|watts?|volts?|amps?)\b", re.IGNORECASE
)
NEGATION = re.compile(
    r"\b(no|not|isn't|is not|don't|doesn't|nicht|kein|keine|nothing|instead|rather|but)\b", re.IGNORECASE
)
OFFER = re.compile(r"route|directions|walk|take you|show you|navigate|lead you|weg|führ|zeig", re.IGNORECASE)

TASK_RULES = """
- When the person says what they want to DO or half remembers a device ('I want to weld', 'where can I copy something', \
'where do I get coffee', 'someone said there is a laser thing in hall 3'), call find_for_task with their own words before \
searching by words. Answer in this order: first confirm what exists and where, then correct gently what differs (the \
corrections field: wrong room or floor, a device type this building does not have and what it has instead), then say what \
the device is for from its summary and say that this is general knowledge of the type. If needs_choice is true ask the \
returned question in one short sentence (in a message with 'Answer:' take the most plausible candidate and say which). \
To explain a device use describe_asset or general knowledge of the type and say it is general. Never state specifications, \
settings, state, capacity or availability of a unit: that data does not exist here. Never claim a device exists that \
find_for_task did not return.
"""


@pytest.fixture(scope="module", autouse=True)
def task_tools_enabled():
    patch = pytest.MonkeyPatch()
    original = agent_module.make_tools

    def with_task_tools(bm, *args, **kwargs):
        tools = original(bm, *args, **kwargs)
        known = {tool.name for tool in tools}
        return [*tools, *(tool for tool in make_task_tools(bm) if tool.name not in known)]

    patch.setattr(agent_module, "make_tools", with_task_tools)
    if "find_for_task" not in agent_module.CONVERSATION_RULES:
        patch.setattr(agent_module, "CONVERSATION_RULES", agent_module.CONVERSATION_RULES + TASK_RULES)
    yield
    patch.undo()


def factory() -> tuple[Path, BuildingMap]:
    for path in sorted(Path("data/dev").glob("proc-factory-*")):
        bm = BuildingMap.load(path)
        types = {asset["type"] for asset in bm.assets.values()}
        if {
            "welding_station",
            "coffee_machine",
            "waterjet_cutter",
            "press_brake",
        } <= types and "laser_cutter" not in types:
            return path, bm
    raise LookupError("no dev factory with welding, coffee, waterjet and press brake but no laser cutter")


def places(bm: BuildingMap, *types: str) -> set[str]:
    found = set()
    for asset in bm.assets.values():
        if asset["type"] in types:
            space = bm.spaces[asset["space_id"]]
            found |= {space["name"].lower(), (space.get("ref") or "").lower()}
    return {item for item in found if item}


def names_a_place(reply: str, expected: set[str]) -> bool:
    lowered = reply.lower()
    return any(item in lowered for item in expected)


def used(transcript: Transcript, names: tuple[str, ...]) -> int:
    return sum(len(transcript.calls(name)) for name in names)


def report(label: str, transcript: Transcript) -> None:
    calls = [call.name for turn in transcript.turns for call in turn.calls]
    print(f"\n[task-find] {label}: {len(calls)} tool calls, {used(transcript, SEARCH_TOOLS)} search: {calls}")


@pytest.mark.parametrize(
    ("question", "types", "needs_choice_ok"),
    [
        ("I need to weld two parts, where do I go?", ("welding_station",), True),
        ("where can I get coffee?", ("coffee_machine",), True),
        ("I want to cut a sheet of metal into shape", ("waterjet_cutter", "laser_cutter"), True),
        ("what does a press brake do and where is one?", ("press_brake",), True),
    ],
)
def test_task_questions_use_the_task_tool(question, types, needs_choice_ok):
    path, bm = factory()
    transcript = run_script(path, [question])
    report(question, transcript)
    reply = transcript.turns[0].reply
    assert used(transcript, TASK_TOOLS) >= 1, "neither find_for_task nor describe_asset was called"
    assert used(transcript, SEARCH_TOOLS) <= 3
    assert not any(call.is_error for turn in transcript.turns for call in turn.calls)
    assert names_a_place(reply, places(bm, *types)), f"reply names no real room for {types}: {reply[:300]}"
    assert not SPEC_WORDS.search(reply), f"reply states a spec: {reply[:300]}"


def test_hearsay_laser_cutter_in_hall_3_is_corrected():
    path, bm = factory()
    transcript = run_script(path, ["someone told me there is a laser cutter in hall 3, where is it?"])
    report("hearsay laser cutter", transcript)
    reply = transcript.turns[0].reply
    lowered = reply.lower()
    assert used(transcript, TASK_TOOLS) >= 1 and used(transcript, SEARCH_TOOLS) <= 3
    assert "waterjet" in lowered, reply[:300]
    assert names_a_place(reply, places(bm, "waterjet_cutter")), reply[:300]
    if "laser" in lowered:
        assert NEGATION.search(reply), f"reply may claim a laser cutter exists: {reply[:300]}"
    assert not re.search(r"\bthere is a laser cutter in hall 3\b", lowered)
    assert transcript.calls("find_route") or transcript.calls("give_directions") or OFFER.search(reply)
    assert not SPEC_WORDS.search(reply)
