# ruff: noqa: C408
"""Quantify how far the kit's coarse optimum is from the geodesic optimum.

Run: uv run python -m spikes.route.evaluate [--cap-route 100] [--cap-other 40]
"""

import argparse
import json
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

from spikes.route.geodesic import RouteModel, model_for
from starter_agent.building_map import BuildingMap, MapError

DATA = Path("data")
SOURCES = ["osm", "proc", "resplan", "swiss"]
# model name -> kwargs for the model whose OWN optimum becomes "our sequence"
VARIANTS = {
    "anchor-kit": dict(metric="anchor", vertical="kit"),  # = BuildingMap.route (checked separately)
    "anchor-synera": dict(metric="anchor", vertical="synera"),
    "straight-kit": dict(metric="straight", vertical="kit"),
    "straight-synera": dict(metric="straight", vertical="synera"),
}


def load_cases(cap_route: int, cap_other: int, seed: int = 7) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    pools: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for path in sorted(DATA.glob("*/*/questions_basic.jsonl")):
        if path.parts[1] not in ("dev", "train"):
            continue
        for line in path.read_text().splitlines():
            q = json.loads(line)
            src = q["building_id"].split("-")[0]
            a = q["answer"]
            if q["kind"] in ("route", "route_step_free"):
                if a.get("reachable") is False:
                    group, case = "route", dict(q, step_free=q["kind"] == "route_step_free", legs=None)
                    case.update(start=a["from_space_id"], end=a["to_space_id"], closed=None, unreachable=True)
                else:
                    group = "route"
                    case = dict(start=a["from_space_id"], end=a["to_space_id"], closed=None, unreachable=False)
                case.update(building=q["building_id"], kind=q["kind"], step_free=q["kind"] == "route_step_free")
                case["labelled"] = a.get("space_path")
                pools[(src, group)].append(case)
            elif q["kind"] == "route_with_closure":
                case = dict(building=q["building_id"], kind=q["kind"], step_free=False, closed=a["closed_element_id"])
                case.update(start=a["from_space_id"], end=a["to_space_id"], labelled=a.get("space_path"))
                case["unreachable"] = a.get("reachable") is False
                pools[(src, "other")].append(case)
            elif q["kind"] == "tour":
                for leg in a["legs"]:
                    case = dict(building=q["building_id"], kind="tour_leg", step_free=False, closed=None)
                    case.update(start=leg["from_space_id"], end=leg["to_space_id"], labelled=leg.get("space_path"))
                    case["unreachable"] = leg.get("reachable") is False
                    pools[(src, "other")].append(case)
    out: dict[str, list[dict]] = {}
    for src in SOURCES:
        cases = []
        for group, cap in (("route", cap_route), ("other", cap_other)):
            pool = pools[(src, group)]
            rng.shuffle(pool)
            cases += pool[:cap]
        out[src] = cases
    return out


def building_path(building_id: str) -> Path:
    for split in ("dev", "train"):
        p = DATA / split / building_id
        if p.exists():
            return p
    raise FileNotFoundError(building_id)


def pct(values: list[float], q: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, max(0, int(q * (len(values) - 1))))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap-route", type=int, default=100)
    ap.add_argument("--cap-other", type=int, default=40)
    ap.add_argument("--out", default="spikes/route/results.json")
    args = ap.parse_args()
    cases = load_cases(args.cap_route, args.cap_other)
    bms: dict[str, BuildingMap] = {}
    rows = []
    t0 = time.time()
    for src, items in cases.items():
        for c in items:
            bm = bms.get(c["building"]) or bms.setdefault(c["building"], BuildingMap.load(building_path(c["building"])))
            bm.closed = {c["closed"]} if c["closed"] else set()
            row = dict(src=src, building=c["building"], kind=c["kind"], start=c["start"], end=c["end"])
            truth = model_for(bm, step_free=c["step_free"], closed=bm.closed)
            best = truth.best_route(c["start"], c["end"])
            try:
                ours = bm.route(c["start"], c["end"], step_free=c["step_free"]).space_path
            except MapError:
                ours = None
            row["unreachable_label"] = c["unreachable"]
            row["kit_none"] = ours is None
            row["geo_none"] = best is None
            row["same_as_label"] = bool(c["labelled"]) and ours == c["labelled"]
            if ours is None or best is None:
                rows.append(row)
                continue
            row["best"] = best[1]
            measured = truth.measure(ours)
            row["coarse_len"] = measured
            row["coarse"] = None if measured is None else (best[1] / measured if measured > 0 else 1.0)
            anchor_truth = model_for(bm, step_free=c["step_free"], closed=bm.closed, endpoints="anchor")
            best_a, meas_a = anchor_truth.best_route(c["start"], c["end"]), anchor_truth.measure(ours)
            row["coarse_anchor_endpoints"] = None if not meas_a or not best_a else best_a[1] / meas_a
            for name, kw in VARIANTS.items():
                if name == "anchor-kit":
                    continue
                model = RouteModel(bm, step_free=c["step_free"], closed=set(bm.closed), **kw)
                choice = model.best_route(c["start"], c["end"])
                m = truth.measure(choice[0]) if choice else None
                row[name] = None if m is None else (best[1] / m if m > 0 else 1.0)
            rows.append(row)
    print(f"cases {len(rows)} in {time.time() - t0:.0f}s")
    Path(args.out).write_text(json.dumps(rows))
    report(rows)


def report(rows: list[dict]) -> None:
    models = ["coarse", "anchor-synera", "straight-kit", "straight-synera", "coarse_anchor_endpoints"]
    print("\nper source and model: n, share>=0.99, median, p5, min, invalid")
    for model in models:
        print(f"-- {model}")
        for src in [*SOURCES, "ALL"]:
            sel = [r for r in rows if (src == "ALL" or r["src"] == src) and "best" in r]
            vals = [r[model] for r in sel if r.get(model) is not None]
            invalid = sum(1 for r in sel if r.get(model) is None)
            if not vals:
                continue
            full = sum(v >= 0.99 for v in vals) / len(vals)
            print(
                f"{src:8s} n={len(vals):4d} full={full:5.1%} med={statistics.median(vals):.4f} "
                f"p5={pct(vals, 0.05):.3f} min={min(vals):.3f} invalid={invalid}"
            )
    print("\nreachability mismatch (kit none vs geodesic none):")
    for r in rows:
        if r["kit_none"] != r["geo_none"]:
            print(r["building"], r["start"], r["end"], "kit_none", r["kit_none"], "geo_none", r["geo_none"])
    print("\nsame sequence as label:", sum(r["same_as_label"] for r in rows), "of", len(rows))
    print("\nworst 5 coarse per source")
    for src in SOURCES:
        sel = sorted((r for r in rows if r["src"] == src and r.get("coarse") is not None), key=lambda r: r["coarse"])
        for r in sel[:5]:
            print(
                src,
                r["building"],
                r["kind"],
                r["start"][-9:],
                r["end"][-9:],
                f"{r['coarse']:.3f}",
                f"best={r['best']:.1f}",
            )


if __name__ == "__main__":
    main()
