"""Preflight for an unseen building: cheap structural checks before the expensive agent runs.

Used by scripts/preflight.py. Each check yields Findings (OK / WARN / FAIL, one line, offending ids capped)."""

import itertools
import json
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

import networkx as nx
from shapely.geometry import Point, Polygon

from building_agent.registry import load_kinds
from building_agent.submission import QUESTION_FILES, load_questions
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError
from tests.sweep_inputs import Pools, build_inputs

OK, WARN, FAIL = "OK", "WARN", "FAIL"
ID_CAP = 5
REQUIRED_KEYS = ("building", "floors", "spaces", "openings", "vertical_connectors", "assets")
OPENING_TOLERANCE_M = 1.0
STACKED_SOURCES = {"osm_indoor", "procedural"}  # as in kinds/room_stacked.py
TRAINING_SPLITS = ("train", "dev", "test")


@dataclass
class Finding:
    check: str
    level: str
    message: str
    ids: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


def _f(check: str, level: str, message: str, ids=(), **data) -> Finding:
    ids = [str(i) for i in ids]
    suffix = f" (+{len(ids) - ID_CAP} more)" if len(ids) > ID_CAP else ""
    return Finding(check, level, message + suffix, ids[:ID_CAP], data)


# ---------- 1. loads ----------


def check_loads(directory: Path) -> tuple[list[Finding], dict | None]:
    file = directory / "building.json"
    if not file.exists():
        return [_f("loads", FAIL, f"{file} does not exist")], None
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [_f("loads", FAIL, f"building.json does not parse: {error}")], None
    if not isinstance(raw, dict):
        return [_f("loads", FAIL, "building.json is not a JSON object")], None
    missing = [key for key in REQUIRED_KEYS if key not in raw]
    if missing:
        return [_f("loads", FAIL, f"required keys missing: {', '.join(missing)}", missing)], None
    out = [_f("loads", OK, "building.json parses, all required keys present")]
    try:
        BuildingMap.load(directory)
    except Exception as error:  # noqa: BLE001 - report whatever the kit loader trips over
        return [*out, _f("loads", FAIL, f"BuildingMap.load fails: {type(error).__name__}: {error}")], None
    out.append(_f("loads", OK, "BuildingMap.load works"))

    # BuildingMap.load already indexes by id, so duplicate ids would silently collapse: count them here.
    for key in ("floors", "spaces", "openings", "vertical_connectors", "assets"):
        ids = [item.get("id") for item in raw[key] if isinstance(item, dict)]
        dupes = sorted({i for i in ids if ids.count(i) > 1}, key=str)
        if dupes:
            out.append(_f("ids", FAIL, f"duplicate ids in {key}: {len(dupes)}", dupes))
    if not any(f.check == "ids" for f in out):
        out.append(_f("ids", OK, "ids unique within every list"))

    floors = {f["id"] for f in raw["floors"]}
    spaces = {s["id"] for s in raw["spaces"]}
    bad: dict[str, list[str]] = {}

    def dangling(label: str, owner: str, ref: str, valid: set[str], allow_outside: bool = False) -> None:
        if ref not in valid and not (allow_outside and ref == OUTSIDE):
            bad.setdefault(label, []).append(f"{owner}->{ref}")

    for space in raw["spaces"]:
        dangling("space.floor_id", space["id"], space.get("floor_id"), floors)
    for opening in raw["openings"]:
        dangling("opening.floor_id", opening["id"], opening.get("floor_id"), floors)
        for ref in opening.get("space_ids", []):
            dangling("opening.space_ids", opening["id"], ref, spaces, allow_outside=True)
    for connector in raw["vertical_connectors"]:
        for ref in connector.get("floor_ids", []):
            dangling("connector.floor_ids", connector["id"], ref, floors)
        for ref in connector.get("space_ids", []):
            dangling("connector.space_ids", connector["id"], ref, spaces)
    for asset in raw["assets"]:
        dangling("asset.space_id", asset["id"], asset.get("space_id"), spaces)
        dangling("asset.floor_id", asset["id"], asset.get("floor_id"), floors)
    for label, refs in bad.items():
        out.append(_f("refs", FAIL, f"dangling {label}: {len(refs)}", refs))
    if not bad:
        out.append(_f("refs", OK, "every referenced id exists"))
    return out, raw


# ---------- 2. geometry ----------


def _polygon(space: dict) -> Polygon | None:
    try:
        return Polygon(space["polygon"])
    except Exception:  # noqa: BLE001
        return None


def check_geometry(bm: BuildingMap) -> list[Finding]:
    out: list[Finding] = []
    invalid, repaired_empty, zero_area, unbuildable = [], [], [], []
    polygons: dict[str, Polygon] = {}
    for space_id, space in bm.spaces.items():
        polygon = _polygon(space)
        if polygon is None:
            unbuildable.append(space_id)
            continue
        if not polygon.is_valid:
            invalid.append(space_id)
            polygon = polygon.buffer(0)
            if polygon.is_empty:
                repaired_empty.append(space_id)
        if polygon.area <= 0:
            zero_area.append(space_id)
        polygons[space_id] = polygon
    if unbuildable:
        out.append(_f("geometry", FAIL, f"{len(unbuildable)} spaces have no usable polygon", unbuildable))
    if repaired_empty:
        out.append(
            _f("geometry", FAIL, f"{len(repaired_empty)} invalid polygons vanish under buffer(0)", repaired_empty)
        )
    if zero_area:
        out.append(_f("geometry", FAIL, f"{len(zero_area)} spaces have zero area", zero_area))
    if invalid:
        out.append(
            _f("geometry", WARN, f"{len(invalid)} of {len(bm.spaces)} polygons invalid, need buffer(0)", invalid)
        )
    if not (unbuildable or repaired_empty or zero_area or invalid):
        out.append(_f("geometry", OK, f"all {len(bm.spaces)} polygons valid with non-zero area"))

    far = []
    for opening_id, opening in bm.openings.items():
        sides = [s for s in opening["space_ids"] if s != OUTSIDE and s in polygons]
        if not sides:
            continue
        point = Point(opening["position"])
        if min(polygons[s].exterior.distance(point) for s in sides) > OPENING_TOLERANCE_M:
            far.append(opening_id)
    if far:
        out.append(
            _f("openings", WARN, f"{len(far)} openings farther than {OPENING_TOLERANCE_M} m from their spaces", far)
        )
    else:
        out.append(_f("openings", OK, "all openings lie near the outline of their spaces"))

    elevation_missing = [f["id"] for f in bm.floors.values() if "elevation_m" not in f or "level" not in f]
    if elevation_missing:
        out.append(_f("floors", FAIL, "floors without elevation_m/level", elevation_missing))
    else:
        levels = [f["level"] for f in bm.floors.values()]
        level = FAIL if len(set(levels)) != len(levels) else OK
        out.append(
            _f(
                "floors",
                level,
                f"{len(levels)} floors, levels {sorted(levels)}" + (" (duplicates)" if level == FAIL else ""),
            )
        )

    out.append(_frame_finding(bm, polygons))
    return out


def _frame_finding(bm: BuildingMap, polygons: dict[str, Polygon]) -> Finding:
    source = bm.data["building"].get("source")
    if len(bm.floors) < 2:
        return _f("frame", OK, "single floor, nothing to stack")
    boxes: dict[int, tuple[float, float, float, float]] = {}
    for space_id, polygon in polygons.items():
        level = bm.floors[bm.spaces[space_id]["floor_id"]]["level"]
        x0, y0, x1, y1 = polygon.bounds
        old = boxes.get(level, (x0, y0, x1, y1))
        boxes[level] = (min(old[0], x0), min(old[1], y0), max(old[2], x1), max(old[3], y1))
    weak = []
    ordered = sorted(boxes)
    for low, high in itertools.pairwise(ordered):
        a, b = boxes[low], boxes[high]
        w = min(a[2], b[2]) - max(a[0], b[0])
        h = min(a[3], b[3]) - max(a[1], b[1])
        smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
        if w <= 0 or h <= 0 or smaller <= 0 or w * h / smaller < 0.5:
            weak.append(f"{low}/{high}")
    shared = not weak
    if source in STACKED_SOURCES:
        if shared:
            return _f("frame", OK, f"floors share one XY frame (source {source}); room_stacked applicable")
        return _f("frame", WARN, f"source {source} but floor footprints barely overlap; room_stacked may mislead", weak)
    note = "floors look aligned" if shared else "floors are not aligned"
    return _f(
        "frame",
        WARN,
        f"source '{source}' is not in {sorted(STACKED_SOURCES)}: room_stacked will refuse ({note})",
    )


# ---------- 3. graph ----------


def _vocabulary(root: Path, exclude: Path) -> dict[str, set[str]]:
    vocab: dict[str, set[str]] = {
        k: set() for k in ("type", "room_type", "asset_type", "opening_kind", "connector_kind")
    }
    for split in TRAINING_SPLITS:
        for path in sorted((root / split).glob("*/building.json")) if (root / split).is_dir() else []:
            if path.parent.resolve() == exclude.resolve():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                vocab["type"] |= {s["type"] for s in data["spaces"]}
                vocab["room_type"] |= {s["room_type"] for s in data["spaces"]}
                vocab["asset_type"] |= {a["type"] for a in data["assets"]}
                vocab["opening_kind"] |= {o["kind"] for o in data["openings"]}
                vocab["connector_kind"] |= {c["kind"] for c in data["vertical_connectors"]}
            except (OSError, ValueError, KeyError, TypeError):
                continue
    return vocab


def check_graph(bm: BuildingMap, directory: Path, data_root: Path | None) -> list[Finding]:
    out: list[Finding] = []
    entrances = [o for o in bm.openings.values() if OUTSIDE in o["space_ids"]]
    if not entrances:
        out.append(_f("entrances", FAIL, "no opening connects to 'outside': nothing is reachable"))
    else:
        free = sum(1 for o in entrances if o["step_free"])
        out.append(
            _f(
                "entrances",
                OK if free else WARN,
                f"{len(entrances)} entrances, {free} step-free" + ("" if free else " (none!)"),
            )
        )
    for step_free in (False, True):
        label = "step-free" if step_free else "normal"
        graph = bm.graph(step_free)
        reach = nx.node_connected_component(graph, OUTSIDE) if OUTSIDE in graph else set()
        unreachable = sorted(s for s in bm.spaces if s not in reach)
        share = len(unreachable) / max(len(bm.spaces), 1)
        level = OK if not unreachable else (FAIL if (not step_free and share > 0.5) else WARN)
        out.append(
            _f(
                "reachable",
                level,
                f"{label}: {len(bm.spaces) - len(unreachable)}/{len(bm.spaces)} spaces reachable from outside",
                unreachable,
            )
        )

    levels = sorted(f["level"] for f in bm.floors.values() if "level" in f)
    bad = []
    for connector_id, connector in bm.connectors.items():
        stop_levels = sorted(bm.floors[f]["level"] for f in connector["floor_ids"] if f in bm.floors)
        if (
            len(stop_levels) < 2
            or any(
                levels.index(b) - levels.index(a) != 1
                for a, b in itertools.pairwise(stop_levels)
                if a in levels and b in levels
            )
            or len(connector["floor_ids"]) != len(connector["space_ids"])
        ):
            bad.append(connector_id)
    if bad:
        out.append(_f("connectors", WARN, f"{len(bad)} connectors skip a level or have mismatched stops", bad))
    else:
        out.append(_f("connectors", OK, f"{len(bm.connectors)} connectors join consecutive levels"))

    if data_root is None or not data_root.is_dir():
        out.append(_f("vocabulary", WARN, "no training data directory found; vocabulary not compared"))
        return out
    vocab = _vocabulary(data_root, directory)
    if not any(vocab.values()):
        out.append(_f("vocabulary", WARN, "no training buildings found; vocabulary not compared"))
        return out
    here = {
        "type": {s["type"] for s in bm.spaces.values()},
        "room_type": {s["room_type"] for s in bm.spaces.values()},
        "asset_type": {a["type"] for a in bm.assets.values()},
        "opening_kind": {o["kind"] for o in bm.openings.values()},
        "connector_kind": {c["kind"] for c in bm.connectors.values()},
    }
    new = {k: sorted(here[k] - vocab[k]) for k in here if here[k] - vocab[k]}
    if new:
        for key, values in new.items():
            out.append(_f("vocabulary", WARN, f"new {key} values not in training data: {', '.join(values)}", values))
    else:
        out.append(_f("vocabulary", OK, "all type/room_type/asset/opening/connector values known from training data"))
    return out


# ---------- 4. kinds ----------


def _summary(error: BaseException) -> str:
    frames = traceback.extract_tb(error.__traceback__)
    where = f" at {Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else ""
    return f"{type(error).__name__}: {error}{where}"


def check_kinds(directory: Path, bm: BuildingMap) -> list[Finding]:
    out: list[Finding] = []
    kinds = load_kinds()
    try:
        pools = Pools(bm, directory.name)
    except Exception as error:  # noqa: BLE001
        return [_f("kinds", FAIL, f"cannot derive sweep inputs from this building: {_summary(error)}")]
    for name in sorted(kinds):
        start = time.perf_counter()
        try:
            inputs = build_inputs(name, pools)
        except KeyError:
            out.append(_f(f"kind:{name}", WARN, "no input generator in tests/sweep_inputs.py; not exercised"))
            continue
        except Exception as error:  # noqa: BLE001
            out.append(_f(f"kind:{name}", FAIL, f"input generation failed: {_summary(error)}"))
            continue
        crashes, refusals, ran = [], 0, 0
        for kwargs in inputs:
            try:
                kinds[name].fn(BuildingMap(bm.data), **kwargs)
                ran += 1
            except MapError:
                refusals += 1
            except Exception as error:  # noqa: BLE001
                crashes.append(_summary(error))
        seconds = time.perf_counter() - start
        if crashes:
            out.append(
                _f(
                    f"kind:{name}",
                    FAIL,
                    f"{len(crashes)}/{len(inputs)} calls crashed: {crashes[0]}",
                    crashes,
                    seconds=seconds,
                )
            )
        elif ran == 0:
            out.append(
                _f(
                    f"kind:{name}",
                    WARN,
                    f"all {refusals} calls refused with MapError ({seconds:.2f}s)",
                    seconds=seconds,
                )
            )
        else:
            out.append(_f(f"kind:{name}", OK, f"{ran} ok, {refusals} MapError ({seconds:.2f}s)", seconds=seconds))
    out.extend(_check_routes(bm))
    return out


def _check_routes(bm: BuildingMap) -> list[Finding]:
    out: list[Finding] = []
    spaces = sorted(bm.spaces)
    if len(spaces) < 2:
        return [_f("route", WARN, "fewer than two spaces, no route to test")]
    # A far-apart pair makes the route exercise stairs/lifts where possible.
    first = spaces[0]
    second = max(
        spaces,
        key=lambda s: abs(
            bm.floors[bm.spaces[s]["floor_id"]]["level"] - bm.floors[bm.spaces[first]["floor_id"]]["level"]
        ),
    )
    for step_free in (False, True):
        label = "step-free route" if step_free else "route"
        start = time.perf_counter()
        try:
            result = BuildingMap(bm.data).route(first, second, step_free=step_free)
            out.append(
                _f(
                    "route",
                    OK,
                    f"{label} {first} -> {second}: {result.length_m} m ({time.perf_counter() - start:.2f}s)",
                )
            )
        except MapError as error:
            out.append(_f("route", WARN, f"{label} refused: {error}"))
        except Exception as error:  # noqa: BLE001
            out.append(_f("route", FAIL, f"{label} crashed: {_summary(error)}"))
    return out


# ---------- 5. questions ----------


def check_questions(directory: Path) -> list[Finding]:
    files = [directory / name for name in QUESTION_FILES if (directory / name).exists()]
    if not files:
        return [_f("questions", OK, "no questions file next to the building (nothing to check)")]
    try:
        questions = load_questions(files[0])
    except ValueError as error:
        if str(error).startswith("no questions found"):
            return [_f("questions", WARN, f"{files[0].name} is empty")]
        return [_f("questions", FAIL, f"{files[0].name} does not load: {_summary(error)}")]
    except Exception as error:  # noqa: BLE001
        return [_f("questions", FAIL, f"{files[0].name} does not load: {_summary(error)}")]
    out = [_f("questions", OK, f"{files[0].name}: {len(questions)} questions")]
    known = set(load_kinds())
    try:
        from building_agent.submission import read_records

        records = read_records(files[0])
    except Exception:  # noqa: BLE001
        return out
    counts: dict[str, int] = {}
    for record in records:
        kind = record.get("kind")
        if kind is not None:
            counts[str(kind)] = counts.get(str(kind), 0) + 1
    if counts:
        out.append(
            _f("questions", OK, "per kind: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())), counts=counts)
        )
        unknown = sorted(set(counts) - known)
        if unknown:
            out.append(_f("questions", WARN, f"no KIND for: {', '.join(unknown)}", unknown))
    else:
        out.append(_f("questions", WARN, "questions carry no 'kind' field; cannot count per kind (free text only)"))
    return out


# ---------- driver ----------


def run(directory: Path, data_root: Path | None = None) -> list[Finding]:
    if data_root is None:
        for candidate in (Path("data"), Path(__file__).resolve().parent.parent / "data"):
            if candidate.is_dir():
                data_root = candidate
                break
    findings, raw = check_loads(directory)
    if raw is not None and not any(f.level == FAIL for f in findings):
        bm = BuildingMap.load(directory)
        steps = (
            lambda: check_geometry(bm),
            lambda: check_graph(bm, directory, data_root),
            lambda: check_kinds(directory, bm),
        )
        for step in steps:
            try:
                findings += step()
            except Exception as error:  # noqa: BLE001 - a broken building must not kill the report
                findings.append(_f("preflight", FAIL, f"check aborted: {_summary(error)}"))
    elif raw is not None:
        findings.append(_f("preflight", WARN, "structural FAILs above: geometry, graph and kind checks skipped"))
    findings += check_questions(directory)
    return findings


def to_json(findings: list[Finding]) -> str:
    worst = FAIL if any(f.level == FAIL for f in findings) else WARN if any(f.level == WARN for f in findings) else OK
    return json.dumps({"status": worst, "findings": [asdict(f) for f in findings]}, indent=2)


def render(findings: list[Finding]) -> str:
    lines = []
    for f in findings:
        ids = f"  [{', '.join(f.ids)}]" if f.ids and f.level != OK else ""
        lines.append(f"{f.level:<4}  {f.check:<22} {f.message}{ids}")
    counts = {lvl: sum(f.level == lvl for f in findings) for lvl in (OK, WARN, FAIL)}
    lines.append(f"\n{counts[OK]} OK, {counts[WARN]} WARN, {counts[FAIL]} FAIL")
    return "\n".join(lines)
