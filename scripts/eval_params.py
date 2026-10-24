"""Can a cheap LLM read the tool parameters out of the question text?

uv run --env-file .env python scripts/eval_params.py --per-kind 5   (or --all --max-calls 600)
uv run --env-file .env python scripts/eval_params.py --split test --max-calls 200   (unlabelled test questions, checked without labels)
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
from building_agent.params_eval import (
    building_source,
    check_unlabelled,
    compare_params,
    estimate_cost,
    group_mismatches,
)
from building_agent.registry import load_kinds
from building_agent.tools import kind_tool
from starter_agent.building_map import BuildingMap
from tests.conftest import DATA, labelled_questions

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
    usage = {"input_tokens": message.usage.input_tokens, "output_tokens": message.usage.output_tokens}
    return {"tool": call.name if call else None, "input": call.input if call else {}, "usage": usage}


def test_questions() -> list[tuple[str, dict]]:
    found = []
    for path in sorted((DATA / "test").glob("*/questions.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                found.append((str(path.parent), json.loads(line)))
    return found


def share(rows: list[bool]) -> str:
    return f"{sum(rows)}/{len(rows)} ({100 * sum(rows) / len(rows):.0f}%)" if rows else "-"


def run_test_split(client: anthropic.Anthropic, tools: list[dict], max_calls: int) -> int:
    """Ask the model for every unlabelled test question and check the output without labels."""
    schemas = {tool["name"]: tool["input_schema"] for tool in tools}
    CACHE.mkdir(parents=True, exist_ok=True)
    maps: dict[str, BuildingMap] = {}
    calls = 0
    stopped = None
    run_tokens = [0, 0]
    all_tokens = [0, 0]
    results = []
    for building, question in test_questions():
        bm = maps.setdefault(building, BuildingMap.load(Path(building)))
        path = cache_path(question["id"])
        if path.exists():
            response = json.loads(path.read_text())
        else:
            if calls >= max_calls:
                stopped = f"max-calls ({max_calls}) reached"
                break
            try:
                calls += 1
                response = ask_model(client, bm, tools, question["question"])
            except anthropic.APIError as error:
                stopped = f"API error: {type(error).__name__}: {str(error)[:200]}"
                break
            path.write_text(json.dumps(response))
            run_tokens[0] += response["usage"]["input_tokens"]
            run_tokens[1] += response["usage"]["output_tokens"]
        all_tokens[0] += response["usage"]["input_tokens"]
        all_tokens[1] += response["usage"]["output_tokens"]
        reasons = check_unlabelled(
            bm, question["kind"], question["question"], response, schemas.get(question["kind"], {})
        )
        results.append((question, response, reasons))

    for title, key in (("kind", lambda q: q["kind"]), ("source", lambda q: building_source(q["building_id"]))):
        print(f"\nUsable share per {title}:")
        for value in sorted({key(q) for q, _, _ in results}):
            print(f"  {value:22} {share([not r for q, _, r in results if key(q) == value])}")
    print(f"\nOverall usable: {share([not r for _, _, r in results])}")
    bad = [item for item in results if item[2]]
    print(f"\nUnusable questions ({len(bad)}):")
    for question, response, reasons in bad:
        print(f"  {question['id']}  [{question['building_id']}]  kind={question['kind']}")
        print(f"      question: {question['question']}")
        print(f"      model: {response['tool']} {json.dumps(response['input'], ensure_ascii=False)}")
        for reason in reasons:
            print(f"      reason: {reason}")
    print(f"\nAPI calls this run: {calls} (cache: {CACHE})")
    print(f"Tokens this run: {run_tokens[0]} in / {run_tokens[1]} out, est. ${estimate_cost(*run_tokens):.4f}")
    print(
        f"Tokens incl. cached responses: {all_tokens[0]} in / {all_tokens[1]} out, est. ${estimate_cost(*all_tokens):.4f} ({MODEL})"
    )
    if stopped:
        print(f"STOPPED: {stopped}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-kind", default="5", help="questions per kind, or 'all'")
    parser.add_argument("--all", action="store_true", help="same as --per-kind all")
    parser.add_argument("--max-calls", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--split",
        choices=["train", "test"],
        default="train",
        help="train = labelled train/dev, test = unlabelled test questions",
    )
    args = parser.parse_args()
    per_kind = None if args.all or args.per_kind == "all" else int(args.per_kind)

    kinds = load_kinds()
    tools = [kind_tool(None, kind).to_dict() for kind in kinds.values()]
    client = anthropic.Anthropic(max_retries=0)
    if args.split == "test":
        return run_test_split(client, tools, args.max_calls)
    CACHE.mkdir(parents=True, exist_ok=True)
    maps: dict[str, BuildingMap] = {}
    calls = 0
    stopped = None
    run_tokens = [0, 0]
    all_tokens = [0, 0]
    total_questions = 0
    all_mismatches = []
    bm_for = {}

    for name in kinds:
        questions = labelled_questions(name)
        sample = (
            questions if per_kind is None else random.Random(args.seed).sample(questions, min(per_kind, len(questions)))
        )
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
                run_tokens[0] += response["usage"]["input_tokens"]
                run_tokens[1] += response["usage"]["output_tokens"]
            usage = response.get("usage")
            if usage:
                all_tokens[0] += usage["input_tokens"]
                all_tokens[1] += usage["output_tokens"]
            done += 1
            bm_for[question["id"]] = bm
            if response["tool"] == name:
                tool_ok += 1
                diff = compare_params(bm, question["inputs"], response["input"])
                params_ok += not diff
                mismatches += [(question["id"], key, exp, got) for key, exp, got in diff]
            else:
                mismatches.append((question["id"], "TOOL", name, response["tool"]))
        total_questions += done
        all_mismatches += [(name, *m) for m in mismatches]
        print(f"{name:20} n={done}  tool correct {tool_ok}/{done}  all params correct {params_ok}/{done}")
        for question_id, key, expected, got in mismatches:
            print(f"    {question_id}  {key}: expected {expected!r}, got {got!r}")
        if stopped:
            break
    print(f"\nQuestions evaluated: {total_questions}")
    groups = group_mismatches(bm_for, all_mismatches)
    print(f"\nMismatch patterns ({len(all_mismatches)} total):")
    for label, items in groups.items():
        print(f"  {len(items):4}  {label}")
        for kind, question_id, key, expected, got in items[:2]:
            print(f"          e.g. {kind} {question_id} {key}: expected {expected!r}, got {got!r}")
    print(f"\nAPI calls this run: {calls} (cache: {CACHE})")
    print(f"Tokens this run: {run_tokens[0]} in / {run_tokens[1]} out, est. ${estimate_cost(*run_tokens):.4f}")
    print(
        f"Tokens incl. cached responses: {all_tokens[0]} in / {all_tokens[1]} out, est. ${estimate_cost(*all_tokens):.4f} ({MODEL})"
    )
    if stopped:
        print(f"STOPPED: {stopped}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
