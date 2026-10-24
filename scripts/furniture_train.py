"""Train and evaluate the furniture model (room types and asset types from the furniture glyphs of the plan svg).

Offline, no API. Reads data/train (and data/dev with --with-dev); data/test is never touched.

  uv run python scripts/furniture_train.py --eval            # leave-one-building-out and leave-one-source-out report
  uv run python scripts/furniture_train.py --write           # fit on data/train, write building_agent/level4/furniture_model.json

The truth (room types, assets) comes from building.json; the plan side (rooms, glyphs) from the svg. The building
scale used here is the true one (width of the svg rooms against width of the spaces), as the questions eval does."""

import argparse
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shapely.geometry import Point, Polygon

from building_agent.level4 import furniture as fm
from building_agent.level4.svg_read import read_svg

DATA = Path("data")
CACHE = Path("agent_output") / "furniture_samples.pkl"
IMPORTANT = ["kitchen", "office", "meeting_room", "toilet", "bathroom", "bedroom", "living_room", "storage"]


def source_of(name: str) -> str:
    if name.startswith("proc"):
        return "proc-factory" if "factory" in name else "proc-campus"
    return name.split("-")[0]


def load_samples(splits: tuple[str, ...]) -> list[dict]:
    samples = []
    for split in splits:
        for directory in sorted((DATA / split).iterdir()):
            if (directory / "building.json").exists():
                samples.extend(building_samples(directory))
    return samples


def to_px(frame: tuple, x: float, y: float) -> tuple[float, float]:
    """Metres (y up) to plan pixels (y down) from the corner pairing of the room extents."""
    left, bottom, x_min, y_min, px_per_m = frame
    return left + (x - x_min) * px_per_m, bottom - (y - y_min) * px_per_m


def building_samples(directory: Path) -> list[dict]:
    truth = json.loads((directory / "building.json").read_text(encoding="utf-8"))
    out = []
    for floor in truth["floors"]:
        level = floor["level"]
        path = directory / f"floor_{level}.svg"
        plan = read_svg(path) if path.exists() else None
        if plan is None:
            continue
        spaces = [s for s in truth["spaces"] if s["floor_id"] == floor["id"]]
        xs = [x for s in spaces for x, _ in s["polygon"]]
        ys = [y for s in spaces for _, y in s["polygon"]]
        pxs = [x for r in plan.rooms for x, _ in r.polygon_px]
        pys = [y for r in plan.rooms for _, y in r.polygon_px]
        px_per_m = (max(pxs) - min(pxs)) / (max(xs) - min(xs))

        frame = (min(pxs), max(pys), min(xs), min(ys), px_per_m)

        truth_shapes = [(s, Polygon([to_px(frame, x, y) for x, y in s["polygon"]])) for s in spaces]
        glyphs = fm.read_glyphs(path.read_text(encoding="utf-8"))
        polygons = [r.polygon_px for r in plan.rooms]
        fills = [r.fill for r in plan.rooms]
        held = fm.glyphs_by_room(polygons, glyphs)
        corridor = fm.corridor_flags(polygons, fills, px_per_m)
        assets = [(Point(*to_px(frame, *a["position"])), a) for a in truth["assets"] if a["floor_id"] == floor["id"]]
        for room, room_glyphs, flag in zip(plan.rooms, held, corridor):
            centre = Polygon(room.polygon_px).representative_point()
            holder = [s for s, p in truth_shapes if p.is_valid and p.contains(centre)]
            if not holder:
                continue
            item = fm.RoomInput(room.polygon_px, room.ref, room.fill, room_glyphs, flag)
            glyph_truth = []
            for glyph, (key, rank) in zip(room_glyphs, fm.glyph_ranks(room_glyphs, px_per_m), strict=True):
                near = min(assets, key=lambda pa: pa[0].distance(Point(glyph.x, glyph.y)), default=None)
                ok = near is not None and near[0].distance(Point(glyph.x, glyph.y)) < 0.3 * px_per_m
                glyph_truth.append((key, rank, near[1]["type"] if ok else None))
            out.append(
                {
                    "b": directory.name,
                    "src": source_of(directory.name),
                    "label": holder[0]["room_type"],
                    "fill": room.fill,
                    "input": item,
                    "px_per_m": px_per_m,
                    "level": level,
                    "n_rooms": len(plan.rooms),
                    "glyphs": glyph_truth,
                }
            )
    return out


def tokens_of(sample: dict) -> dict[str, float]:
    return fm.room_tokens(sample["input"], sample["px_per_m"], sample["level"], sample["n_rooms"])


def fit(samples: list[dict]) -> fm.Model:
    model = fm.Model(fm.RoomTypeModel(), fm.AssetTypeTable())
    for sample in samples:
        add(model, sample, 1)
    return model


def add(model: fm.Model, sample: dict, sign: int) -> None:
    if sample["fill"] in fm.CLASSIFIED_FILLS:
        model.rooms.add(sample["label"], sample["tokens"], sign)
    for key, rank, asset_type in sample["glyphs"]:
        if asset_type:
            model.assets.add(key, sample["label"], asset_type, rank, sign)


def evaluate(samples: list[dict]) -> None:
    for sample in samples:
        sample["tokens"] = tokens_of(sample)
    full = fit(samples)
    for protocol in ("building", "source"):
        report(protocol, samples, full)


def leave_out(protocol: str, samples: list[dict], full: fm.Model) -> tuple[list, list]:
    """(room rows, asset rows) predicted with every building (or source) held out of the model in turn."""
    groups = defaultdict(list)
    for sample in samples:
        groups[sample["b"] if protocol == "building" else sample["src"]].append(sample)
    rows = []  # (src, truth, predicted, confidence)
    assets = []  # (src, truth type, predicted or None)
    for held in groups.values():
        for sample in held:
            add(full, sample, -1)
        for sample in held:
            rows_and_assets(full, sample, rows, assets)
        for sample in held:
            add(full, sample, 1)
    return rows, assets


def report(protocol: str, samples: list[dict], full: fm.Model) -> None:
    rows, assets = leave_out(protocol, samples, full)
    print(f"\n===== leave-one-{protocol}-out =====")
    print_rooms(rows)
    print_assets(assets)


def rows_and_assets(model: fm.Model, sample: dict, rows: list, assets: list) -> None:
    context = fm.asset_context(sample["fill"])
    if sample["fill"] in fm.CLASSIFIED_FILLS:
        label, confidence = model.rooms.predict(sample["tokens"])
        rows.append((sample["src"], sample["label"], label, confidence))
        context = label if confidence >= fm.ROOM_CONFIDENCE else None
    for key, rank, asset_type in sample["glyphs"]:
        if asset_type is None:
            continue
        found = model.assets.predict(key, context, rank)
        sure = found if found and found[1] >= fm.ASSET_CONFIDENCE else None
        assets.append((sample["src"], asset_type, sure[0] if sure else None))


def print_rooms(rows: list) -> None:
    for threshold in (0.0, fm.ROOM_CONFIDENCE, 0.95):
        print(f"-- room types, confidence >= {threshold}")
        for src in sorted({r[0] for r in rows}) + ["ALL"]:
            part = [r for r in rows if src == "ALL" or r[0] == src]
            done = [r for r in part if r[3] >= threshold and r[2] != fm.GENERIC]
            right = sum(1 for r in done if r[1] == r[2])
            # accuracy over all rooms when the generic fallback counts as "no type" (right only for true generic)
            overall = sum(1 for r in part if (r[2] if r[3] >= threshold else fm.GENERIC) == r[1]) / len(part)
            print(
                f"  {src:13s} rooms {len(part):6d}  typed {len(done):6d} ({len(done) / len(part):.0%})"
                f"  precision of typed {right / max(len(done), 1):.1%}  overall acc {overall:.1%}"
            )
    print("-- per type at the shipped threshold (precision, recall, support), all sources")
    for label in IMPORTANT:
        truth = [r for r in rows if r[1] == label]
        said = [r for r in rows if r[2] == label and r[3] >= fm.ROOM_CONFIDENCE]
        hit = sum(1 for r in said if r[1] == label)
        recall_hit = sum(1 for r in truth if r[2] == label and r[3] >= fm.ROOM_CONFIDENCE)
        print(
            f"  {label:13s} precision {hit / max(len(said), 1):.1%}  recall {recall_hit / max(len(truth), 1):.1%}  n={len(truth)}"
        )
    print("-- confusion for important types (truth -> predicted at threshold, top 4)")
    for label in IMPORTANT:
        counts = Counter(r[2] if r[3] >= fm.ROOM_CONFIDENCE else "(generic)" for r in rows if r[1] == label)
        print(f"  {label:13s} {counts.most_common(4)}")


def print_assets(assets: list) -> None:
    print("-- asset types at the shipped threshold, all sources")
    truth_counts = Counter(a[1] for a in assets)
    said = Counter(a[2] for a in assets if a[2])
    hit = Counter(a[1] for a in assets if a[1] == a[2])
    listed = sum(said.values())
    print(
        f"  listed {listed} of {len(assets)} glyphs ({listed / len(assets):.1%}), precision {sum(hit.values()) / listed:.1%}"
    )
    for src in sorted({a[0] for a in assets}):
        part = [a for a in assets if a[0] == src]
        got = [a for a in part if a[2]]
        print(
            f"  {src:13s} listed {len(got) / len(part):.1%} precision {sum(1 for a in got if a[1] == a[2]) / max(len(got), 1):.1%}"
        )
    worst = []
    for asset_type, n in truth_counts.items():
        precision = hit[asset_type] / said[asset_type] if said[asset_type] else None
        worst.append((asset_type, n, precision, hit[asset_type] / n))
    print("  type: n, precision, recall (types below 0.8 precision first)")
    for asset_type, n, precision, recall in sorted(worst, key=lambda r: r[2] if r[2] is not None else -1):
        if n >= 20:
            shown = "n/a" if precision is None else f"{precision:.1%}"
            print(f"   {asset_type:28s} n={n:5d} precision {shown:>6s} recall {recall:.1%}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--with-dev", action="store_true", help="include data/dev (eval and write)")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    splits = ("train", "dev") if args.with_dev else ("train",)
    cache = CACHE.with_name(f"furniture_samples_{'_'.join(splits)}.pkl")
    if cache.exists() and not args.refresh:
        samples = pickle.loads(cache.read_bytes())
    else:
        samples = load_samples(splits)
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(pickle.dumps(samples))
    print(f"{len(samples)} rooms from {len({s['b'] for s in samples})} buildings ({', '.join(splits)})")
    if args.eval:
        evaluate(samples)
    if args.write:
        for sample in samples:
            sample["tokens"] = tokens_of(sample)
        model = fit(samples)
        rows, assets = leave_out("building", samples, model)
        typed = [r for r in rows if r[3] >= fm.ROOM_CONFIDENCE and r[2] != fm.GENERIC]
        listed = [a for a in assets if a[2]]
        model.meta = {
            "buildings": len({s["b"] for s in samples}),
            "room_precision": round(sum(r[1] == r[2] for r in typed) / max(len(typed), 1), 3),
            "room_typed_share": round(len(typed) / max(len(rows), 1), 3),
            "asset_precision": round(sum(a[1] == a[2] for a in listed) / max(len(listed), 1), 3),
        }
        model.save()
        print(f"wrote {fm.MODEL_PATH}")


if __name__ == "__main__":
    main()
