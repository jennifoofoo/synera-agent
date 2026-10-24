"""Stress test of the Level 4 build path on SYNTHETIC foreign drawing styles (not real architect plans).

  uv run --env-file /path/to/.env python scripts/level4_style_eval.py --styles lines,scan --buildings resplan-439,swiss-31
  uv run python scripts/level4_style_eval.py            # cached extractions only costs nothing

Per style and building: render the floor (scripts/render_plan_styles.py), run extraction + segmentation + markers +
convert + validate exactly as build_from_plan does (through make_level4_tools), and measure against the truth in the
image frame. Extractions are cached per image hash in agent_output/level4_cache, so a rerun is free.
The scale is the true building width as known length."""

import argparse
import hashlib
import json
import pickle
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from building_agent.guide_tools import GuideState
from building_agent.level4 import extract as extract_module
from building_agent.level4 import tools as level4_tools
from building_agent.level4.convert import scale_from_bar
from building_agent.level4.extract import ExtractError, ExtractResult, extract_floor
from building_agent.level4.markers import detect_markers
from building_agent.level4.schema import ExtractedDoor, ExtractedRoom, Extraction, Scale
from building_agent.level4.segment import segment_rooms
from building_agent.level4.tools import BMHolder, make_level4_tools
from scripts.render_plan_styles import DATA_DEV, FLOORS, OUT_DIRECTORY, STYLES, Render, render
from starter_agent.building_map import BuildingMap
from tests.level4_helpers import FloorCase, measure

CACHE_DIRECTORY = Path("agent_output") / "level4_cache"
RESULTS_FILE = OUT_DIRECTORY / "results.json"
DEFAULT_MAX_DOLLARS = 1.20
CALL_ESTIMATE_USD = 0.05
FULL = 0.99


class BudgetStop(Exception):
    pass


class FatalApi(Exception):
    pass


@dataclass
class Spend:
    limit: float
    spent: float = 0.0
    calls: int = 0
    costs: list[float] = field(default_factory=list)

    def estimate(self) -> float:
        return max(CALL_ESTIMATE_USD, max(self.costs, default=0.0))


def image_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:24]


def cached_extractor(spend: Spend, log: list[dict]):
    """Drop-in for extract_floor: disk cache by image hash, a real call only while the budget allows."""

    def fake(path, client=None, allowed_root=None, **kwargs) -> ExtractResult:
        CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        file = CACHE_DIRECTORY / f"style-{image_hash(Path(path))}.pkl"
        if file.exists():
            log.append({"fresh": False})
            return pickle.loads(file.read_bytes())
        if spend.spent + spend.estimate() > spend.limit:
            raise BudgetStop
        spend.calls += 1
        try:
            result = extract_floor(path, allowed_root=allowed_root)
        except ExtractError as error:
            if str(error) == extract_module._FATAL_MESSAGE:
                raise FatalApi(str(error)) from error
            raise
        spend.spent += result.cost_usd
        spend.costs.append(result.cost_usd)
        file.write_bytes(pickle.dumps(result))
        log.append({"fresh": True})
        return result

    return fake


def truth_case(made: Render, extraction: Extraction | None = None) -> FloorCase:
    """Truth of the render in the frame the converter uses (metres, y up, origin bottom left of the image)."""
    mpp = 1 / made.px_per_m
    height = made.height_px

    def to_m(point):
        return [point[0] * mpp, (height - point[1]) * mpp]

    spaces = [{**s, "polygon": [to_m(p) for p in s["polygon_px"]]} for s in made.spaces]
    openings = [{**o, "position": to_m(o["position_px"])} for o in made.openings]
    data = json.loads((DATA_DEV / made.building_id / "building.json").read_text(encoding="utf-8"))
    floor = next(f for f in data["floors"] if f["level"] == made.level)
    truth = {
        "building": data["building"],
        "floors": [floor],
        "spaces": spaces,
        "openings": openings,
        "vertical_connectors": [],
        "assets": [],
    }
    empty = extraction or Extraction(made.width_px, made.height_px, [], [])
    return FloorCase(made.building_id, made.level, empty, Scale(mpp, "known_length", "truth"), (0.0, 0.0), truth)


def true_width_m(made: Render) -> float:
    xs = [x for s in made.spaces for x, _ in s["polygon"]]
    return max(xs) - min(xs)


def judge_summary(metrics: dict) -> dict:
    pairs = metrics["judge_pairs"]
    return {
        "pairs": pairs,
        "full": round(metrics["judge_full_share"] * pairs),
        "invalid": metrics["judge_invalid"],
        "no_route": metrics["judge_no_route"],
    }


def entrance_counts(building: dict, truth: dict) -> tuple[int, int]:
    def count(data):
        return sum("outside" in o["space_ids"] for o in data["openings"])

    return count(building), count(truth)


def run_one(made: Render, spend: Spend, tmp: Path) -> dict:
    """The build path of build_from_plan on one image; returns one flat result row."""
    row: dict = {"style": made.style, "building": made.building_id, "level": made.level}
    row["image"] = f"{made.width_px}x{made.height_px}"
    log: list[dict] = []
    original = level4_tools.extract_floor
    level4_tools.extract_floor = cached_extractor(spend, log)
    try:
        state = GuideState()
        holder = BMHolder(BuildingMap(json.loads((DATA_DEV / made.building_id / "building.json").read_text("utf-8"))))
        tools = {t.name: t for t in make_level4_tools(holder, tmp / "out", state, None, made.path.parent, tmp / "b")}
        try:
            began = time.monotonic()
            summary = json.loads(
                tools["build_from_plan"](image_path=made.path.name, level=made.level, known_length_m=true_width_m(made))
            )
            row["wall_seconds"] = round(time.monotonic() - began, 1)
        except BudgetStop:
            raise
        except FatalApi:
            raise
        except Exception as error:  # noqa: BLE001 - a refused build is a result too
            row["error"] = str(error)[:300]
            return row
        draft = state.level4
        result = next(iter(draft.cache.values()))
        extraction = result.extraction
        row["model_cost_usd"] = round(result.cost_usd, 4)
        row["model_seconds"] = round(result.seconds, 1)
        row["fresh"] = bool(log and log[-1]["fresh"])
        row["model_rooms"] = len(extraction.rooms)
        row["model_doors"] = len(extraction.doors)
        row["scale_bar_read"] = [extraction.scale_bar_px, extraction.scale_bar_m]
        bar = scale_from_bar(extraction)
        row["bar_mpp_error"] = (
            round(abs(bar.metres_per_px * made.px_per_m - 1), 3) if bar else None
        )  # relative error of the printed-bar scale against truth
        row["bar_true"] = list(made.scale_bar) if made.scale_bar else None
        row["marker_notes"] = draft.marker_notes
        seg = segment_rooms(made.path)
        row["seg_regions"] = len(seg.regions)
        row["seg_usable"] = seg.usable
        row["seg_fill_share"] = round(seg.fill_share, 3)
        row["markers_found"] = len(detect_markers(made.path))
        converted = draft.building
        row.update(score(made, extraction, converted))
        state.begin_turn()
        card = json.loads(tools["preview_draft"]())
        row["card_problems"] = card["problems found"]
        row["card_notes"] = card.get("notes", [])
        row["card_question"] = card.get("question")
        row["summary_rooms"] = summary["rooms"]
        return row
    finally:
        level4_tools.extract_floor = original


def score(made: Render, extraction: Extraction, converted: dict) -> dict:
    """Room, door, entrance, area and judge-route quality of a converted floor against the render truth."""
    case = truth_case(made, extraction)
    metrics = measure(case, converted)
    true_rooms = len(case.truth["spaces"])
    found, true = entrance_counts(converted, case.truth)
    return {
        "rooms_true": true_rooms,
        "rooms_found": metrics["rooms_found"],
        "rooms_matched": metrics["rooms_matched"],
        "recall": round(metrics["rooms_matched"] / true_rooms, 3) if true_rooms else 0.0,
        "precision": round(metrics["rooms_matched"] / metrics["rooms_found"], 3) if metrics["rooms_found"] else 0.0,
        "door_recall": round(metrics["door_recall"], 3),
        "area_err_median": round(metrics["area_err_median"], 3),
        "judge": judge_summary(metrics),
        "entrances": [found, true],
    }


def perfect_extraction(made: Render) -> Extraction:
    """What a flawless reader would return for this render (for testing the metric code)."""
    ids = {s["id"]: f"r{i}" for i, s in enumerate(made.spaces)}
    rooms = [
        ExtractedRoom(ids[s["id"]], s["polygon_px"], s.get("ref"), s.get("name"), s["type"], s["room_type"])
        for s in made.spaces
    ]
    doors = [
        ExtractedDoor(
            tuple("outside" if end == "outside" else ids[end] for end in o["space_ids"]),
            o["position_px"],
            o["kind"],
            o["width_m"] * made.px_per_m,
        )
        for o in made.openings
    ]
    return Extraction(made.width_px, made.height_px, rooms, doors)


def markdown(rows: list[dict]) -> str:
    lines = []
    for style in dict.fromkeys(r["style"] for r in rows):
        lines += [
            f"**{style}**",
            "",
            (
                "| building | rooms found/true | recall | precision | door recall | entrances | area err | judge full/pairs "
                "(invalid, no route) | seg regions/markers | cost | s |"
            ),
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in [r for r in rows if r["style"] == style]:
            if "error" in r:
                lines.append(f"| {r['building']} | refused: {r['error'][:90]} | | | | | | | | | |")
                continue
            j = r["judge"]
            lines.append(
                f"| {r['building']} | {r['rooms_found']}/{r['rooms_true']} | {r['recall']:.2f} | {r['precision']:.2f} "
                f"| {r['door_recall']:.2f} | {r['entrances'][0]}/{r['entrances'][1]} | {r['area_err_median']:.2f} "
                f"| {j['full']}/{j['pairs']} ({j['invalid']}, {j['no_route']}) "
                f"| {r['seg_regions']}/{r['markers_found']} | ${r['model_cost_usd']:.3f} | {r['model_seconds']} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--styles", default="lines,scan")
    parser.add_argument("--buildings", default=",".join(b for b, _ in FLOORS))
    parser.add_argument("--max-dollars", type=float, default=DEFAULT_MAX_DOLLARS)
    args = parser.parse_args()
    levels = dict(FLOORS)
    spend = Spend(args.max_dollars)
    rows: list[dict] = json.loads(RESULTS_FILE.read_text()) if RESULTS_FILE.exists() else []
    stopped = ""
    for style in args.styles.split(","):
        if style not in STYLES:
            sys.exit(f"unknown style {style}")
        for building_id in args.buildings.split(","):
            level = levels.get(building_id, 0)
            made = render(
                DATA_DEV / building_id / "building.json",
                level,
                style,
                OUT_DIRECTORY / style / f"{building_id}-L{level}.png",
            )
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    row = run_one(made, spend, Path(tmp))
                except BudgetStop:
                    stopped = "budget"
                    break
                except FatalApi as error:
                    stopped = f"api: {error}"
                    break
            rows = [r for r in rows if (r["style"], r["building"]) != (style, building_id)] + [row]
            RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            RESULTS_FILE.write_text(json.dumps(rows, indent=1))
            print(
                style, building_id, {k: row.get(k) for k in ("recall", "precision", "door_recall", "error")}, flush=True
            )
        if stopped:
            break
    print(
        f"fresh API calls {spend.calls}, spent ${spend.spent:.3f} of ${spend.limit}"
        + (f", stopped: {stopped}" if stopped else "")
    )
    print(markdown(rows))
    if rows:
        print("median recall", statistics.median(r.get("recall", 0) for r in rows))


if __name__ == "__main__":
    main()
