"""Check the warm-up questions (locate, count, route, route_step_free, route_with_closure, tour) on a split.

  uv run python scripts/eval_warmup.py data/dev --oracle          # tools only, free: proves the extraction
  uv run python scripts/eval_warmup.py data/train data/dev --routes   # routing vs the labels, free, per kind
  uv run --env-file .env python scripts/eval_warmup.py data/dev --limit 12   # our live agent, costs money

Route kinds are scored like Synera does (building_agent.judge_score: valid steps, labelled best length / our length
measured on the kit route model; OK means valid and score >= 0.99). Locate and count use the kit scorer. --kit-score also prints
the kit's length comparison for routes. The structured entry of the first questions is printed too."""

import argparse
import json
import random
import statistics
from collections import Counter
from pathlib import Path

import anthropic

import starter_agent.agent as starter_module
from benchmark.evaluate import PRICE_PER_MILLION
from building_agent import routing
from building_agent.agent import Session
from building_agent.judge_score import FULL_MARKS, ROUTE_KINDS, score_route
from building_agent.structured import route_entry, structured_entry
from starter_agent.building_map import BuildingMap, MapError
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


def run(
    directory: Path,
    limit: int | None,
    per_kind: int | None,
    oracle: bool,
    kind: str | None,
    max_dollars: float,
    kit_score: bool = False,
) -> None:
    results: Counter[tuple[str, bool]] = Counter()
    route_scores: dict[str, list[float]] = {}
    judge_maps: dict[Path, BuildingMap] = {}
    usage: Counter[str] = Counter()
    shown = 0
    questions = load_questions(directory, None)
    if kind:
        questions = [item for item in questions if item[1]["kind"] == kind]
    if per_kind:
        questions = sample_per_kind(questions, per_kind)
    if limit:
        questions = questions[:limit]
    for building_directory, question in questions:
        bm = routing.load_map(building_directory)
        if oracle:
            reply = oracle_answer(question, bm)
        else:
            # The warm-up measures the benchmark kinds: Opus (the starter's model, or --model), not the page chat model.
            session = Session(
                bm, OUTPUT_DIRECTORY / building_directory.name, model=starter_module.MODEL, effort=starter_module.EFFORT
            )
            try:
                reply = session.ask(question["question"])
            except anthropic.APIError as error:
                print(f"[warmup] {question['id']}: API error {error}")
                reply = ""
            usage.update(session.usage)
            if dollars(usage) > max_dollars:
                print(f"[warmup] stopping: estimated cost ${dollars(usage):.2f} passed --max-dollars {max_dollars}")
                break
        detail = ""
        if question["kind"] in ROUTE_KINDS:
            fresh = judge_maps.get(building_directory) or judge_maps.setdefault(
                building_directory, routing.load_map(building_directory)
            )
            judged = score_route(fresh, route_entry(bm), question)
            correct = judged.valid and judged.score >= FULL_MARKS
            route_scores.setdefault(question["kind"], []).append(judged.score)
            detail = f" score {judged.score:.3f}  {judged.reason}"
            if kit_score:
                detail += f"  [kit: {'OK' if score(question, bm, reply) else 'BAD'}]"
        else:
            correct = score(question, bm, reply)
        results[(question["kind"], correct)] += 1
        print(f"[warmup] {question['id']:40s} {question['kind']:20s} {'OK ' if correct else 'BAD'}{detail}")
        if shown < SHOWN:
            print(json.dumps(structured_entry(question["id"], question["kind"], bm, reply), ensure_ascii=False)[:400])
            shown += 1
    print("\nkind                  correct / total")
    for name in sorted({name for name, _ in results}):
        print(f"  {name:20s} {results[(name, True)]:4d} / {results[(name, True)] + results[(name, False)]}")
    print(f"  {'all':20s} {sum(c for (_, ok), c in results.items() if ok):4d} / {sum(results.values())}")
    if route_scores:
        print("\nkind                  mean score")
        for name in sorted(route_scores):
            print(f"  {name:20s} {sum(route_scores[name]) / len(route_scores[name]):.3f}")
    if usage:
        print(f"tokens: {dict(usage)}  estimated cost: ${dollars(usage):.2f} (Opus prices, even if --model is cheaper)")


def route_agreement(directories: list[Path]) -> None:
    """Free check of building_agent.routing against the labelled route answers: per kind the share with full
    marks (Synera-style judge), the share where reachability agrees, and our length relative to the label."""
    rows: dict[str, list[tuple[bool, bool, float | None]]] = {}
    for directory in directories:
        for building_directory, question in load_questions(directory, None):
            kind, answer = question["kind"], question["answer"]
            if kind not in ROUTE_KINDS:
                continue
            bm = routing.load_map(building_directory)
            if answer.get("closed_element_id"):
                bm.closed.add(answer["closed_element_id"])
            labelled = answer.get("reachable") is not False
            try:
                if kind == "tour":
                    routing.route(bm, answer["stops"][0], answer["stops"][-1], via=answer["stops"][1:-1])
                else:
                    routing.route(bm, answer["from_space_id"], answer["to_space_id"], kind == "route_step_free")
            except MapError:
                bm.last_route = None
            judged = score_route(routing.load_map(building_directory), route_entry(bm), question)
            ratio = None
            if labelled and bm.last_route and answer["optimal_length_m"]:
                ratio = bm.last_route.length_m / answer["optimal_length_m"]
            rows.setdefault(kind, []).append(
                (judged.valid and judged.score >= FULL_MARKS, (bm.last_route is not None) == labelled, ratio)
            )
    print("kind                  n  full marks  reachability  length vs label (median, worst)")
    for kind, items in sorted(rows.items()):
        ratios = [ratio for _, _, ratio in items if ratio is not None]
        worst = max(ratios, key=lambda value: abs(value - 1))
        print(
            f"  {kind:20s} {len(items):4d}  {sum(item[0] for item in items) / len(items):8.1%}  "
            f"{sum(item[1] for item in items) / len(items):10.1%}  {statistics.median(ratios):.4f}, {worst:.4f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(prog="eval_warmup")
    parser.add_argument("directory", type=Path, nargs="+", help="a split directory (--routes accepts several)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--per-kind", type=int, default=None, help="sample N questions per kind (seeded)")
    parser.add_argument("--model", default=None, help="override the agent model (default: the agent's own)")
    parser.add_argument("--kind", default=None, help="only one question kind, e.g. route_with_closure")
    parser.add_argument("--max-dollars", type=float, default=3.0, help="stop a live run above this estimate")
    parser.add_argument("--routes", action="store_true", help="free: routing agreement with the route labels")
    parser.add_argument("--oracle", action="store_true", help="tools only, no API calls")
    parser.add_argument("--kit-score", action="store_true", help="also print the kit's length comparison for routes")
    arguments = parser.parse_args()
    if arguments.routes:
        route_agreement(arguments.directory)
        return
    if len(arguments.directory) > 1:
        parser.error("several directories are only for --routes")
    for name in ("limit", "per_kind"):
        value = getattr(arguments, name)
        if value is not None and value < 1:
            parser.error(f"--{name.replace('_', '-')} must be at least 1")
    if not arguments.oracle and arguments.limit is None and arguments.per_kind is None and not arguments.kind:
        parser.error("a live run needs --limit, --per-kind or --kind (it costs money); use --oracle for the free check")
    if arguments.model:
        starter_module.MODEL = arguments.model
    run(
        arguments.directory[0],
        arguments.limit,
        arguments.per_kind,
        arguments.oracle,
        arguments.kind,
        arguments.max_dollars,
        arguments.kit_score,
    )


if __name__ == "__main__":
    main()
