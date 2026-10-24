"""Connectivity-graph score of a built building against the true one, in the style of Blueprint-Bench 2.

The graph has one node per room (type room, hall or corridor) plus the outside, one edge per pair of rooms joined by
a door. Rooms of the built and the true building are matched by polygon overlap (greedy best IoU), so both buildings
must be in the same frame (pass `offset` if the built one is shifted). Stairs, lifts and outdoor areas are no nodes;
a built room that matches one of them best is ignored rather than counted as an extra room.

Parts, with the Blueprint-Bench weights:
  edge Jaccard 50%, degree similarity 20%, density similarity 10%, room count 10%, door count 5%.
The 5% orientation part is left out (matching uses the true frame, no rotation or reflection is searched), so the
composite divides by 0.95 and a perfect build still scores 1.0.

Unmatched built rooms and missing true rooms lower the score: their edges count as wrong or missed, their degree
similarity is 0. Never raises on empty or odd input."""

import math
from dataclasses import dataclass

from shapely.geometry import Polygon

from starter_agent.building_map import OUTSIDE

NODE_TYPES = {"room", "hall", "corridor"}
MATCH_MIN_IOU = 0.3
WEIGHTS = {"jaccard": 0.50, "degree": 0.20, "density": 0.10, "rooms": 0.10, "doors": 0.05}


@dataclass(frozen=True)
class GraphScore:
    jaccard: float
    degree: float
    density: float
    rooms: float
    doors: float
    composite: float  # weighted, orientation left out (see module docstring)
    matched: int  # rooms present in both buildings
    built_rooms: int
    true_rooms: int


def graph_score(built: dict, truth: dict, offset: tuple[float, float] = (0.0, 0.0)) -> GraphScore:
    """Score the room connectivity of `built` against `truth` (both building.json dicts).

    offset: built metres minus true metres, if the built frame is shifted."""
    built_rooms = _rooms(built, offset)
    true_rooms = _rooms(truth, (0.0, 0.0))
    # A built room that overlaps a true stair, lift or outdoor area best is a typing difference, not an extra room:
    # it is matched against all true spaces and then left out of the graph.
    matching = _match(built_rooms, _rooms(truth, (0.0, 0.0), nodes_only=False))  # built id -> true id
    for built_id in [b for b, t in matching.items() if t not in true_rooms]:
        del matching[built_id]
        del built_rooms[built_id]
    built_edges, built_doors = _edges(built, built_rooms)
    true_edges, true_doors = _edges(truth, true_rooms)

    def name(node: str) -> tuple[str, str]:
        if node == OUTSIDE:
            return ("t", OUTSIDE)
        return ("t", matching[node]) if node in matching else ("b", node)

    mapped = {frozenset(name(end) for end in edge) for edge in built_edges}
    expected = {frozenset(("t", end) for end in edge) for edge in true_edges}
    union = mapped | expected
    jaccard = len(mapped & expected) / len(union) if union else 1.0

    built_degree = _degrees(mapped)
    true_degree = _degrees(expected)
    found = set(matching.values())
    sims = [
        _ratio_similarity(built_degree.get(("t", room), 0), true_degree.get(("t", room), 0)) if room in found else 0.0
        for room in true_rooms
    ]
    sims += [0.0 for room in built_rooms if room not in matching]  # extra built rooms
    degree = sum(sims) / len(sims) if sims else 1.0

    density = _ratio_similarity(
        _density(len(built_rooms) + 1, len(mapped)), _density(len(true_rooms) + 1, len(expected))
    )
    rooms = _ratio_similarity(len(built_rooms), len(true_rooms))
    doors = _ratio_similarity(built_doors, true_doors)
    parts = {"jaccard": jaccard, "degree": degree, "density": density, "rooms": rooms, "doors": doors}
    composite = sum(WEIGHTS[key] * value for key, value in parts.items()) / sum(WEIGHTS.values())
    return GraphScore(
        jaccard, degree, density, rooms, doors, composite, len(matching), len(built_rooms), len(true_rooms)
    )


def _rooms(building: dict, offset: tuple[float, float], nodes_only: bool = True) -> dict[str, tuple[int, Polygon]]:
    """Node spaces (all spaces if not nodes_only) as id -> (floor level, polygon in the true frame).
    Unusable outlines are left out."""
    levels = {floor.get("id"): floor.get("level") for floor in building.get("floors", [])}
    found = {}
    for space in building.get("spaces", []):
        if nodes_only and space.get("type") not in NODE_TYPES:
            continue
        try:
            coords = [(float(x) - offset[0], float(y) - offset[1]) for x, y in space["polygon"]]
            polygon = Polygon(coords)
            if len(coords) < 3 or not polygon.is_valid or polygon.area <= 0 or not math.isfinite(polygon.area):
                continue
            found[space["id"]] = (levels.get(space.get("floor_id")), polygon)
        except (KeyError, TypeError, ValueError):
            continue
    return found


def _match(built: dict[str, tuple[int, Polygon]], truth: dict[str, tuple[int, Polygon]]) -> dict[str, str]:
    """Greedy best-IoU matching on the same floor level, threshold MATCH_MIN_IOU."""
    pairs = []
    for built_id, (built_level, shape) in built.items():
        for true_id, (true_level, other) in truth.items():
            if built_level != true_level or not shape.intersects(other):
                continue
            union = shape.union(other).area
            overlap = shape.intersection(other).area / union if union else 0.0
            if overlap >= MATCH_MIN_IOU:
                pairs.append((overlap, built_id, true_id))
    matching: dict[str, str] = {}
    used: set[str] = set()
    for _, built_id, true_id in sorted(pairs, reverse=True):
        if built_id not in matching and true_id not in used:
            matching[built_id] = true_id
            used.add(true_id)
    return matching


def _edges(building: dict, rooms: dict) -> tuple[set[frozenset], int]:
    """Room-to-room (and room-to-outside) connections, and the number of doors that make them."""
    edges: set[frozenset] = set()
    doors = 0
    for opening in building.get("openings", []):
        ends = opening.get("space_ids", [])
        if len(ends) != 2 or ends[0] == ends[1] or any(end != OUTSIDE and end not in rooms for end in ends):
            continue
        edges.add(frozenset(ends))
        doors += 1
    return edges, doors


def _degrees(edges: set[frozenset]) -> dict:
    degree: dict = {}
    for edge in edges:
        for end in edge:
            degree[end] = degree.get(end, 0) + 1
    return degree


def _density(nodes: int, edges: int) -> float:
    return 2 * edges / (nodes * (nodes - 1)) if nodes > 1 else 0.0


def _ratio_similarity(a: float, b: float) -> float:
    """1 when equal, smaller the further apart; 1 if both are zero."""
    largest = max(a, b)
    return 1.0 if largest == 0 else 1.0 - abs(a - b) / largest
