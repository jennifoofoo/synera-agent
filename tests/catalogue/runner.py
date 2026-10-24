"""Run catalogue items live against the agent and score them (cached through tests/live/harness.py).

    uv run --env-file .env python -m tests.catalogue.runner data/dev/proc-factory-dev-003 --sample 26 --max-usd 1.5

Spend is estimated from agent_output/live_usage.jsonl at Sonnet list prices (an assumption, not an invoice) and the
run stops before a script that would start over --max-usd. Every item is one fresh agent (all its turns)."""

import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tests.catalogue.generate import build
from tests.catalogue.scoring import score
from tests.live.harness import LIVE_MODEL, LIVE_USAGE, cache_file, run_script

PRICE_PER_MILLION = {
    "input_tokens": 3.0,
    "output_tokens": 15.0,
    "cache_read_input_tokens": 0.30,
    "cache_creation_input_tokens": 3.75,
}
RESULTS = Path("agent_output") / "catalogue_results.jsonl"


def usage_dollars(lines: list[dict]) -> float:
    return sum(sum(line.get(key, 0) * price for key, price in PRICE_PER_MILLION.items()) for line in lines) / 1e6


def usage_lines() -> list[dict]:
    if not LIVE_USAGE.exists():
        return []
    return [json.loads(line) for line in LIVE_USAGE.read_text(encoding="utf-8").splitlines() if line.strip()]


def stratified(items: list[dict], count: int) -> list[dict]:
    """Round-robin over (persona, intent) groups so every persona and intent is touched before any is repeated."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        if item["persona"] == "benchmark" and "Finish with a line" in item["text"]:
            continue  # the canonical sentence is answered by the deterministic parser, not the model
        groups.setdefault((item["persona"], item["kind_or_intent"]), []).append(item)
    picked: list[dict] = []
    while len(picked) < min(count, len(items)):
        for key in list(groups):
            if groups[key] and len(picked) < count:
                picked.append(groups[key].pop(0))
    return picked


def known_names(directory: Path) -> set[str]:
    from building_agent import routing

    bm = routing.load_map(directory)
    names = {s["name"] for s in bm.spaces.values()} | {a["name"] for a in bm.assets.values()}
    return names | {c["name"] for c in bm.connectors.values()} | {f["name"] for f in bm.floors.values()}


def previous_turns(directory: Path, source: Path) -> set[tuple[str, ...]]:
    if not source.exists():
        return set()
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {tuple(r["turns"]) for r in rows if r["building"] == directory.name}


def run(
    directory: Path,
    count: int,
    max_usd: float,
    only: set[str] | None,
    workers: int = 3,
    rescore: Path | None = None,
) -> list[dict]:
    items = build(directory)
    if rescore:  # the items a file of earlier results holds (same turns), scored again from the cache
        seen = previous_turns(directory, rescore)
        chosen = [i for i in items if tuple(i["turns"]) in seen or (only and i["id"] in only)]
    else:
        chosen = [i for i in items if i["id"] in only] if only else stratified(items, count)
    names = known_names(directory)
    baseline = len(usage_lines())
    lock = threading.Lock()
    results: list[dict] = []
    stopped = {"flag": False}

    def spent() -> float:
        return usage_dollars(usage_lines()[baseline:])

    def work(item: dict) -> dict | None:
        with lock:
            if stopped["flag"] or spent() > max_usd:
                stopped["flag"] = True
                return None
        cached = cache_file(directory, item["turns"], LIVE_MODEL).exists()
        try:
            transcript = run_script(directory, item["turns"])
        except Exception as error:  # noqa: BLE001 - an API or agent crash is a finding, not a stop
            return {
                **item,
                "building": directory.name,
                "passed": False,
                "reasons": [f"crash: {type(error).__name__}: {str(error)[:120]}"],
                "replies": [],
                "calls": [],
                "cached": cached,
            }
        verdict = score(item, transcript, names)
        return {
            **item,
            "building": directory.name,
            **verdict,
            "replies": transcript.replies(),
            "calls": [
                [turn_index, call.name, call.is_error]
                for turn_index, turn in enumerate(transcript.turns)
                for call in turn.calls
            ],
            "cached": cached,
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(work, chosen):
            if result is not None:
                results.append(result)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    new = usage_lines()[baseline:]
    print(
        f"{directory.name}: ran {len(results)}/{len(chosen)} items, {len(new)} uncached scripts, estimated ${usage_dollars(new):.2f}"
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("building", type=Path)
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--max-usd", type=float, default=1.0)
    parser.add_argument("--ids", default="", help="comma separated item ids instead of a sample")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--rescore", type=Path, help="results file: score the items it holds again, from the cache")
    args = parser.parse_args()
    only = set(filter(None, args.ids.split(","))) or None
    run(args.building, args.sample, args.max_usd, only, args.workers, args.rescore)


if __name__ == "__main__":
    main()
