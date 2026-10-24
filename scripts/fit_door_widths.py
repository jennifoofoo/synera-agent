"""Fit the door width table (building_agent/level4/door_width_table.json) on the labelled train buildings and report
how the estimator does on held-out buildings.

  uv run python scripts/fit_door_widths.py            # fit on data/train, write the table, score on data/dev
  uv run python scripts/fit_door_widths.py --no-write # only score

Scores: share of doors whose class (>= 1.0 m and >= 1.1 m) is right, and exact agreement of the labelled
wide_delivery_count questions when the widths of the true building are replaced by the estimate. Compared with the
constant 0.9 m. Also leave-one-building-out over train and dev for the table rule (the table of all other buildings)."""

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import networkx as nx

from building_agent.level4 import door_widths
from starter_agent.building_map import DOOR_PREFIX, BuildingMap

DATA = Path("data")
THRESHOLDS = (1.0, 1.1)


def key_of(opening: dict, spaces: dict[str, dict]) -> str | None:
    fine = [door_widths.side_labels(spaces.get(i))[1] for i in opening["space_ids"]]
    if len(fine) != 2 or not fine[0] or not fine[1] or opening["kind"] not in ("door", "opening"):
        return None
    return door_widths.table_key(opening["kind"], fine[0], fine[1])


def collect(split: str) -> list[tuple[Path, dict]]:
    return [(d, json.loads((d / "building.json").read_text())) for d in sorted((DATA / split).iterdir())]


def counts_per_key(buildings: list[tuple[Path, dict]]) -> dict[str, list[tuple[str, float]]]:
    found: dict[str, list[tuple[str, float]]] = collections.defaultdict(list)
    for directory, data in buildings:
        spaces = {s["id"]: s for s in data["spaces"]}
        for opening in data["openings"]:
            key = key_of(opening, spaces)
            if key:
                found[key].append((directory.name, opening["width_m"]))
    return found


def table_from(found: dict[str, list[tuple[str, float]]], skip: str | None = None) -> dict[str, float]:
    table = {}
    for key, items in found.items():
        widths = [w for name, w in items if name != skip]
        if len(widths) >= door_widths.MIN_TABLE_COUNT:
            table[key] = round(statistics.median(widths), 3)
    return table


def estimated(data: dict, table: dict[str, float]) -> dict[str, float]:
    spaces = {s["id"]: s for s in data["spaces"]}
    return {
        o["id"]: door_widths.estimate(o["kind"], [spaces.get(i) for i in o["space_ids"]], table).width_m
        for o in data["openings"]
    }


def answer(bm: BuildingMap, widths: dict[str, float], inputs: dict) -> int:
    graph = bm.graph(step_free=True)
    graph.remove_nodes_from([DOOR_PREFIX + i for i, w in widths.items() if w < inputs["min_width"] - 1e-9])
    reachable = nx.node_connected_component(graph, inputs["start"])
    return sum(
        1
        for s in reachable
        if s in bm.spaces and bm.spaces[s]["floor_id"] == inputs["floor_id"] and bm.spaces[s]["type"] == "room"
    )


def score(label: str, buildings: list[tuple[Path, dict]], widths_for) -> None:
    hits = total = door_hits = door_total = 0
    for directory, data in buildings:
        questions = [
            q
            for q in map(json.loads, (directory / "questions.jsonl").read_text().splitlines())
            if q["kind"] == "wide_delivery_count"
        ]
        widths = widths_for(directory.name, data)
        for opening in data["openings"]:
            for threshold in THRESHOLDS:
                door_total += 1
                door_hits += (widths[opening["id"]] >= threshold - 1e-9) == (opening["width_m"] >= threshold - 1e-9)
        if questions:
            bm = BuildingMap.load(directory)
            for q in questions:
                total += 1
                hits += answer(bm, widths, q["inputs"]) == q["answer"]["value"]
    print(f"{label:34s} wide_delivery {hits}/{total}  door classes {door_hits / max(door_total, 1):.3f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    train, dev = collect("train"), collect("dev")
    table = table_from(counts_per_key(train))
    if not args.no_write:
        payload = {
            "fitted_on": "data/train",
            "min_count": door_widths.MIN_TABLE_COUNT,
            "widths": dict(sorted(table.items())),
        }
        door_widths.TABLE_PATH.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {len(table)} keys to {door_widths.TABLE_PATH}")
    print(f"--- held out: table fitted on train, scored on dev ({len(dev)} buildings)")
    score("constant 0.9", dev, lambda name, data: {o["id"]: 0.9 for o in data["openings"]})
    score("estimator, plan colours only", dev, lambda name, data: estimated(data, {}))  # no room types
    score("estimator, with room types", dev, lambda name, data: estimated(data, table))
    print("--- leave one building out, train + dev")
    both = train + dev
    found = counts_per_key(both)
    score("estimator, with room types", both, lambda name, data: estimated(data, table_from(found, skip=name)))


if __name__ == "__main__":
    main()
