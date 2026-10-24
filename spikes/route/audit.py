# ruff: noqa: RUF015
"""Runtime of the geodesic build on the largest building and an audit of forklift/bay semantics in the data.

Run: uv run python -m spikes.route.audit
"""

import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from spikes.route.geodesic import RouteModel
from starter_agent.building_map import BuildingMap

DATA = Path("data")
BAY_TYPES = {"production_zone", "additive_zone", "assembly_zone", "warehouse_zone", "logistics_zone"}


def all_buildings() -> list[tuple[str, str, Path]]:
    rows = []
    with (DATA / "manifest.csv").open() as handle:
        for r in csv.DictReader(handle):
            rows.append((r["building_id"], r["source"], DATA / r["path"]))
    return rows


def runtime() -> None:
    rows = all_buildings()
    sized = []
    for bid, src, path in rows:
        b = json.loads((path / "building.json").read_text())
        verts = sum(len(s["polygon"]) for s in b["spaces"])
        sized.append((len(b["spaces"]), len(b["openings"]), verts, bid, src, path))
    sized.sort(reverse=True)
    print("largest by spaces:", [(s[3], s[0], s[1], s[2]) for s in sized[:3]])
    for spaces, openings, verts, bid, src, path in sized[:3]:
        bm = BuildingMap.load(path)
        model = RouteModel(bm)
        t = time.perf_counter()
        graph = model.build()
        dt = time.perf_counter() - t
        fallbacks = sum(g.fallback for g in model.geoms.values())
        reflex = sum(len(g.verts) for g in model.geoms.values())
        print(
            f"{bid} ({src}): spaces={spaces} openings={openings} vertices={verts} "
            f"graph nodes={graph.number_of_nodes()} edges={graph.number_of_edges()} "
            f"build={dt:.1f}s shrink-fallback spaces={fallbacks} reflex vertices={reflex}"
        )
        t = time.perf_counter()
        first, last = list(bm.spaces)[0], list(bm.spaces)[-1]
        model.best_route(first, last)
        print(f"   one query after build: {(time.perf_counter() - t) * 1000:.0f} ms")


def semantics() -> None:
    by_source = defaultdict(Counter)
    widths = defaultdict(list)
    wide_kinds = defaultdict(Counter)
    names = Counter()
    bay_in_buildings = defaultdict(set)
    corridor_like = defaultdict(Counter)
    for bid, src, path in all_buildings():
        b = json.loads((path / "building.json").read_text())
        spaces = {s["id"]: s for s in b["spaces"]}
        for s in b["spaces"]:
            if s["room_type"] in BAY_TYPES:
                by_source[src][s["room_type"]] += 1
                bay_in_buildings[src].add(bid)
            low = s["name"].lower()
            if "aisle" in low or "forklift" in low or "gang" in low or "fahr" in low:
                names[(src, s["name"].split()[0])] += 1
            if s["type"] in ("corridor", "hall"):
                corridor_like[src][s["type"]] += 1
        for o in b["openings"]:
            widths[src].append(o["width_m"])
            if o["width_m"] >= 3.0:
                types = tuple(sorted(spaces[s]["room_type"] if s in spaces else "outside" for s in o["space_ids"]))
                wide_kinds[src][(o["kind"], types)] += 1
    print("\nbay-like room types per source (all splits):", {k: dict(v) for k, v in by_source.items()})
    print("buildings with bays:", {k: len(v) for k, v in bay_in_buildings.items()})
    print("aisle-named spaces:", dict(names))
    print("corridor/hall counts:", {k: dict(v) for k, v in corridor_like.items()})
    for src, ws in widths.items():
        ws.sort()
        print(
            f"opening width {src}: n={len(ws)} min={ws[0]} p50={ws[len(ws) // 2]} max={ws[-1]} >=3m: {sum(w >= 3 for w in ws)}"
        )
    for src, c in wide_kinds.items():
        print(f"openings >= 3 m in {src}:")
        for k, v in c.most_common(12):
            print("   ", v, k)


if __name__ == "__main__":
    runtime()
    semantics()
