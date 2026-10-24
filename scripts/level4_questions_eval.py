"""Level 4 on the labelled dev questions: build each dev building from its plan files, then ask the known questions.

Synera grades Level 4 with the usual questions on the building we built from the plans. This script plays that:
for N dev buildings it builds the building from `floor_<n>.png` + `floor_<n>.svg` through the real tool path
(`build_from_plan`, no API: the vision call is switched off or answered from a cache), then asks every labelled
question of `questions.jsonl` and `questions_basic.jsonl` on the BUILT building and compares with the label using the
README section 6 tolerances. The rooms of a question are found like the agent finds them (`find_space` with the room
name printed in the question, then with the room number alone), so a room that the built building cannot name the way
the question does counts as unresolved.

  uv run python scripts/level4_questions_eval.py                    # 20 buildings, svg path, no API, writes the log
  uv run python scripts/level4_questions_eval.py --n 6 --no-log     # quick look
  uv run python scripts/level4_questions_eval.py --compare-vision   # floor 0 of the buildings with a cached extraction:
                                                                      svg path vs cached vision reading

Not answerable from a plan: locate, count and errand need the furniture list, route_with_closure and
step_free_reachable_count name a lift by an element id that the built building cannot have. They are counted but not
scored. The scale is given the way Synera says it comes (a building.json next to the plans) with the true pixels per
metre of each floor, so the scale itself is not what is measured here."""

import argparse
import copy
import hashlib
import json
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic.lib.tools import ToolError

from building_agent import find_space as find_space_module
from building_agent import routing
from building_agent.find_space import find_space
from building_agent.guide_tools import GuideState
from building_agent.level4 import extract as extract_module
from building_agent.level4 import tools as level4_tools
from building_agent.level4.extract import ExtractError, ExtractResult
from building_agent.level4.schema import ExtractedDoor, ExtractedRoom, Extraction
from building_agent.level4.svg_read import read_svg
from building_agent.level4.tools import BMHolder, make_level4_tools
from building_agent.registry import load_kinds
from starter_agent.building_map import BuildingMap, MapError

DATA_DEV = Path("data/dev")
CACHE_DIRECTORY = Path("agent_output") / "level4_cache"
EVAL_LOG = Path("docs") / "eval-log.md"
HEADING = "### Level 4 questions on built buildings"
PROMPT_HASH = hashlib.sha256(extract_module.PROMPT.encode()).hexdigest()[:8]
ROUTE_KINDS = ("route", "route_step_free", "tour")
SKIPPED = {
    "locate": "needs the furniture list",
    "count": "needs the furniture list",
    "errand": "needs the furniture list",
    "route_with_closure": "names a lift by element id",
    "step_free_reachable_count": "names a lift by element id",
}
SOURCE_NAMES = {"osm_indoor": "osm", "procedural": "proc", "resplan": "resplan", "swiss_dwellings": "swiss"}
ROUTE_TOLERANCE = 0.01


# ---------- choosing buildings ----------


def building_info(directory: Path) -> dict:
    data = json.loads((directory / "building.json").read_text(encoding="utf-8"))
    levels = sorted(floor["level"] for floor in data["floors"])
    return {
        "id": directory.name,
        "dir": directory,
        "source": SOURCE_NAMES.get(data["building"]["source"], "other"),
        "levels": levels,
    }


def choose(count: int) -> list[dict]:
    """Round robin over the sources, multi-floor buildings first inside a source, so every source is in."""
    infos = [building_info(d) for d in sorted(DATA_DEV.iterdir()) if (d / "building.json").exists()]
    infos = [i for i in infos if all((i["dir"] / f"floor_{level}.svg").exists() for level in i["levels"])]
    by_source: dict[str, list[dict]] = defaultdict(list)
    for info in sorted(infos, key=lambda i: (-len(i["levels"]), i["id"])):
        by_source[info["source"]].append(info)
    chosen: list[dict] = []
    while len(chosen) < count and any(by_source.values()):
        for source in sorted(by_source):
            if by_source[source] and len(chosen) < count:
                chosen.append(by_source[source].pop(0))
    return chosen


# ---------- building from the plan files ----------


def true_px_per_m(directory: Path, level: int, truth: dict) -> float:
    floor = next(f for f in truth["floors"] if f["level"] == level)
    xs_m = [x for s in truth["spaces"] if s["floor_id"] == floor["id"] for x, _ in s["polygon"]]
    plan = read_svg(directory / f"floor_{level}.svg")
    xs_px = [x for room in plan.rooms for x, _ in room.polygon_px]
    return (max(xs_px) - min(xs_px)) / (max(xs_m) - min(xs_m))


def load_cached(building_id: str, level: int) -> ExtractResult | None:
    path = CACHE_DIRECTORY / f"{building_id}_{level}_{PROMPT_HASH}.json"
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
    return ExtractResult(extraction, 0, 0, 0.0, 0.0)


def build_building(info: dict, mode: str, levels: list[int], work: Path) -> tuple[BuildingMap | None, str]:
    """(built map, note). mode: "svg" (svg only), "svg+vision" (svg plus cached extraction for names and types)
    or "vision" (png only, cached extraction, known building width)."""
    directory = info["dir"]
    truth = json.loads((directory / "building.json").read_text(encoding="utf-8"))
    uploads = work / "uploads"
    uploads.mkdir(parents=True)
    floors_json = []
    for level in levels:
        plain = mode == "vision"
        shutil.copy(directory / f"floor_{level}{'_plain' if plain else ''}.png", uploads / f"floor_{level}.png")
        if mode != "vision":
            shutil.copy(directory / f"floor_{level}.svg", uploads / f"floor_{level}.svg")
        floors_json.append({"level": level, "px_per_m": true_px_per_m(directory, level, truth)})
    if mode != "vision":
        (uploads / "building.json").write_text(json.dumps({"floors": floors_json}), encoding="utf-8")
    current = {"level": 0}

    def fake_extract(path, client=None, allowed_root=None, **kwargs):
        cached = load_cached(info["id"], current["level"]) if mode != "svg" else None
        if cached is None:
            raise ExtractError("no vision reading in this run")
        return cached

    original = level4_tools.extract_floor
    level4_tools.extract_floor = fake_extract
    try:
        state = GuideState()
        tools = {
            t.name: t for t in make_level4_tools(BMHolder(bm=None), work / "out", state, None, uploads, work / "b")
        }
        notes = []
        for level in levels:
            current["level"] = level
            state.begin_turn()
            args = {"image_path": f"floor_{level}.png", "level": level}
            if mode == "vision":
                floor = next(f for f in truth["floors"] if f["level"] == level)
                xs = [x for s in truth["spaces"] if s["floor_id"] == floor["id"] for x, _ in s["polygon"]]
                args["known_length_m"] = max(xs) - min(xs)
            try:
                summary = json.loads(tools["build_from_plan"](**args))
            except ToolError as error:
                return None, f"floor {level}: {str(error)[:120]}"
            notes.append(summary.get("read_from", ""))
        building = copy.deepcopy(state.level4.building)
    finally:
        level4_tools.extract_floor = original
    building.setdefault("assets", [])
    path = work / "built.json"
    path.write_text(json.dumps(building), encoding="utf-8")
    return BuildingMap.load(path), notes[0] if notes else ""


# ---------- asking the questions ----------


class Mapper:
    """Finds the built room for a room of the true building, the way the agent finds rooms in a question."""

    def __init__(self, truth: dict, built: BuildingMap) -> None:
        self.true = {s["id"]: s for s in truth["spaces"]}
        self.level_of_floor = {f["id"]: f["level"] for f in truth["floors"]}
        self.true_floor = {f["level"]: f["id"] for f in truth["floors"]}
        self.built = built
        self.built_floor = {f["level"]: fid for fid, f in built.floors.items()}

    def level(self, true_id: str) -> int:
        return self.level_of_floor[self.true[true_id]["floor_id"]]

    def space(self, true_id: str) -> tuple[str | None, str]:
        """(built space id or None, how): 'exact' (a built room has the very name of the question), 'name'
        (find_space finds it from that name), 'ref' (only from the room number) or 'none'."""
        room = self.true[true_id]
        level = self.level(true_id)
        same = [
            space_id
            for space_id, space in self.built.spaces.items()
            if self.built.floors[space["floor_id"]]["level"] == level and space["name"].lower() == room["name"].lower()
        ]
        if len(same) == 1:
            return same[0], "exact"
        for how, text in (("name", room["name"]), ("ref", room.get("ref") or "")):
            if not text:
                continue
            try:
                found = find_space(self.built, text, level)
            except MapError:
                continue
            if "match" in found:
                return found["match"]["id"], how
        return None, "none"

    def floor(self, true_floor_id: str) -> str | None:
        return self.built_floor.get(self.level_of_floor[true_floor_id])


def tolerance_ok(got: float, expected: dict) -> bool:
    tol = max(expected.get("absolute_tolerance", 0.0), expected.get("relative_tolerance", 0.0) * expected["value"])
    return abs(got - expected["value"]) <= tol


def accepted(built: BuildingMap, space_id: str, answer: dict) -> bool:
    space = built.spaces[space_id]
    names = {str(space.get("ref") or ""), space["name"]}
    return bool(names & set(answer["accept"])) and not names & set(answer.get("reject") or [])


def ask(question: dict, mapper: Mapper, kinds: dict) -> tuple[str, str]:
    """(status, detail). status: skipped | unresolved | wrong | correct | error."""
    kind, answer, inputs = question["kind"], question["answer"], question.get("inputs", {})
    if kind in SKIPPED:
        return "skipped", SKIPPED[kind]
    built = mapper.built
    hows = []

    def room(true_id: str) -> str | None:
        found, how = mapper.space(true_id)
        hows.append(how)
        return found

    try:
        if kind in ROUTE_KINDS:
            ids = [answer["from_space_id"], answer["to_space_id"]] if kind != "tour" else answer["stops"]
            mapped = [room(i) for i in ids]
            if None in mapped:
                return "unresolved", ",".join(hows)
            reachable = answer.get("reachable") is not False
            try:
                result = routing.route(built, mapped[0], mapped[-1], kind == "route_step_free", via=mapped[1:-1])
            except MapError:
                return ("correct" if not reachable else "wrong"), "no route found"
            if not reachable:
                return "wrong", "route found, label says none"
            expected = answer["optimal_length_m"]
            ok = abs(result.length_m - expected) <= max(ROUTE_TOLERANCE * expected, ROUTE_TOLERANCE)
            return ("correct" if ok else "wrong"), f"{result.length_m:.1f} vs {expected:.1f}"
        fn = kinds[kind].fn
        if kind in ("largest_room", "floor_area_total"):
            floor = mapper.floor(inputs["floor_id"])
            wanted = inputs["room_type"]
            if floor is None or not any(
                s["room_type"] == wanted and s["floor_id"] == floor for s in built.spaces.values()
            ):
                return "unresolved", f"no {wanted} on that floor"
            result = fn(built, floor_id=floor, room_type=wanted)
            if kind == "floor_area_total":
                return ("correct" if tolerance_ok(result["total_m2"], answer) else "wrong"), f"{result['total_m2']}"
            ok = accepted(built, result["space_id"], answer) and tolerance_ok(result["area_m2"], answer["area"])
            return ("correct" if ok else "wrong"), f"{result['name']} {result['area_m2']}"
        args = {}
        for name, value in inputs.items():
            if name in ("start", "first", "second") and value in mapper.true:
                args[name] = room(value)
            elif name in ("floor_id", "door_floor_id"):
                args[name] = mapper.floor(value)
            else:
                args[name] = value
        if None in args.values():
            return "unresolved", ",".join(hows)
        result = fn(built, **args)
        if kind == "room_stacked":
            return ("correct" if accepted(built, result["space_id"], answer) else "wrong"), result["name"]
        got = result.get("count", result.get("distance_m"))
        return ("correct" if tolerance_ok(got, answer) else "wrong"), f"{got} vs {answer['value']}"
    except MapError as error:
        return "error", str(error)[:80]
    except (KeyError, ValueError, TypeError, ArithmeticError) as error:
        return "error", f"{type(error).__name__}: {error}"[:80]


def load_questions(directory: Path) -> list[dict]:
    found = []
    for name in ("questions.jsonl", "questions_basic.jsonl"):
        path = directory / name
        if path.exists():
            found += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return found


def floors_of(question: dict, mapper: Mapper) -> set[int]:
    """Levels of every room and floor the question names (to restrict a comparison to the floors that were built)."""
    levels = set()
    text = json.dumps([question.get("inputs", {}), question["answer"]])
    for true_id in mapper.true:
        if true_id in text:
            levels.add(mapper.level(true_id))
    for floor_id, level in mapper.level_of_floor.items():
        if floor_id in text:
            levels.add(level)
    return levels


def run_building(info: dict, mode: str, levels: list[int], kinds: dict, only_levels: set[int] | None = None) -> dict:
    truth = json.loads((info["dir"] / "building.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as folder:
        started = time.monotonic()
        built, note = build_building(info, mode, levels, Path(folder))
        seconds = time.monotonic() - started
        rows = []
        if built is None:
            return {"info": info, "built": False, "note": note, "rows": rows, "seconds": seconds, "spaces": 0}
        mapper = Mapper(truth, built)
        for question in load_questions(info["dir"]):
            if only_levels is not None and not floors_of(question, mapper) <= only_levels:
                continue
            status, detail = ask(question, mapper, kinds)
            how = ""
            if status != "skipped":
                ids = [
                    v
                    for v in list(question.get("inputs", {}).values())
                    + [question["answer"].get(k) for k in ("from_space_id", "to_space_id")]
                    + list(question["answer"].get("stops") or [])
                    if isinstance(v, str) and v in mapper.true
                ]
                kinds_used = [mapper.space(i)[1] for i in ids]
                how = ""
                for step in ("exact", "name", "ref"):  # the weakest way any room of the question needed
                    if kinds_used and all(
                        k in ("exact", "name", "ref")[: ("exact", "name", "ref").index(step) + 1] for k in kinds_used
                    ):
                        how = step
                        break
                else:
                    how = "none" if kinds_used else ""
            rows.append(
                {"kind": question["kind"], "status": status, "detail": detail, "how": how, "id": question["id"]}
            )
        return {
            "info": info,
            "built": True,
            "note": note,
            "rows": rows,
            "seconds": seconds,
            "spaces": len(built.spaces),
        }


# ---------- report ----------


def share(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "-"


def kind_table(results: list[dict]) -> list[str]:
    rows = [row for result in results for row in result["rows"]]
    count = Counter()
    for row in rows:
        count[(row["kind"], row["status"])] += 1
        if row["status"] not in ("skipped", "unresolved") or row["status"] == "unresolved":
            pass
    lines = [
        "| Kind | Questions | Resolved | Correct | Correct of resolved | Unresolved share |",
        "|---|---|---|---|---|---|",
    ]
    total = resolved_total = correct_total = 0
    for kind in sorted({row["kind"] for row in rows}):
        n = sum(v for (k, _), v in count.items() if k == kind)
        if kind in SKIPPED:
            lines.append(f"| {kind} | {n} | not scored ({SKIPPED[kind]}) | | | |")
            continue
        unresolved = count[(kind, "unresolved")]
        resolved = n - unresolved
        correct = count[(kind, "correct")]
        total, resolved_total, correct_total = total + n, resolved_total + resolved, correct_total + correct
        lines.append(f"| {kind} | {n} | {resolved} | {correct} | {share(correct, resolved)} | {share(unresolved, n)} |")
    lines.append(
        f"| **all scored kinds** | {total} | {resolved_total} | {correct_total} | {share(correct_total, resolved_total)} | {share(total - resolved_total, total)} |"
    )
    return lines


def source_table(results: list[dict]) -> list[str]:
    lines = [
        "| Source | Buildings | Questions | Resolved | Correct | Score | Unresolved share |",
        "|---|---|---|---|---|---|---|",
    ]
    for source in sorted({r["info"]["source"] for r in results}):
        chosen = [r for r in results if r["info"]["source"] == source]
        rows = [row for r in chosen for row in r["rows"] if row["status"] != "skipped"]
        unresolved = sum(row["status"] == "unresolved" for row in rows)
        correct = sum(row["status"] == "correct" for row in rows)
        lines.append(
            f"| {source} | {len(chosen)} | {len(rows)} | {len(rows) - unresolved} | {correct} | {share(correct, len(rows))} | {share(unresolved, len(rows))} |"
        )
    return lines


def naming_table(results: list[dict]) -> list[str]:
    rows = [row for r in results for row in r["rows"] if row["status"] != "skipped" and row["how"]]
    count = Counter(row["how"] for row in rows)
    return [
        "| Rooms of the question found by | Questions | Share |",
        "|---|---|---|",
        f"| a room with exactly that name | {count['exact']} | {share(count['exact'], len(rows))} |",
        f"| find_space with that name (not exact) | {count['name']} | {share(count['name'], len(rows))} |",
        f"| the room number alone | {count['ref']} | {share(count['ref'], len(rows))} |",
        f"| not at all | {count['none']} | {share(count['none'], len(rows))} |",
    ]


def building_table(results: list[dict], weakest: int = 8) -> list[str]:
    scored = []
    for r in results:
        rows = [row for row in r["rows"] if row["status"] != "skipped"]
        if rows:
            scored.append((sum(row["status"] == "correct" for row in rows) / len(rows), r, rows))
    lines = [
        "| Building | Source | Floors | Built rooms | Questions | Correct | Unresolved |",
        "|---|---|---|---|---|---|---|",
    ]
    for score, r, rows in sorted(scored, key=lambda item: item[0])[:weakest]:
        unresolved = sum(row["status"] == "unresolved" for row in rows)
        lines.append(
            f"| {r['info']['id']} | {r['info']['source']} | {len(r['info']['levels'])} | {r['spaces']} | {len(rows)} | {score:.0%} | {unresolved} |"
        )
    return lines


def report(results: list[dict], title: str) -> list[str]:
    built = [r for r in results if r["built"]]
    rows = [row for r in built for row in r["rows"] if row["status"] != "skipped"]
    correct = sum(row["status"] == "correct" for row in rows)
    lines = [
        f"**{title}**",
        "",
        f"{len(built)} of {len(results)} buildings built, {len(rows)} scored questions, {correct} correct "
        f"(score {share(correct, len(rows))}). Not built: "
        + (", ".join(f"{r['info']['id']} ({r['note']})" for r in results if not r["built"]) or "none")
        + ".",
        "",
        *kind_table(built),
        "",
        *source_table(built),
        "",
        *naming_table(built),
        "",
        "Weakest buildings:",
        "",
        *building_table(built),
    ]
    return lines


def write_log(lines: list[str]) -> None:
    text = EVAL_LOG.read_text(encoding="utf-8") if EVAL_LOG.exists() else ""
    if HEADING in text:
        head, _, tail = text.partition(HEADING)
        rest = tail.split("\n### ", 1)
        text = head.rstrip("\n") + ("\n\n### " + rest[1] if len(rest) > 1 else "") + "\n"
    EVAL_LOG.write_text(text.rstrip("\n") + "\n\n" + HEADING + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8")


def run_all(chosen: list[dict], kinds: dict, verbose: bool) -> list[dict]:
    results = []
    for info in chosen:
        result = run_building(info, "svg", info["levels"], kinds)
        rows = [r for r in result["rows"] if r["status"] != "skipped"]
        if verbose:
            print(
                f"[l4q] {info['id']:26s} {info['source']:7s} floors {len(info['levels'])} rooms {result['spaces']:4d} "
                f"questions {len(rows):3d} correct {sum(r['status'] == 'correct' for r in rows):3d} "
                f"unresolved {sum(r['status'] == 'unresolved' for r in rows):3d} {result['seconds']:.0f}s"
            )
        results.append(result)
    return results


def compare_table(compared: list[tuple[str, list[dict]]]) -> list[str]:
    lines = [
        "Comparison (same questions, other reading or other lookup):",
        "",
        "| Reading | Buildings | Questions | Resolved | Correct | Score | Unresolved share | Found from the full name in one call |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for title, results in compared:
        rows = [row for r in results for row in r["rows"] if row["status"] != "skipped"]
        unresolved = sum(row["status"] == "unresolved" for row in rows)
        correct = sum(row["status"] == "correct" for row in rows)
        named = [row for row in rows if row["how"]]
        by_name = sum(row["how"] in ("exact", "name") for row in named)
        lines.append(
            f"| {title} | {len(results)} | {len(rows)} | {len(rows) - unresolved} | {correct} | "
            f"{share(correct, len(rows))} | {share(unresolved, len(rows))} | {share(by_name, len(named))} |"
        )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(prog="level4_questions_eval")
    parser.add_argument("--n", type=int, default=20, help="number of dev buildings")
    parser.add_argument("--compare-vision", action="store_true", help="floor 0 of buildings with a cached extraction")
    parser.add_argument(
        "--no-number-fallback",
        action="store_true",
        help="switch off the room-number fallback of find_space (the state before it was added)",
    )
    parser.add_argument(
        "--compare-fallback", action="store_true", help="also run once with that fallback off and compare"
    )
    parser.add_argument("--no-log", action="store_true", help="do not write docs/eval-log.md")
    arguments = parser.parse_args()
    if arguments.n < 1:
        parser.error("--n must be at least 1")
    if arguments.no_number_fallback:
        find_space_module._by_printed_number = lambda spaces, text: []
    kinds = load_kinds()
    chosen = choose(arguments.n)
    results = run_all(chosen, kinds, True)
    lines = report(results, f"SVG path (svg + building.json scale, no vision), {len(chosen)} dev buildings")
    compared = [("svg path, all floors", results)]
    if arguments.compare_fallback:
        original = find_space_module._by_printed_number
        find_space_module._by_printed_number = lambda spaces, text: []
        try:
            compared.append(("svg path, all floors, find_space without number fallback", run_all(chosen, kinds, False)))
        finally:
            find_space_module._by_printed_number = original
    if arguments.compare_vision:
        cached = [i for i in choose(100) if load_cached(i["id"], 0) is not None]
        for mode, title in (
            ("svg", "floor 0 only, svg (no names, no types)"),
            ("svg+vision", "floor 0 only, svg plus cached vision reading"),
            ("vision", "floor 0 only, cached vision reading of the plain png (old path)"),
        ):
            compared.append((title, [run_building(i, mode, [0], kinds, only_levels={0}) for i in cached]))
    if len(compared) > 1:
        lines += ["", *compare_table(compared)]
    print("\n".join(lines))
    if not arguments.no_log:
        write_log(lines)


if __name__ == "__main__":
    main()
