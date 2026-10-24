"""Live test of the Level 4 tools beyond one clean floor: two floors, plans with furniture, another drawing style.

  uv run --env-file /path/to/.env python scripts/level4_live_test.py a --building proc-campus-dev-000
  uv run --env-file /path/to/.env python scripts/level4_live_test.py b --building resplan-439
  uv run --env-file /path/to/.env python scripts/level4_live_test.py c --building proc-campus-dev-000
  uv run python scripts/level4_live_test.py a --building proc-campus-dev-000   # repeat from the cache, no API

Uses the real conversation tools (build_from_plan, preview_draft, save_building) with the real vision call. Raw
extractions are cached under agent_output/level4_cache (key = image bytes + prompt), so a repeat costs nothing.
Budget guard: at most MAX_CALLS vision calls and MAX_DOLLARS in total (counted in agent_output/level4_live/budget.json).
Results are written as JSON to agent_output/level4_live/. Nothing is written into data/."""

import argparse
import dataclasses
import hashlib
import json
import random
import shutil
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_level4
from PIL import Image, ImageOps

from building_agent import judge_score, routing
from building_agent.guide_tools import GuideState
from building_agent.level4 import tools as level4_tools
from building_agent.level4.extract import PROMPT, ExtractResult
from building_agent.level4.markers import detect_markers
from building_agent.level4.schema import OUTSIDE
from building_agent.level4.segment import segment_rooms
from building_agent.level4.tools import BMHolder, make_level4_tools
from starter_agent.building_map import BuildingMap, MapError
from tests.level4_helpers import DATA_DEV, floor_case, load_building, match_rooms, measure

MAX_CALLS = 20
MAX_DOLLARS = 1.00
LIVE_DIR = ROOT / "agent_output" / "level4_live"
BUDGET_FILE = LIVE_DIR / "budget.json"
PROMPT_HASH = hashlib.sha256(PROMPT.encode()).hexdigest()[:8]


class BudgetStop(Exception):
    pass


# ---------- budget and cache ----------


def read_budget() -> dict:
    if BUDGET_FILE.exists():
        return json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    return {"calls": 0, "cost_usd": 0.0, "log": []}


def write_budget(budget: dict) -> None:
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_FILE.write_text(json.dumps(budget, indent=1), encoding="utf-8")


def cached_extract(real_extract):
    """Replace extract_floor: cache by image content, count calls and dollars, stop before the budget is spent."""

    def wrapper(path, client=None, allowed_root=None, **kwargs):
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
        file = eval_level4.CACHE_DIRECTORY / f"live_{digest}_{PROMPT_HASH}.json"
        cached = eval_level4.load_cached(file)
        if cached is not None:
            return dataclasses.replace(cached, seconds=cached.seconds)
        budget = read_budget()
        if budget["calls"] >= MAX_CALLS or budget["cost_usd"] > MAX_DOLLARS - 0.06:
            raise BudgetStop(f"budget reached: {budget['calls']} calls, {budget['cost_usd']:.3f} USD")
        try:
            result: ExtractResult = real_extract(path, allowed_root=allowed_root, **kwargs)
        except Exception as error:
            budget["log"].append({"image": Path(path).name, "error": f"{type(error).__name__}: {error}"})
            write_budget(budget)
            raise
        eval_level4.store(file, result)
        budget["calls"] += 1
        budget["cost_usd"] = round(budget["cost_usd"] + result.cost_usd, 4)
        budget["log"].append({"image": Path(path).name, "cost_usd": result.cost_usd, "seconds": result.seconds})
        write_budget(budget)
        return result

    return wrapper


# ---------- the conversation rig (like tests/test_level4_tools.py, but with the real vision call) ----------


class LiveRig:
    def __init__(self, scratch: Path, building_id: str | None):
        self.uploads = scratch / "uploads"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.buildings = scratch / "buildings"
        self.saved: list[Path] = []
        if not getattr(level4_tools.extract_floor, "is_cached", False):
            level4_tools.extract_floor = cached_extract(level4_tools.extract_floor)
            level4_tools.extract_floor.is_cached = True
        start = BuildingMap(load_building(building_id)) if building_id else BuildingMap(load_building("resplan-439"))
        self.holder = BMHolder(start)
        self.state = GuideState()
        made = make_level4_tools(
            self.holder, scratch / "out", self.state, self.saved.append, self.uploads, self.buildings
        )
        self.tools = {tool.name: tool for tool in made}

    def put_image(self, source: Path, name: str) -> str:
        shutil.copy(source, self.uploads / name)
        return name

    def turn(self) -> None:
        self.state.begin_turn()

    def call(self, name: str, **kwargs) -> dict:
        return json.loads(self.tools[name](**kwargs))

    @property
    def draft(self):
        return self.state.level4


def floor_width_m(building_id: str, level: int) -> float:
    case = floor_case(building_id, level)
    xs = [x for s in case.truth["spaces"] for x, _ in s["polygon"]]
    return max(xs) - min(xs)


# ---------- measuring a built floor against the truth ----------


def restrict(building: dict, level: int) -> dict:
    floor_ids = {f["id"] for f in building["floors"] if f["level"] == level}
    return {
        **building,
        "spaces": [s for s in building["spaces"] if s["floor_id"] in floor_ids],
        "openings": [o for o in building["openings"] if o["floor_id"] in floor_ids],
    }


def floor_report(building_id: str, level: int, draft) -> dict:
    """Rooms, doors and routes of one floor of the draft against the original floor."""
    converted = restrict(draft.building, level)
    case = floor_case(building_id, level)
    source = draft.floors[level]
    case = dataclasses.replace(case, extraction=source.extraction, scale=source.scale)
    case = dataclasses.replace(case, offset=eval_level4.best_offset(case, converted))
    found_doors = [o for o in converted["openings"] if OUTSIDE not in o["space_ids"]]
    found_entr = [o for o in converted["openings"] if OUTSIDE in o["space_ids"]]
    truth_doors = [o for o in case.truth["openings"] if OUTSIDE not in o["space_ids"]]
    truth_entr = [o for o in case.truth["openings"] if OUTSIDE in o["space_ids"]]
    kinds = {}
    for o in case.truth["openings"]:
        kinds[o["kind"]] = kinds.get(o["kind"], 0) + 1
    m = measure(case, converted)
    return {
        "rooms_true": m["rooms_true"],
        "rooms_found": m["rooms_found"],
        "rooms_matched": m["rooms_matched"],
        "doors_true": len(truth_doors),
        "doors_found": len(found_doors),
        "entrances_true": len(truth_entr),
        "entrances_found": len(found_entr),
        "truth_opening_kinds": kinds,
        "door_recall": round(m["door_recall"], 3),
        "area_err_median": round(m["area_err_median"], 4),
        "judge_pairs": m["judge_pairs"],
        "judge_full_share": round(m["judge_full_share"], 3),
        "judge_invalid": m["judge_invalid"],
        "judge_no_route": m["judge_no_route"],
        "judge_err_median": round(m["judge_err_median"], 4),
        "scale_m_per_px": round(source.scale.metres_per_px, 5),
        "scale_note": source.scale.note,
    }


def free_image_probe(image: Path) -> dict:
    """Deterministic steps only (no API): colour segmentation and marker detection on the image."""
    out: dict = {}
    try:
        seg = segment_rooms(image)
        out["segments"] = len(seg.regions)
        out["segment_usable"] = seg.usable
        out["fill_share"] = round(seg.fill_share, 3)
        out["segment_colours"] = sorted({r.colour_name for r in seg.regions})
    except Exception as error:  # noqa: BLE001
        out["segment_error"] = f"{type(error).__name__}: {error}"
    try:
        marks = detect_markers(image)
        out["markers"] = {
            "doors": len(marks.doors),
            "openings": len(marks.openings),
            "entrances": len(marks.entrances),
        }
    except Exception as error:  # noqa: BLE001
        out["marker_error"] = f"{type(error).__name__}: {error}"
    return out


def build_one(rig: LiveRig, building_id: str, level: int, image: Path, name: str, known: float | None) -> dict:
    """build_from_plan for one image through the tool, returning the tool summary plus timing."""
    rig.put_image(image, name)
    started = time.monotonic()
    summary = rig.call("build_from_plan", image_path=name, level=level, known_length_m=known)
    summary["wall_seconds"] = round(time.monotonic() - started, 2)
    return summary


def raw_extraction_counts(result: ExtractResult) -> dict:
    kinds: dict = {}
    for d in result.extraction.doors:
        kinds[d.kind] = kinds.get(d.kind, 0) + 1
    return {"rooms": len(result.extraction.rooms), "doors": len(result.extraction.doors), "door_kinds": kinds}


def cached_raw(image: Path) -> ExtractResult | None:
    digest = hashlib.sha256(image.read_bytes()).hexdigest()[:16]
    return eval_level4.load_cached(eval_level4.CACHE_DIRECTORY / f"live_{digest}_{PROMPT_HASH}.json")


# ---------- test A: two floors ----------


def cross_floor_eval(
    original: BuildingMap, produced: BuildingMap, matched: dict[str, str], levels: dict, seed: int = 1
):
    """Cross-floor pairs between matched rooms, judged like tests/level4_helpers.judge_route_scores."""
    back = {oid: pid for pid, oid in matched.items()}
    floor_of = {sid: levels[space["floor_id"]] for sid, space in original.spaces.items()}
    rng = random.Random(seed)
    result = {}
    for step_free in (False, True):
        model = judge_score._model(original, set(original.closed), step_free)
        pairs, per = [], {"pairs": 0, "full": 0, "invalid": 0, "no_route": 0, "unreachable_in_truth": 0}
        sources = rng.sample(sorted(back), min(10, len(back)))
        ratios = []
        for source in sources:
            for target in sorted(back):
                if floor_of.get(target) == floor_of.get(source) or floor_of.get(target) not in (0, 1):
                    continue
                best = judge_score.best_length(model, [source, target])
                if best is None or best <= 0:
                    per["unreachable_in_truth"] += 1
                    continue
                per["pairs"] += 1
                try:
                    ours = routing.route(produced, back[source], back[target], step_free=step_free)
                except MapError:
                    per["no_route"] += 1
                    pairs.append((source, target, 0.0, "no route"))
                    continue
                mapped = [s if s == OUTSIDE else matched.get(s) for s in ours.space_path]
                if None in mapped or judge_score._first_invalid_step(model, mapped):
                    per["invalid"] += 1
                    pairs.append((source, target, 0.0, "invalid"))
                    continue
                length = model.measure(mapped)
                score = 1.0 if not length or length <= 1e-9 else min(1.0, best / length)
                per["full"] += score >= judge_score.FULL_MARKS
                ratios.append(ours.length_m / routing.route(original, source, target, step_free=step_free).length_m)
                pairs.append((source, target, score, "ok"))
        per["full_share"] = round(per["full"] / per["pairs"], 3) if per["pairs"] else None
        per["length_ratio_median"] = round(statistics.median(ratios), 3) if ratios else None
        per["length_ratio_max"] = round(max(ratios), 3) if ratios else None
        result["step_free" if step_free else "normal"] = per
    return result


def run_a(building_id: str, scratch: Path) -> dict:
    rig = LiveRig(scratch, building_id)
    out: dict = {"building": building_id, "builds": []}
    rig.turn()
    for level in (0, 1):
        image = DATA_DEV / building_id / f"floor_{level}_plain.png"
        known = floor_width_m(building_id, level)
        summary = build_one(rig, building_id, level, image, f"{building_id}_f{level}.png", known)
        summary["known_length_m"] = round(known, 2)
        summary["image_size"] = Image.open(image).size
        raw = cached_raw(image)
        summary["raw_model"] = raw_extraction_counts(raw) if raw else None
        summary["probe"] = free_image_probe(image)
        out["builds"].append(summary)
    draft = rig.draft
    out["floor_reports"] = {lvl: floor_report(building_id, lvl, draft) for lvl in (0, 1)}
    out["draft_connectors"] = [
        {"kind": c["kind"], "name": c["name"], "floors": len(c["floor_ids"]), "spaces": c["space_ids"]}
        for c in draft.building["vertical_connectors"]
    ]
    out["plain_room_connector_types"] = {
        lvl: [
            (s.get("ref"), s["type"])
            for s in draft.building["spaces"]
            if s["type"] in ("stair", "lift") and s["floor_id"].endswith(f"F{lvl}")
        ]
        for lvl in (0, 1)
    }
    # the card and the save, like the Rig: card in one turn, clear yes in the next
    rig.turn()
    card = rig.call("preview_draft")
    out["card"] = card
    rig.turn()
    try:
        saved = rig.call("save_building", confirmed=True, user_reply="yes, save it")
    except Exception as error:  # noqa: BLE001
        out["save_first_try_error"] = str(error)
        rig.turn()
        rig.call("preview_draft")
        rig.turn()
        saved = rig.call("save_building", confirmed=True, user_reply="yes, save it anyway", accept_problems=True)
        out["saved_with_accept_problems"] = True
    out["saved"] = saved
    loaded = BuildingMap.load(Path(saved["path"]))
    out["loaded"] = {
        "floors": len(loaded.data["floors"]),
        "spaces": len(loaded.spaces),
        "connectors": len(loaded.connectors),
    }
    out["as_built"] = evaluate_building(building_id, loaded)
    out["fix_attempt"] = fix_attempt(scratch / "fix", building_id)
    out["link_attempt"] = link_attempt(scratch / "link", building_id)
    out["oracle_types"] = oracle_types(scratch / "oracle", building_id)
    return out


def evaluate_building(building_id: str, produced: BuildingMap) -> dict:
    """Connectors and cross-floor routes of a two-floor building against the original."""
    original = BuildingMap(load_building(building_id))
    orig_levels = {f["id"]: f["level"] for f in original.data["floors"]}
    between = [c for c in original.connectors.values() if {0, 1} <= {orig_levels[f] for f in c["floor_ids"]}]
    matched: dict[str, str] = {}
    for lvl in (0, 1):
        converted = restrict(produced.data, lvl)
        case = floor_case(building_id, lvl)
        case = dataclasses.replace(case, offset=eval_level4.best_offset(case, converted))
        matched.update(match_rooms(case, converted))
    orig_by_space = {sid: c["id"] for c in between for sid in c["space_ids"]}
    recovered, wrong = set(), 0
    for c in produced.connectors.values():
        ids = {orig_by_space.get(matched.get(sid)) for sid in c["space_ids"]}
        ids.discard(None)
        if len(ids) == 1:
            recovered |= ids
        else:
            wrong += 1
    levels = {f["id"]: f["level"] for f in produced.data["floors"]}
    refs = {s["id"]: s.get("ref") for s in produced.data["spaces"]}
    return {
        "original_connectors_0_1": {"count": len(between), "kinds": [c["kind"] for c in between]},
        "produced_connectors": [
            {
                "kind": c["kind"],
                "floors": sorted(levels[f] for f in c["floor_ids"]),
                "refs": [refs[i] for i in c["space_ids"]],
            }
            for c in produced.connectors.values()
        ],
        "connectors_recovered": len(recovered),
        "connectors_not_matching_an_original": wrong,
        "rooms_matched_total": len(matched),
        "cross_floor": cross_floor_eval(original, produced, matched, orig_levels),
    }


def rebuilt_from_cache(scratch: Path, building_id: str) -> LiveRig:
    """The same two floors again (cache hits, no API call)."""
    rig = LiveRig(scratch, building_id)
    rig.turn()
    for level in (0, 1):
        build_one(
            rig,
            building_id,
            level,
            DATA_DEV / building_id / f"floor_{level}_plain.png",
            f"f{level}.png",
            floor_width_m(building_id, level),
        )
    return rig


def true_connector_refs(building_id: str) -> list[tuple[str, str, int]]:
    original = BuildingMap(load_building(building_id))
    levels = {f["id"]: f["level"] for f in original.data["floors"]}
    found = []
    for c in original.connectors.values():
        if {0, 1} <= {levels[f] for f in c["floor_ids"]}:
            for sid in c["space_ids"]:
                space = original.spaces[sid]
                if levels[space["floor_id"]] in (0, 1):
                    found.append((space.get("ref") or space["name"], c["kind"], levels[space["floor_id"]]))
    return found


def fix_attempt(scratch: Path, building_id: str) -> dict:
    """What the person can do: tell the agent which rooms are stairs and lifts with fix_draft set_room_type."""
    rig = rebuilt_from_cache(scratch, building_id)
    answers = []
    for ref, kind, level in true_connector_refs(building_id):
        room_type = "stairwell" if kind == "stairs" else "lift"
        try:
            answers.append(
                rig.call("fix_draft", action="set_room_type", ref=ref, room_type=room_type, level=level)["done"]
            )
        except Exception as error:  # noqa: BLE001
            answers.append(f"error: {error}")
    return {
        "fix_answers": answers[:3],
        "connectors_after_fixes": len(rig.draft.building["vertical_connectors"]),
        "problems_after_fixes": rig.call("preview_draft")["problems found"],
    }


def link_attempt(scratch: Path, building_id: str) -> dict:
    """What the person can do when the hall numbers differ per floor: fix_draft link_floors for every true connector."""
    rig = rebuilt_from_cache(scratch, building_id)
    original = BuildingMap(load_building(building_id))
    levels = {f["id"]: f["level"] for f in original.data["floors"]}
    answers = []
    for c in original.connectors.values():
        stops = {levels[original.spaces[s]["floor_id"]]: original.spaces[s] for s in c["space_ids"]}
        if 0 not in stops or 1 not in stops:
            continue
        ref0, ref1 = (stops[0].get("ref") or stops[0]["name"]), (stops[1].get("ref") or stops[1]["name"])
        try:
            answers.append(
                rig.call(
                    "fix_draft",
                    action="link_floors",
                    ref=ref0,
                    other_ref=ref1,
                    kind=c["kind"],
                    level=0,
                    other_level=1,
                )["done"]
            )
        except Exception as error:  # noqa: BLE001
            answers.append(f"error: {error}")
    rig.turn()
    card = rig.call("preview_draft")
    return {
        "answers": answers,
        "connectors_after": len(rig.draft.building["vertical_connectors"]),
        "question": card.get("question"),
        "evaluated": evaluate_building(building_id, BuildingMap(rig.draft.building)),
    }


def oracle_types(scratch: Path, building_id: str) -> dict:
    """Upper bound: the model had typed the true stairs and lifts as stair and lift (set in the cached extraction)."""
    rig = rebuilt_from_cache(scratch, building_id)
    wanted = {(ref, level): kind for ref, kind, level in true_connector_refs(building_id)}
    for level, source in rig.draft.floors.items():
        rooms = [
            dataclasses.replace(r, type="stair" if wanted[(r.ref, level)] == "stairs" else "lift")
            if (r.ref, level) in wanted
            else r
            for r in source.extraction.rooms
        ]
        source.extraction = dataclasses.replace(source.extraction, rooms=rooms)
    level4_tools._rebuild(rig.draft)
    rig.turn()
    card = rig.call("preview_draft")
    rig.turn()
    saved = rig.call("save_building", confirmed=True, user_reply="yes, save it") if card["can be saved"] else None
    produced = BuildingMap(rig.draft.building) if saved is None else rig.holder.bm
    result = evaluate_building(building_id, produced)
    result["card_problems"] = card["problems found"]
    result["card_notes"] = card.get("notes")
    result["card_can_be_saved"] = card["can be saved"]
    return result


# ---------- test B and C: one floor from another image ----------


def one_floor(building_id: str, image: Path, scratch: Path, known: float, name: str) -> dict:
    rig = LiveRig(scratch, None)
    rig.turn()
    summary = build_one(rig, building_id, 0, image, name, known)
    raw = cached_raw(image)
    rig.turn()
    card = rig.call("preview_draft")
    entry = {
        "image": image.name,
        "size": Image.open(image).size,
        "summary": summary,
        "raw_model": raw_extraction_counts(raw) if raw else None,
        "probe": free_image_probe(image),
        "card_problems": card.get("problems found"),
        "card_notes": card.get("notes"),
        "card_question": card.get("question"),
        "card_proposal": card.get("proposal"),
        "can_be_saved": card.get("can be saved"),
    }
    try:
        entry["report"] = floor_report(building_id, 0, rig.draft)
    except Exception as error:  # noqa: BLE001
        entry["report_error"] = f"{type(error).__name__}: {error}"
    return entry


def run_b(building_id: str, scratch: Path) -> dict:
    known = floor_width_m(building_id, 0)
    out = {"building": building_id, "known_length_m": round(known, 2)}
    for label, filename in (("plain", "floor_0_plain.png"), ("furniture", "floor_0.png")):
        out[label] = one_floor(building_id, DATA_DEV / building_id / filename, scratch / label, known, f"{label}.png")
    return out


def run_c(building_id: str, scratch: Path, mode: str) -> dict:
    known = floor_width_m(building_id, 0)
    source = DATA_DEV / building_id / "floor_0_plain.png"
    image = Image.open(source).convert("RGB")
    variants = {"invert": ImageOps.invert(image), "grey": ImageOps.grayscale(image).convert("RGB")}
    folder = scratch / "recoloured"
    folder.mkdir(parents=True, exist_ok=True)
    out: dict = {"building": building_id, "known_length_m": round(known, 2), "free_probes": {}}
    for label, picture in variants.items():
        path = folder / f"{building_id}_{label}.png"
        picture.save(path)
        out["free_probes"][label] = free_image_probe(path)
    out["free_probes"]["original"] = free_image_probe(source)
    out["paid"] = {
        mode: one_floor(building_id, folder / f"{building_id}_{mode}.png", scratch / mode, known, f"{mode}.png")
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("test", choices=["a", "b", "c"])
    parser.add_argument("--building", required=True)
    parser.add_argument(
        "--mode", default="grey", choices=["grey", "invert"], help="test c: which image goes to the API"
    )
    parser.add_argument("--scratch", default=str(LIVE_DIR / "scratch"))
    args = parser.parse_args()
    scratch = Path(args.scratch) / f"{args.test}_{args.building}"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    try:
        if args.test == "a":
            result = run_a(args.building, scratch)
        elif args.test == "b":
            result = run_b(args.building, scratch)
        else:
            result = run_c(args.building, scratch, args.mode)
    except BudgetStop as stop:
        print(f"STOPPED: {stop}")
        sys.exit(2)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.mode}" if args.test == "c" else ""
    target = LIVE_DIR / f"result_{args.test}_{args.building}{suffix}.json"
    target.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(json.dumps(result, indent=1, default=str))
    print(f"budget: {read_budget()['calls']} calls, {read_budget()['cost_usd']:.3f} USD; written {target}")


if __name__ == "__main__":
    main()
