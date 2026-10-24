"""Check the warm-up questions (locate, count, route, route_step_free, route_with_closure, tour) on a split.

  uv run python scripts/eval_warmup.py data/dev --oracle          # tools only, free: proves the extraction
  uv run --env-file .env python scripts/eval_warmup.py data/dev --limit 12   # our live agent, costs money

Both modes score like the kit (starter_agent.evaluate.score) and also print the structured entry of the first
questions so the answers.json shape is visible."""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import anthropic

import starter_agent.agent as starter_module
from benchmark.evaluate import PRICE_PER_MILLION
from building_agent.agent import Session
from building_agent.structured import structured_entry
from starter_agent.building_map import BuildingMap
from starter_agent.evaluate import load_questions, oracle_answer, score

OUTPUT_DIRECTORY = Path("agent_output") / "warmup"
SHOWN = 3


def dollars(usage: Counter) -> float:
    return sum(usage[name] * price / 1_000_000 for name, price in PRICE_PER_MILLION.items())


def sample_per_kind(questions: list, per_kind: int) -> list:
    by_kind: dict[str, list] = {}
    for item in questions:
        by_kind.setdefault(item[1]["kind"], []).append(item)
    rng = random.Random(7)
    return [item for kind in sorted(by_kind) for item in rng.sample(by_kind[kind], min(per_kind, len(by_kind[kind])))]


def run(directory: Path, limit: int | None, per_kind: int | None, oracle: bool) -> None:
    results: Counter[tuple[str, bool]] = Counter()
    usage: Counter[str] = Counter()
    shown = 0
    questions = load_questions(directory, limit)
    if per_kind:
        questions = sample_per_kind(questions, per_kind)
    for building_directory, question in questions:
        bm = BuildingMap.load(building_directory)
        if oracle:
            reply = oracle_answer(question, bm)
        else:
            session = Session(bm, OUTPUT_DIRECTORY / building_directory.name)
            try:
                reply = session.ask(question["question"])
            except anthropic.APIError as error:
                print(f"[warmup] {question['id']}: API error {error}")
                reply = ""
            usage.update(session.usage)
        correct = score(question, bm, reply)
        results[(question["kind"], correct)] += 1
        print(f"[warmup] {question['id']:40s} {question['kind']:20s} {'OK ' if correct else 'BAD'}")
        if shown < SHOWN:
            print(json.dumps(structured_entry(question["id"], question["kind"], bm, reply), ensure_ascii=False)[:400])
            shown += 1
    print("\nkind                  correct / total")
    for kind in sorted({kind for kind, _ in results}):
        print(f"  {kind:20s} {results[(kind, True)]:4d} / {results[(kind, True)] + results[(kind, False)]}")
    print(f"  {'all':20s} {sum(c for (_, ok), c in results.items() if ok):4d} / {sum(results.values())}")
    if usage:
        print(f"tokens: {dict(usage)}  estimated cost: ${dollars(usage):.2f} (Opus prices, even if --model is cheaper)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="eval_warmup")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--per-kind", type=int, default=None, help="sample N questions per kind (seeded)")
    parser.add_argument("--model", default=None, help="override the agent model (default: the agent's own)")
    parser.add_argument("--oracle", action="store_true", help="tools only, no API calls")
    arguments = parser.parse_args()
    if not arguments.oracle and arguments.limit is None and arguments.per_kind is None:
        parser.error("a live run needs --limit N or --per-kind N (it costs money); use --oracle for the free check")
    if arguments.model:
        starter_module.MODEL = arguments.model
    run(arguments.directory, arguments.limit, arguments.per_kind, arguments.oracle)


if __name__ == "__main__":
    main()
