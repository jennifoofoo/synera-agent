"""Eval of the Level 4 door suggestions. Free: no API, only cached extractions and artificial ones.

  uv run python scripts/eval_suggest.py                     # cached floors and 16 artificial floors x 3 seeds
  uv run python scripts/eval_suggest.py --set HUB_BONUS=2   # try another score weight

Artificial floors: a real dev floor turned into an extraction with 50 percent of the doors dropped (entrances kept),
converted, then suggested for. A suggestion is "real" when the original floor has a door between the same two rooms
(rooms matched by overlap). Judge metric: share of room pairs whose route scores at least 0.99 on the original."""

import argparse
import dataclasses
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from building_agent.level4 import stair_doors as stair_module
from building_agent.level4 import suggest as suggest_module
from building_agent.level4.convert import FloorInput, convert_floors_with_findings
from building_agent.level4.stair_doors import is_stair_hall, suggest_stair_doors
from building_agent.level4.suggest import apply_suggestions, suggest_doors
from building_agent.level4.validate import validate
from scripts.eval_level4 import DEFAULT_FLOORS, best_offset, cache_file, load_cached, parse_floors
from starter_agent.building_map import OUTSIDE
from tests.level4_helpers import floor_case, match_rooms, measure

ARTIFICIAL_FLOORS = [
    "proc-campus-dev-000:0",
    "proc-campus-dev-001:1",
    "proc-campus-dev-009:0",
    "proc-factory-dev-003:0",
    "proc-factory-dev-004:1",
    "resplan-439:0",
    "resplan-15179:0",
    "resplan-1677:0",
    "resplan-7336:0",
    "swiss-31:1",
    "swiss-2074:0",
    "swiss-450:1",
    "swiss-3254:0",
    "osm-way22744230:0",
    "osm-way27326387:0",
    "osm-way360544293:0",
]
DROP_SHARE = 0.5
SEEDS = (0, 1, 2)


def source_of(building_id: str) -> str:
    return building_id.split("-")[0].replace("proc", "procedural")


def unreachable(building: dict) -> int:
    return sum(len(f.items) for f in validate(building).items if f.code == "room_unreachable")


def drop_doors(case, seed: int):
    """Drop DROP_SHARE of the doors between rooms (entrances stay), reproducible per seed."""
    rng = random.Random(seed)
    kept = [d for d in case.extraction.doors if OUTSIDE in d.rooms or rng.random() >= DROP_SHARE]
    return dataclasses.replace(case, extraction=dataclasses.replace(case.extraction, doors=kept))


def run(case, converted: dict, name: str, source: str, suggester=suggest_doors) -> dict:
    matched = match_rooms(case, converted)
    truth_pairs = {frozenset(o["space_ids"]) for o in case.truth["openings"]}
    suggestions = suggester(converted)
    fixed = apply_suggestions(converted, suggestions)
    real = sum(
        s.first in matched and s.second in matched and frozenset((matched[s.first], matched[s.second])) in truth_pairs
        for s in suggestions
    )
    before_n, after_n = unreachable(converted), unreachable(fixed)
    rooms = len(converted["spaces"])
    return {
        "floor": name,
        "source": source,
        "rooms": rooms,
        "isolated": before_n,
        "suggested": len(suggestions),
        "real": real,
        "reach_before": 1 - before_n / rooms if rooms else 1.0,
        "reach_after": 1 - after_n / rooms if rooms else 1.0,
        "judge_before": measure(case, converted)["judge_full_share"],
        "judge_after": measure(case, fixed)["judge_full_share"],
    }


def cached_rows(floors: list[tuple[str, int]]) -> list[dict]:
    rows = []
    for building_id, level in floors:
        result = load_cached(cache_file(building_id, level))
        if result is None:
            continue
        case = floor_case(building_id, level)
        xs = [x for s in case.truth["spaces"] for x, _ in s["polygon"]]
        from building_agent.level4.convert import scale_from_known_length

        scale = scale_from_known_length(result.extraction, max(xs) - min(xs))
        converted, _ = convert_floors_with_findings(
            [FloorInput(level, result.extraction, scale)], building_id, building_id
        )
        case = dataclasses.replace(case, extraction=result.extraction, scale=scale)
        case = dataclasses.replace(case, offset=best_offset(case, converted))
        rows.append(run(case, converted, f"{building_id}:{level}", source_of(building_id)))
    return rows


def artificial_rows() -> list[dict]:
    rows = []
    for building_id, level in parse_floors(",".join(ARTIFICIAL_FLOORS)):
        for seed in SEEDS:
            case = drop_doors(floor_case(building_id, level, seed=seed), seed)
            converted, _ = convert_floors_with_findings(
                [FloorInput(level, case.extraction, case.scale)], building_id, building_id
            )
            rows.append(run(case, converted, f"{building_id}:{level}", source_of(building_id)))
    return rows


def pooled(rows: list[dict]) -> dict:
    total = {key: sum(r[key] for r in rows) for key in ("rooms", "isolated", "suggested", "real")}
    return {
        **total,
        "precision": total["real"] / total["suggested"] if total["suggested"] else float("nan"),
        "reach_before": statistics.mean(r["reach_before"] for r in rows),
        "reach_after": statistics.mean(r["reach_after"] for r in rows),
        "judge_before": statistics.mean(r["judge_before"] for r in rows),
        "judge_after": statistics.mean(r["judge_after"] for r in rows),
    }


def table(rows: list[dict], group_by: str) -> list[str]:
    lines = [
        f"| {group_by} | runs | isolated rooms | suggestions | real doors | precision | reachable before | after | judge >= 0.99 before | after |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row[group_by], []).append(row)
    for name, items in [*groups.items(), ("all", rows)]:
        p = pooled(items)
        lines.append(
            f"| {name} | {len(items)} | {p['isolated']} | {p['suggested']} | {p['real']} | {p['precision']:.0%} | "
            f"{p['reach_before']:.0%} | {p['reach_after']:.0%} | {p['judge_before']:.0%} | {p['judge_after']:.0%} |"
        )
    return lines


def stair_then_generic(building: dict) -> list:
    first = suggest_stair_doors(building)
    return first + suggest_doors(apply_suggestions(building, first))


SUGGESTERS = {"generic": suggest_doors, "stair": suggest_stair_doors, "stair then generic": stair_then_generic}


def drop_stair_doors(case):
    """The Swiss pattern: every door that touches a stair or lift space is missing (entrances stay)."""
    stairs = {f"r{i}" for i, space in enumerate(case.truth["spaces"]) if is_stair_hall(space)}
    kept = [d for d in case.extraction.doors if OUTSIDE in d.rooms or not stairs & set(d.rooms)]
    dropped = len(case.extraction.doors) - len(kept)
    return dataclasses.replace(case, extraction=dataclasses.replace(case.extraction, doors=kept), dropped_doors=dropped)


def stair_cached_rows(floors: list[tuple[str, int]]) -> list[dict]:
    """Cached model extractions after segmentation and markers, as in eval_level4 --segment --markers."""
    from building_agent.level4.convert import scale_from_known_length
    from building_agent.level4.markers import detect_markers, merge_markers
    from scripts.eval_level4 import apply_segment
    from tests.level4_helpers import DATA_DEV

    rows = []
    for building_id, level in floors:
        result = load_cached(cache_file(building_id, level))
        if result is None:
            continue
        result = apply_segment(result, building_id, level)
        merged, _ = merge_markers(
            result.extraction, detect_markers(DATA_DEV / building_id / f"floor_{level}_plain.png")
        )
        case = floor_case(building_id, level)
        xs = [x for s in case.truth["spaces"] for x, _ in s["polygon"]]
        scale = scale_from_known_length(merged, max(xs) - min(xs))
        converted, _ = convert_floors_with_findings([FloorInput(level, merged, scale)], building_id, building_id)
        case = dataclasses.replace(case, extraction=merged, scale=scale)
        case = dataclasses.replace(case, offset=best_offset(case, converted))
        for variant, suggester in SUGGESTERS.items():
            rows.append(
                {
                    **run(case, converted, f"{building_id}:{level}", source_of(building_id), suggester),
                    "variant": variant,
                }
            )
    return rows


def stair_drop_rows(split: str) -> list[dict]:
    """Every Swiss floor of a split (dev or train) with the stair doors dropped."""
    import tests.level4_helpers as helpers

    helpers.DATA_DEV = Path("data") / split
    rows = []
    try:
        for directory in sorted(helpers.DATA_DEV.glob("swiss-*")):
            for floor in helpers.load_building(directory.name)["floors"]:
                case = drop_stair_doors(floor_case(directory.name, floor["level"]))
                if not case.dropped_doors:
                    continue
                converted, _ = convert_floors_with_findings(
                    [FloorInput(floor["level"], case.extraction, case.scale)], directory.name, directory.name
                )
                for variant, suggester in SUGGESTERS.items():
                    row = run(case, converted, f"{directory.name}:{floor['level']}", split, suggester)
                    rows.append({**row, "variant": variant, "dropped": case.dropped_doors})
    finally:
        helpers.DATA_DEV = Path("data/dev")
    return rows


def stairs_report(arguments) -> None:
    cached = stair_cached_rows(parse_floors(",".join(DEFAULT_FLOORS)))
    print("Cached extractions after segment + markers\n")
    for variant in SUGGESTERS:
        rows = [r for r in cached if r["variant"] == variant]
        if arguments.summary:
            continue
        print(f"{variant}\n" + "\n".join(table(rows, "floor")) + "\n")
    for split in ("dev", "train"):
        rows = stair_drop_rows(split)
        print(f"\nSwiss {split} floors, stair doors dropped ({len({r['floor'] for r in rows})} floors)\n")
        for variant in SUGGESTERS:
            part = [r for r in rows if r["variant"] == variant]
            dropped, real = sum(r["dropped"] for r in part), sum(r["real"] for r in part)
            print(f"{variant}\n" + "\n".join(table(part, "source")))
            print(f"dropped stair doors {dropped}, restored {real} ({real / dropped:.0%} recall)\n")


def main() -> None:
    parser = argparse.ArgumentParser(prog="eval_suggest")
    parser.add_argument("--stairs", action="store_true", help="compare the stair hall rule on cached and Swiss floors")
    parser.add_argument("--set", action="append", default=[], help="override a score weight, e.g. HUB_BONUS=2")
    parser.add_argument("--summary", action="store_true", help="only the per-source tables")
    arguments = parser.parse_args()
    for item in arguments.set:
        key, value = item.split("=")
        setattr(stair_module if hasattr(stair_module, key) else suggest_module, key, float(value))
    if arguments.stairs:
        stairs_report(arguments)
        return
    cached = cached_rows(parse_floors(",".join(DEFAULT_FLOORS)))
    artificial = artificial_rows()
    print("Cached extractions (real vision output)\n")
    if not arguments.summary:
        print("\n".join(table(cached, "floor")) + "\n")
    print("\n".join(table(cached, "source")))
    print("\nArtificial extractions, 50 percent of the doors dropped\n")
    if not arguments.summary:
        print("\n".join(table(artificial, "floor")) + "\n")
    print("\n".join(table(artificial, "source")))


if __name__ == "__main__":
    main()
