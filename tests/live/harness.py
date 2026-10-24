"""Live conversation harness: run scripted user turns through one Agent and record what it did.

Assert on tool calls and applied changes (deterministic), not on wording. Transcripts are cached on disk,
keyed by script turns, model and prompt/tool version, so reruns without changes cost nothing."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import starter_agent.agent as starter_module
from building_agent import agent as agent_module
from building_agent import guide_tools, position_tools, walk
from building_agent.registry import load_kinds
from starter_agent.building_map import BuildingMap

LIVE_MODEL = "claude-sonnet-5-5"
LIVE_CACHE = Path("agent_output") / "live_cache"
LIVE_USAGE = Path("agent_output") / "live_usage.jsonl"  # one line of token counts per uncached script, for spend


@dataclass
class Call:
    name: str
    args: dict
    result: str = ""
    is_error: bool = False


@dataclass
class Turn:
    user: str
    reply: str
    calls: list[Call] = field(default_factory=list)

    def called(self, name: str) -> list[Call]:
        return [call for call in self.calls if call.name == name]


@dataclass
class Transcript:
    turns: list[Turn]

    def calls(self, name: str) -> list[tuple[int, Call]]:
        """(turn index, call) for every call of one tool over the whole conversation."""
        return [(index, call) for index, turn in enumerate(self.turns) for call in turn.called(name)]

    def applied_changes(self) -> list[int]:
        """Turn indices where confirm_change really changed the building."""
        applied = []
        for index, call in self.calls("confirm_change"):
            if not call.is_error and json.loads(call.result).get("applied") is True:
                applied.append(index)
        return applied

    def replies(self) -> list[str]:
        return [turn.reply for turn in self.turns]


def effective_start(bm: BuildingMap, transcript: Transcript, turn: int, call: Call) -> str | None:
    """Space id a route starts from: its start argument, else the position set before it (start left out)."""
    if call.args.get("start"):
        try:
            return bm.resolve_space(call.args["start"])
        except Exception:  # noqa: BLE001 - an unresolvable start is a test finding, not a crash here
            return None
    found = None
    for index, earlier in transcript.calls("set_position"):
        body = json.loads(earlier.result) if earlier.result and not earlier.is_error else {}
        if index <= turn and body.get("position") and not body.get("needs_choice"):
            found = body["position"]["space_id"]
    return found


def block_field(block, name: str):
    return block.get(name) if isinstance(block, dict) else getattr(block, name, None)


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(block_field(block, "text") or "" for block in content or [])


def calls_in(new_messages: list[dict]) -> list[Call]:
    """Pair tool_use blocks (assistant) with their tool_result blocks (next user message)."""
    calls: dict[str, Call] = {}
    ordered: list[Call] = []
    for message in new_messages:
        content = message["content"]
        if isinstance(content, str):
            continue
        for block in content:
            kind = block_field(block, "type")
            if kind == "tool_use":
                call = Call(block_field(block, "name"), dict(block_field(block, "input") or {}))
                calls[block_field(block, "id")] = call
                ordered.append(call)
            elif kind == "tool_result":
                call = calls.get(block_field(block, "tool_use_id"))
                if call is not None:
                    call.result = text_of(block_field(block, "content"))
                    call.is_error = bool(block_field(block, "is_error"))
    return ordered


def cache_file(building_directory: Path, user_turns: list[str], model: str) -> Path:
    version = (
        agent_module.CALCULATION_RULES
        + agent_module.CONVERSATION_RULES
        + json.dumps({name: kind.description for name, kind in load_kinds().items()}, sort_keys=True)
        + "".join(Path(module.__file__).read_text(encoding="utf-8") for module in (position_tools, walk, guide_tools))
    )
    raw = json.dumps([building_directory.name, user_turns, model, version])
    return LIVE_CACHE / f"{hashlib.sha256(raw.encode()).hexdigest()}.json"


def run_script(
    building_directory: Path, user_turns: list[str], model: str = LIVE_MODEL, use_cache: bool = True
) -> Transcript:
    """Play the user turns in order against one fresh agent on one building."""
    path = cache_file(building_directory, user_turns, model)
    if use_cache and path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        return Transcript([Turn(t["user"], t["reply"], [Call(**c) for c in t["calls"]]) for t in saved])
    previous_model = starter_module.MODEL
    starter_module.MODEL = model
    try:
        agent = agent_module.Agent(BuildingMap.load(building_directory), Path("agent_output") / "live_scratch")
        turns = []
        for user_text in user_turns:
            seen = len(agent.messages)
            reply = agent.ask(user_text)
            turns.append(Turn(user_text, reply, calls_in(agent.messages[seen:])))
        LIVE_USAGE.parent.mkdir(parents=True, exist_ok=True)
        with LIVE_USAGE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"turns": user_turns[:1], **agent.usage}) + "\n")
    finally:
        starter_module.MODEL = previous_model
    LIVE_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(turn) for turn in turns], ensure_ascii=False), encoding="utf-8")
    return Transcript(turns)


def dev_building(prefix: str) -> Path:
    """First dev building whose directory name starts with prefix (proc-, osm-, resplan-, swiss-)."""
    matches = sorted(path for path in Path("data/dev").iterdir() if path.name.startswith(prefix))
    if not matches:
        raise FileNotFoundError(f"no dev building starting with {prefix}")
    return matches[0]
