"""Helpers for the Level 4 tests: turn a real dev floor into an artificial Extraction and measure a conversion
against the original. No API involved."""

import json
import math
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
from shapely.geometry import Polygon

from building_agent.level4.schema import ExtractedDoor, ExtractedRoom, Extraction, Scale
from starter_agent.building_map import OUTSIDE, BuildingMap

DATA_DEV = Path("data/dev")
MARGIN_PX = 20
MATCH_MIN_IOU = 0.3

# (building id, floor level): clean procedural, ResPlan, Swiss and OSM floors
SAMPLE_FLOORS = [
    ("proc-campus-dev-000", 0),
    ("proc-campus-dev-001", 1),
    ("proc-factory-dev-003", 0),
    ("proc-factory-dev-004", 1),
    ("resplan-439", 0),
    ("resplan-15179", 0),
    ("swiss-31", 1),
    ("swiss-2074", 0),
    ("osm-way27326387", 0),
    ("osm-way22744230", 0),
]


def load_building(building_id: str) -> dict:
    return json.loads((DATA_DEV / building_id / "building.json").read_text(encoding="utf-8"))


@dataclass
class FloorCase:
    """One real floor, its artificial extraction and how to map the converted frame back."""

    building_id: str
    level: int
    extraction: Extraction
    scale: Scale
    offset: tuple[float, float]  # converted metres minus original metres
    truth: dict  # building.json restricted to this floor
    dropped_doors: int = 0
    notes: dict = field(default_factory=dict)


def floor_case(
    building_id: str, level: int, noise_px: float = 0.0, drop_doors: float = 0.0, seed: int = 0, width_px: int = 1000
) -> FloorCase:
    building = load_building(building_id)
    floor = next(item for item in building["floors"] if item["level"] == level)
    spaces = [space for space in building["spaces"] if space["floor_id"] == floor["id"]]
    openings = [opening for opening in building["openings"] if opening["floor_id"] == floor["id"]]
    xs = [x for space in building["spaces"] for x, _ in space["polygon"]]  # one frame for all floors
    ys = [y for space in building["spaces"] for _, y in space["polygon"]]
    min_x, min_y = min(xs), min(ys)
    px_per_m = width_px / max(max(xs) - min_x, max(ys) - min_y)
    height_px = math.ceil((max(ys) - min_y) * px_per_m) + 2 * MARGIN_PX
    rng = random.Random(seed)

    def to_px(x: float, y: float) -> list[float]:
        return [(x - min_x) * px_per_m + MARGIN_PX, height_px - ((y - min_y) * px_per_m + MARGIN_PX)]

    def jitter(point: list[float]) -> list[float]:
        return [point[0] + rng.gauss(0, noise_px), point[1] + rng.gauss(0, noise_px)] if noise_px else point

    rooms = [
        ExtractedRoom(
            id=f"r{index}",
            polygon_px=[jitter(to_px(x, y)) for x, y in space["polygon"]],
            ref=space.get("ref"),
            name=space.get("name"),
            type=space["type"],
            room_type=space["room_type"],
        )
        for index, space in enumerate(spaces)
    ]
    room_ids = {space["id"]: f"r{index}" for index, space in enumerate(spaces)}
    doors = []
    dropped = 0
    for opening in openings:
        if rng.random() < drop_doors:
            dropped += 1
            continue
        doors.append(
            ExtractedDoor(
                rooms=tuple(OUTSIDE if end == OUTSIDE else room_ids[end] for end in opening["space_ids"]),
                position_px=jitter(to_px(*opening["position"])),
                kind=opening["kind"],
                width_px=opening["width_m"] * px_per_m,
            )
        )
    margin_m = MARGIN_PX / px_per_m
    truth = {
        "building": building["building"],
        "floors": [floor],
        "spaces": spaces,
        "openings": openings,
        "vertical_connectors": [],
        "assets": [],
    }
    return FloorCase(
        building_id,
        level,
        Extraction(width_px=width_px + 2 * MARGIN_PX, height_px=height_px, rooms=rooms, doors=doors),
        Scale(1 / px_per_m, "known_length", "test"),
        (margin_m - min_x, margin_m - min_y),
        truth,
        dropped,
    )


def match_rooms(case: FloorCase, converted: dict) -> dict[str, str]:
    """converted space id -> original space id, greedy by overlap (converted frame shifted back)."""
    dx, dy = case.offset
    original = {space["id"]: Polygon(space["polygon"]) for space in case.truth["spaces"]}
    produced = {space["id"]: Polygon([(x - dx, y - dy) for x, y in space["polygon"]]) for space in converted["spaces"]}
    pairs = []
    for oid, shape in original.items():
        for pid, other in produced.items():
            if not shape.intersects(other):
                continue
            union = shape.union(other).area
            overlap = shape.intersection(other).area / union if union else 0.0
            if overlap >= MATCH_MIN_IOU:
                pairs.append((overlap, oid, pid))
    used_o: set[str] = set()
    matched: dict[str, str] = {}
    for _, oid, pid in sorted(pairs, reverse=True):
        if oid not in used_o and pid not in matched:
            used_o.add(oid)
            matched[pid] = oid
    return matched


def _door_pairs(openings: list[dict], mapping: dict[str, str] | None = None) -> set[frozenset]:
    pairs = set()
    for opening in openings:
        ends = [end if end == OUTSIDE else (mapping or {}).get(end, end) for end in opening["space_ids"]]
        if mapping is None or all(end == OUTSIDE or end in mapping.values() for end in ends):
            pairs.add(frozenset(ends))
    return pairs


def measure(case: FloorCase, converted: dict, n_sources: int = 6, seed: int = 1) -> dict:
    """Room, door, area and route quality of a conversion against the original floor."""
    matched = match_rooms(case, converted)
    originals = {space["id"]: space for space in case.truth["spaces"]}
    produced = {space["id"]: space for space in converted["spaces"]}
    area_errors = []
    for pid, oid in matched.items():
        true_area = Polygon(originals[oid]["polygon"]).area
        if true_area > 0:
            area_errors.append(abs(Polygon(produced[pid]["polygon"]).area - true_area) / true_area)
    true_pairs = _door_pairs(case.truth["openings"])
    found_pairs = _door_pairs(converted["openings"], matched)
    route_errors = _route_errors(case, converted, matched, n_sources, seed)
    return {
        "rooms_true": len(originals),
        "rooms_found": len(produced),
        "rooms_matched": len(matched),
        "area_err_max": max(area_errors, default=0.0),
        "area_err_median": statistics.median(area_errors) if area_errors else 0.0,
        "door_recall": len(true_pairs & found_pairs) / len(true_pairs) if true_pairs else 1.0,
        "routes": len(route_errors),
        "route_err_median": statistics.median(route_errors) if route_errors else 0.0,
        "route_err_max": max(route_errors, default=0.0),
    }


def _route_errors(case: FloorCase, converted: dict, matched: dict[str, str], n_sources: int, seed: int) -> list[float]:
    original_graph = BuildingMap(case.truth).graph(step_free=False)
    produced_graph = BuildingMap(converted).graph(step_free=False)
    back = {oid: pid for pid, oid in matched.items()}
    rng = random.Random(seed)
    sources = rng.sample(sorted(back), min(n_sources, len(back)))
    errors = []
    for source in sources:
        true_lengths = nx.single_source_dijkstra_path_length(original_graph, source, weight="weight")
        found_lengths = nx.single_source_dijkstra_path_length(produced_graph, back[source], weight="weight")
        for target, produced_target in back.items():
            if target == source or true_lengths.get(target, 0) <= 0 or produced_target not in found_lengths:
                continue
            errors.append(abs(found_lengths[produced_target] - true_lengths[target]) / true_lengths[target])
    return errors
