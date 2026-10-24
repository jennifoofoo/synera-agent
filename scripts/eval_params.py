"""Can a cheap LLM read the tool parameters out of the question text?

uv run --env-file .env python scripts/eval_params.py --per-kind 5
One forced tool call per question, nothing is executed. Responses are cached in agent_output/params_cache/."""

import argparse
import json
import random
import re
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from building_agent.agent import overview_with_floor_ids
from building_agent.params_eval import compare_params
from building_agent.registry import load_kinds
from building_agent.tools import kind_tool
from starter_agent.building_map import BuildingMap
from tests.conftest import labelled_questions

MODEL = "claude-haiku-5-5"
CACHE = Path("agent_output") / "params_cache"
SYSTEM = (
    "You pick the right tool for a question about one building and fill in its parameters from the question text. "
    "You only see the building overview, not the room list. Floor parameters take the floor id from the overview. "
    "For room parameters pass the room name or number exactly as written in the question if you do not know its id.\n\n"
    "Building overview:\n{overview}"
)


def cache_path(question_id: str) -> Path:
    return CACHE / f"{question_id}__{re.sub(r'[^A-Za-z0-9._-]', '_', MODEL)}.json"


def ask_model(client: anthropic.Anthropic, bm: BuildingMap, tools: list[dict], text: str) -> dict:
    overview = json.dumps(overview_with_floor_ids(bm), ensure_ascii=False)
    message = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SYSTEM.format(overview=overview),
        tools=tools,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": text}],
    )
    call = next((block for block in message.content if block.type == "tool_use"), None)
    return {"tool": call.name if call else None, "input": call.input if call else {}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-kind", type=int, default=5)
    parser.add_argument("--max-calls", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    kinds = load_kinds()
    tools = [kind_tool(None, kind).to_dict() for kind in kinds.values()]
    client = anthropic.Anthropic(max_retries=0)
    CACHE.mkdir(parents=True, exist_ok=True)
    maps: dict[str, BuildingMap] = {}
    calls = 0
    stopped = None

    for name in kinds:
        questions = labelled_questions(name)
        sample = random.Random(args.seed).sample(questions, min(args.per_kind, len(questions)))
        tool_ok = params_ok = done = 0
        mismatches = []
        for building, question in sample:
            bm = maps.setdefault(building, BuildingMap.load(Path(building)))
            path = cache_path(question["id"])
            if path.exists():
                response = json.loads(path.read_text())
            else:
                if calls >= args.max_calls:
                    stopped = f"max-calls ({args.max_calls}) reached"
                    break
                try:
                    calls += 1
                    response = ask_model(client, bm, tools, question["question"])
                except anthropic.APIError as error:
                    stopped = f"API error: {type(error).__name__}: {str(error)[:200]}"
                    break
                path.write_text(json.dumps(response))
            done += 1
            if response["tool"] == name:
                tool_ok += 1
                diff = compare_params(bm, question["inputs"], response["input"])
                params_ok += not diff
                mismatches += [(question["id"], key, exp, got) for key, exp, got in diff]
            else:
                mismatches.append((question["id"], "TOOL", name, response["tool"]))
        print(f"{name:20} n={done}  tool correct {tool_ok}/{done}  all params correct {params_ok}/{done}")
        for question_id, key, expected, got in mismatches:
            print(f"    {question_id}  {key}: expected {expected!r}, got {got!r}")
        if stopped:
            break
    print(f"\nAPI calls this run: {calls} (cache: {CACHE})")
    if stopped:
        print(f"STOPPED: {stopped}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
