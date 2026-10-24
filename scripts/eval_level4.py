"""Level 4 eval: extract (vision) + convert + validate on dev floors, measured against the original building.

  uv run --env-file .env python scripts/eval_level4.py                       # 8 default floors, cached, max $2
  uv run --env-file .env python scripts/eval_level4.py --floors resplan-439,swiss-31:1 --max-dollars 0.5

The raw extraction of each image is cached under agent_output/level4_cache, so a repeat run costs nothing.
The scale is the true width of the floor (as in the spike), so this measures extraction quality, not the scale.
Results are appended to docs/eval-log.md under the heading "Level 4"."""

import argparse
import dataclasses
import datetime
import hashlib
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from building_agent.level4 import extract as extract_module
from building_agent.level4.convert import FloorInput, convert_floors_with_findings, scale_from_known_length
from building_agent.level4.extract import DEFAULT_MODEL, ExtractError, ExtractResult, extract_floor
from building_agent.level4.schema import ExtractedDoor, ExtractedRoom, Extraction
from building_agent.level4.validate import validate
from tests.level4_helpers import DATA_DEV, floor_case, measure

CACHE_DIRECTORY = Path("agent_output") / "level4_cache"
EVAL_LOG = Path("docs") / "eval-log.md"
HEADING = "## Level 4"
DEFAULT_FLOORS = [
    "proc-campus-dev-000:0",
    "proc-campus-dev-001:0",
    "proc-factory-dev-003:0",
    "resplan-439:0",
    "resplan-1465:0",
    "swiss-31:0",
    "swiss-203:0",
    "osm-way27326387:0",
]
ESTIMATE_PER_FLOOR_USD = 0.05
PROMPT_HASH = hashlib.sha256(extract_module.PROMPT.encode()).hexdigest()[:8]
# Acceptance targets of docs/specs/level4.md (clean = procedural and ResPlan floors)
TARGETS = {"recall": 0.95, "precision": 0.95, "door_recall": 0.90, "area_err": 0.03, "route_err": 0.03}


def parse_floors(text: str | None) -> list[tuple[str, int]]:
    items = [item.strip() for item in (text.split(",") if text else DEFAULT_FLOORS) if item.strip()]
    return [(item.split(":")[0], int(item.split(":")[1]) if ":" in item else 0) for item in items]


def group_of(building_id: str) -> str:
    if building_id.startswith(("proc-", "resplan-")):
        return "clean"
    return "swiss" if building_id.startswith("swiss-") else "other"


def cache_file(building_id: str, level: int) -> Path:
    return CACHE_DIRECTORY / f"{building_id}_{level}_{PROMPT_HASH}.json"


def load_cached(path: Path) -> ExtractResult | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    data = raw["extraction"]
    extraction = Extraction(
        data["width_px"],
        data["height_px"],
        [ExtractedRoom(**room) for room in data["rooms"]],
        [ExtractedDoor(**{**door, "rooms": tuple(door["rooms"])}) for door in data["doors"]],
        data.get("scale_bar_px"),
        data.get("scale_bar_m"),
    )
    return ExtractResult(
        extraction, **{key: raw[key] for key in ("input_tokens", "output_tokens", "seconds", "cost_usd")}
    )


def store(path: Path, result: ExtractResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = {key: getattr(result, key) for key in ("input_tokens", "output_tokens", "seconds", "cost_usd")}
    raw["extraction"] = dataclasses.asdict(result.extraction)
    path.write_text(json.dumps(raw), encoding="utf-8")


def best_offset(case, converted: dict) -> tuple[float, float]:
    """The image frame is unknown, so align the extracted outline to the true one (corner or centre, whichever
    matches more rooms). Only the frame is fitted, never the shapes."""
    from tests.level4_helpers import match_rooms

    def box(spaces):
        xs = [x for s in spaces for x, _ in s["polygon"]]
        ys = [y for s in spaces for _, y in s["polygon"]]
        return min(xs), min(ys), max(xs), max(ys)

    truth, found = box(case.truth["spaces"]), box(converted["spaces"])
    options = [
        (found[0] - truth[0], found[1] - truth[1]),
        ((found[0] + found[2]) / 2 - (truth[0] + truth[2]) / 2, (found[1] + found[3]) / 2 - (truth[1] + truth[3]) / 2),
    ]
    scored = []
    for offset in options:
        trial = dataclasses.replace(case, offset=offset)
        scored.append((len(match_rooms(trial, converted)), offset))
    return max(scored, key=lambda item: item[0])[1]


def evaluate_floor(building_id: str, level: int, result: ExtractResult) -> dict:
    case = floor_case(building_id, level)
    xs = [x for s in case.truth["spaces"] for x, _ in s["polygon"]]
    scale = scale_from_known_length(result.extraction, max(xs) - min(xs))
    converted, convert_findings = convert_floors_with_findings(
        [FloorInput(level, result.extraction, scale)], building_id, building_id
    )
    findings = validate(converted)
    case = dataclasses.replace(case, extraction=result.extraction, scale=scale)
    case = dataclasses.replace(case, offset=best_offset(case, converted))
    measured = measure(case, converted)
    codes = {finding.code for finding in [*convert_findings.items, *findings.items]}
    return {
        "floor": f"{building_id}:{level}",
        "group": group_of(building_id),
        "rooms": f"{measured['rooms_found']}/{measured['rooms_true']}",
        "recall": measured["rooms_matched"] / measured["rooms_true"],
        "precision": measured["rooms_matched"] / measured["rooms_found"] if measured["rooms_found"] else 0.0,
        "area_err": measured["area_err_median"],
        "door_recall": measured["door_recall"],
        "route_err": measured["route_err_median"],
        "routes": measured["routes"],
        "findings": len(convert_findings.items) + len(findings.items),
        "unreachable": "room_unreachable" in codes,
        "tokens": f"{result.input_tokens}/{result.output_tokens}",
        "seconds": result.seconds,
        "cost": result.cost_usd,
    }


def median(rows: list[dict], key: str) -> float:
    return statistics.median(row[key] for row in rows) if rows else float("nan")


def render(rows: list[dict], total_cost: float) -> list[str]:
    lines = [
        (
            "| Floor | Rooms found/true | Recall | Precision | Area err (median) | Door recall | Route err (median) "
            "| Findings | Unreachable warned | Tokens in/out | Seconds | Cost USD |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['floor']} | {r['rooms']} | {r['recall']:.2f} | {r['precision']:.2f} | {r['area_err']:.1%} "
            f"| {r['door_recall']:.2f} | {r['route_err']:.1%} ({r['routes']}) | {r['findings']} "
            f"| {'yes' if r['unreachable'] else 'no'} | {r['tokens']} | {r['seconds']:.1f} | {r['cost']:.3f} |"
        )
    lines.append("")
    for group, label in (("clean", "Clean (procedural, ResPlan)"), ("swiss", "Swiss"), ("other", "OSM")):
        part = [r for r in rows if r["group"] == group]
        if part:
            lines.append(
                f"- {label}, {len(part)} floors, medians: recall {median(part, 'recall'):.2f}, precision "
                f"{median(part, 'precision'):.2f}, door recall {median(part, 'door_recall'):.2f}, area err "
                f"{median(part, 'area_err'):.1%}, route err {median(part, 'route_err'):.1%}, "
                f"floors with an unreachable-room finding: {sum(r['unreachable'] for r in part)}/{len(part)}"
            )
    lines.append(
        f"- All {len(rows)} floors: median seconds {median(rows, 'seconds'):.1f}, median cost "
        f"{median(rows, 'cost'):.3f} USD, total {total_cost:.3f} USD (list price, not checked against an invoice)."
    )
    clean = [r for r in rows if r["group"] == "clean"]
    if clean:
        checks = {
            "room recall": median(clean, "recall") >= TARGETS["recall"],
            "room precision": median(clean, "precision") >= TARGETS["precision"],
            "door recall": median(clean, "door_recall") >= TARGETS["door_recall"],
            "area error": median(clean, "area_err") <= TARGETS["area_err"],
            "route error": median(clean, "route_err") <= TARGETS["route_err"],
            "unreachable on at most 1 of 10 floors": sum(r["unreachable"] for r in clean) <= len(clean) / 10,
        }
        lines.append(
            "- Targets on clean floors: " + ", ".join(f"{k} {'met' if ok else 'MISSED'}" for k, ok in checks.items())
        )
    swiss = [r for r in rows if r["group"] == "swiss"]
    if swiss:
        warned = sum(r["unreachable"] for r in swiss if r["recall"] < 1 or r["door_recall"] < 1)
        bad = sum(1 for r in swiss if r["recall"] < 1 or r["door_recall"] < 1)
        lines.append(
            f"- Swiss floors with missing rooms or doors that were also warned about: {warned}/{bad} (target 100%)."
        )
    return lines


def write_log(lines: list[str], model: str) -> None:
    EVAL_LOG.parent.mkdir(exist_ok=True)
    text = EVAL_LOG.read_text(encoding="utf-8") if EVAL_LOG.exists() else "# Eval log\n"
    block = (
        f"\n### Run {datetime.date.today().isoformat()} ({model}, prompt {PROMPT_HASH})\n\n" + "\n".join(lines) + "\n"
    )
    if HEADING not in text.splitlines():
        text = text.rstrip("\n") + f"\n\n{HEADING}\n" + block
    else:
        start = text.index(f"\n{HEADING}\n") + 1
        end = text.find("\n## ", start + len(HEADING))
        end = len(text) if end == -1 else end
        text = text[:end].rstrip("\n") + "\n" + block + text[end:]
    EVAL_LOG.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(prog="eval_level4")
    parser.add_argument("--floors", default=None, help="comma list of building[:level], default 8 dev floors")
    parser.add_argument("--max-dollars", type=float, default=2.0, help="stop before a live call above this total")
    parser.add_argument("--no-log", action="store_true", help="do not write docs/eval-log.md")
    arguments = parser.parse_args()
    rows: list[dict] = []
    spent = 0.0
    for building_id, level in parse_floors(arguments.floors):
        path = cache_file(building_id, level)
        result = load_cached(path)
        source = "cached"
        if result is None:
            if spent + ESTIMATE_PER_FLOOR_USD > arguments.max_dollars:
                print(f"[level4] stopping before {building_id}: ${spent:.3f} spent, cap ${arguments.max_dollars}")
                break
            image = DATA_DEV / building_id / f"floor_{level}_plain.png"
            try:
                result = extract_floor(image, allowed_root=DATA_DEV)
            except ExtractError as error:
                print(f"[level4] {building_id}:{level} extraction failed: {error}")
                if "refused the request" in str(error):
                    break
                continue
            store(path, result)
            spent += result.cost_usd
            source = "live"
        row = evaluate_floor(building_id, level, result)
        rows.append(row)
        print(
            f"[level4] {row['floor']:28s} {source:6s} recall {row['recall']:.2f} prec {row['precision']:.2f} "
            f"doors {row['door_recall']:.2f} area {row['area_err']:.1%} route {row['route_err']:.1%} "
            f"findings {row['findings']} ${row['cost']:.3f} {row['seconds']:.1f}s"
        )
    if not rows:
        print("[level4] nothing evaluated")
        return
    lines = render(rows, sum(r["cost"] for r in rows))
    print("\n" + "\n".join(lines))
    if not arguments.no_log:
        write_log(lines, DEFAULT_MODEL)
        print(f"\n[level4] appended to {EVAL_LOG}")


if __name__ == "__main__":
    main()
