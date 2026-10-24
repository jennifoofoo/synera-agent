"""Measure an extraction against the original building.json of the same floor.

uv run python -m spikes.level4.measure   (reads spikes/level4/outputs/*_run1.json, writes results.json)"""

import itertools
import json
import random
import statistics
import sys
from pathlib import Path

import networkx as nx
from shapely.geometry import Polygon

from spikes.level4.convert import bbox, convert, metres_per_pixel
from spikes.level4.extract import OUT, find_building, parse_json
from starter_agent.building_map import BuildingMap, MapError

TOLERANCE_M = 2.0
N_ROUTES = 5


def load_floor(building_id: str, floor_index: int) -> dict:
    data = json.loads((find_building(building_id) / "building.json").read_text())
    floor = sorted(data["floors"], key=lambda f: f["level"])[floor_index]
    spaces = [s for s in data["spaces"] if s["floor_id"] == floor["id"]]
    openings = [o for o in data["openings"] if o["floor_id"] == floor["id"]]
    return {"building": data["building"], "floors": [floor], "spaces": spaces, "openings": openings}


def full_map(fragment: dict) -> dict:
    return {
        "building": {"id": "x", "name": "x", "source": "x"},
        "floors": fragment["floors"],
        "spaces": fragment["spaces"],
        "openings": fragment["openings"],
        "vertical_connectors": [],
        "assets": [],
    }


def shift(fragment: dict, dx: float, dy: float) -> None:
    for space in fragment["spaces"]:
        space["polygon"] = [[x + dx, y + dy] for x, y in space["polygon"]]
    for opening in fragment["openings"]:
        opening["position"] = [opening["position"][0] + dx, opening["position"][1] + dy]


def match_rooms(true_spaces: list[dict], gen_spaces: list[dict]) -> dict[str, str]:
    """Greedy one-to-one matching of generated to true rooms by centroid distance."""
    true_centroid = {s["id"]: Polygon(s["polygon"]).centroid for s in true_spaces}
    gen_centroid = {s["id"]: Polygon(s["polygon"]).centroid for s in gen_spaces}
    pairs = sorted(
        (true_centroid[t["id"]].distance(gen_centroid[g["id"]]), t["id"], g["id"])
        for t in true_spaces
        for g in gen_spaces
    )
    used_t, used_g, matched = set(), set(), {}
    for distance, true_id, gen_id in pairs:
        if distance > TOLERANCE_M:
            break
        if true_id in used_t or gen_id in used_g:
            continue
        used_t.add(true_id)
        used_g.add(gen_id)
        matched[gen_id] = true_id
    return matched


def route_length(map_data: dict, start: str, end: str) -> float | None:
    try:
        return BuildingMap(map_data).route(start, end).length_m
    except MapError:
        return None


def measure(building_id: str, floor_index: int, scale_mode: str, record: dict) -> dict:
    truth = load_floor(building_id, floor_index)
    extraction = record["extraction"]
    rooms = [r for r in extraction["rooms"] if len(r.get("polygon_px") or []) >= 3]
    tx0, ty0, tx1, _ty1 = bbox([p for s in truth["spaces"] for p in s["polygon"]])
    scale = metres_per_pixel(extraction, scale_mode, tx1 - tx0)
    result: dict = {"building": building_id, "scale_mode": scale_mode}
    if scale is None:
        return {**result, "error": "no scale available"}
    gen_x0, _, gen_x1, _ = bbox([p for r in rooms for p in r["polygon_px"]])
    true_scale = (tx1 - tx0) / (gen_x1 - gen_x0)
    result["scale_error_rel"] = round(scale / true_scale - 1, 3)
    fragment = convert(extraction, building_id, truth["floors"][0]["level"], scale)
    gx0, gy0, _, _ = bbox([p for s in fragment["spaces"] for p in s["polygon"]])
    shift(fragment, tx0 - gx0, ty0 - gy0)

    true_spaces, gen_spaces = truth["spaces"], fragment["spaces"]
    matched = match_rooms(true_spaces, gen_spaces)
    true_area = {s["id"]: Polygon(s["polygon"]).area for s in true_spaces}
    gen_area = {s["id"]: Polygon(s["polygon"]).area for s in gen_spaces}
    area_errors = [abs(gen_area[g] - true_area[t]) / true_area[t] for g, t in matched.items()]
    result["rooms"] = {
        "true": len(true_spaces),
        "found": len(gen_spaces),
        "matched": len(matched),
        "recall": round(len(matched) / len(true_spaces), 2),
        "precision": round(len(matched) / len(gen_spaces), 2),
        "area_err_median": round(statistics.median(area_errors), 3) if area_errors else None,
        "area_err_worst": round(max(area_errors), 3) if area_errors else None,
    }

    def pair_set(openings: list[dict], mapping: dict[str, str] | None) -> set[frozenset]:
        pairs = set()
        for opening in openings:
            ids = opening["space_ids"]
            if "outside" in ids or opening["kind"] == "entrance":
                continue
            if mapping is not None:
                ids = [mapping.get(i) for i in ids]
                if None in ids:
                    continue
            pairs.add(frozenset(ids))
        return pairs

    true_pairs = pair_set(truth["openings"], None)
    gen_pairs = pair_set(fragment["openings"], matched)
    gen_pairs_all = {frozenset(o["space_ids"]) for o in fragment["openings"] if "outside" not in o["space_ids"]}
    hits = true_pairs & gen_pairs
    true_entrances = sum(1 for o in truth["openings"] if "outside" in o["space_ids"])
    gen_entrances = sum(1 for o in fragment["openings"] if "outside" in o["space_ids"])
    result["doors"] = {
        "true_internal": len(true_pairs),
        "found_internal": len(gen_pairs_all),
        "correct_pairs": len(hits),
        "recall": round(len(hits) / len(true_pairs), 2) if true_pairs else None,
        "precision": round(len(hits) / len(gen_pairs_all), 2) if gen_pairs_all else None,
        "entrances_true": true_entrances,
        "entrances_found": gen_entrances,
        "dropped_by_converter": len(fragment["warnings"]),
    }

    # routes between matched room pairs: original floor vs generated floor
    original_map = full_map({"floors": truth["floors"], "spaces": true_spaces, "openings": truth["openings"]})
    generated_map = full_map(fragment)
    reverse = {t: g for g, t in matched.items()}
    candidates = [
        pair
        for pair in itertools.combinations(sorted(reverse), 2)
        if route_length(original_map, pair[0], pair[1]) is not None
    ]
    picked = random.Random(0).sample(candidates, min(N_ROUTES, len(candidates)))
    routes, errors = [], []
    for a, b in picked:
        original = route_length(original_map, a, b)
        generated = route_length(generated_map, reverse[a], reverse[b])
        error = None if generated is None else round(abs(generated - original) / original, 3)
        routes.append({"pair": [a[-4:], b[-4:]], "original_m": original, "generated_m": generated, "rel_err": error})
        errors.append(error)
    found = [e for e in errors if e is not None]
    result["routes"] = {
        "pairs": routes,
        "no_route": len(errors) - len(found),
        "rel_err_median": round(statistics.median(found), 3) if found else None,
        "rel_err_worst": max(found) if found else None,
    }
    # validation checks a product flow would run
    components = list(nx.connected_components(BuildingMap(generated_map).graph(False)))
    unreachable = [s["id"] for s in gen_spaces if not any(s["id"] in c and "outside" in c for c in components)]
    result["validation"] = {"components": len(components), "rooms_not_connected_to_outside": len(unreachable)}
    return result


def main() -> None:
    results = []
    for file in sorted(OUT.glob("*.json")):
        record = json.loads(file.read_text())
        if "extraction" not in record:
            try:
                record["extraction"] = parse_json(record["raw_text"])
                record.pop("parse_error", None)
                file.write_text(json.dumps(record, indent=1, ensure_ascii=False))
            except ValueError:
                pass
        if "extraction" not in record:
            continue
        for mode in ("true_width", "door"):
            results.append(
                {
                    **measure(record["building_id"], record["floor_index"], mode, record),
                    "run": file.stem,
                    "seconds": record["seconds"],
                    "tokens": [record["input_tokens"], record["output_tokens"]],
                }
            )
    (Path(__file__).parent / "results.json").write_text(json.dumps(results, indent=1))
    json.dump(results, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
