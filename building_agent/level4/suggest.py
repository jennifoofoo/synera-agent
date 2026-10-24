"""Level 4 door suggestions: propose doors for rooms that have no way out. Deterministic, no API, never edits input.

The person confirms every suggestion; `apply_suggestions` returns a new building with the doors added."""

import copy
import dataclasses
import itertools
import math
from collections import defaultdict
from dataclasses import dataclass

from shapely.geometry import LineString, Polygon
from shapely.ops import linemerge, nearest_points
from shapely.strtree import STRtree

from building_agent.level4.validate import room_label
from starter_agent.building_map import ADJACENT_DISTANCE_M, OUTSIDE

MIN_WALL_M = 0.9
NESTED_SHARE = 0.8
WALL_TOLERANCE_M = 0.25
WALL_TRIM_M = 0.4
SUGGESTED_DOOR_WIDTH_M = 0.9
HUB_TYPES = {"corridor", "hall"}
HUB_ROOM_TYPES = {"corridor", "lobby"}
VERTICAL_TYPES = {"stair", "lift"}
VERTICAL_ROOM_TYPES = {"stairwell", "lift"}
WET_ROOM_TYPES = {"bathroom", "toilet"}
LIVING_ROOM_TYPES = {"bedroom", "kitchen", "living_room"}

# Score weights, tuned on the plateau found in scripts/eval_suggest.py (see docs/eval-log.md, "Door suggestions").
# DEGREE: a reachable room with many doors is probably a corridor, even when its type says nothing.
HUB_BONUS = 3.0
WALL_WEIGHT = 0.2
WALL_CAP_M = 6.0
VERTICAL_PENALTY = 3.0
WET_PENALTY = 1.0
OUTDOOR_PENALTY = 1.5
DEGREE_WEIGHT = 2.0
DEGREE_CAP = 6


@dataclass(frozen=True)
class Suggestion:
    first: str
    second: str
    first_ref: str
    second_ref: str
    floor_id: str
    position: tuple[float, float]
    wall_length_m: float
    score: float
    reason: str


@dataclass(frozen=True)
class _Pair:
    first: str
    second: str
    position: tuple[float, float]
    wall: float
    score: float
    reason: str


def _polygon(space: dict) -> Polygon | None:
    try:
        coords = [(float(x), float(y)) for x, y in space["polygon"]]
    except (KeyError, TypeError, ValueError):
        return None
    if len(coords) < 3 or not all(math.isfinite(v) for point in coords for v in point):
        return None
    polygon = Polygon(coords)
    return polygon if polygon.is_valid and polygon.area > 0 else None


def _role(space: dict) -> str:
    kind, room_type = space.get("type"), space.get("room_type")
    if kind in VERTICAL_TYPES or room_type in VERTICAL_ROOM_TYPES:
        return "vertical"
    if kind in HUB_TYPES or room_type in HUB_ROOM_TYPES:
        return "hub"
    if kind == "outdoor" or room_type == "balcony":
        return "outdoor"
    if room_type in WET_ROOM_TYPES:
        return "wet"
    if room_type in LIVING_ROOM_TYPES:
        return "living"
    return "room"


def _score(first: dict, second: dict, wall: float) -> tuple[float, str]:
    roles = {_role(first), _role(second)}
    score = WALL_WEIGHT * min(wall, WALL_CAP_M)
    parts = [f"{wall:.1f} m of shared wall"]
    if "hub" in roles:
        score += HUB_BONUS
        parts.append("one side is a corridor or hall")
    if "vertical" in roles:
        score -= VERTICAL_PENALTY
        parts.append("a stair or lift is involved")
    if "outdoor" in roles:
        score -= OUTDOOR_PENALTY
        parts.append("one side is outdoors")
    if "wet" in roles and roles & {"living"}:
        score -= WET_PENALTY
        parts.append("a bathroom next to a living room")
    return score, ", ".join(parts)


def _door_spot(first: Polygon, second: Polygon, stretch: LineString) -> tuple[float, float]:
    middle = stretch.interpolate(0.5, normalized=True)
    other = nearest_points(second.boundary, middle)[0]
    return (round((middle.x + other.x) / 2, 3), round((middle.y + other.y) / 2, 3))


def _shared_wall(first: Polygon, second: Polygon) -> list[LineString]:
    """Stretches of first's outline that run along second, within reach of a skewed wall (WALL_TRIM_M is taken off later for the corner overshoot)."""
    near = first.boundary.intersection(second.boundary.buffer(first.distance(second) + WALL_TOLERANCE_M))
    parts = [g for g in getattr(near, "geoms", [near]) if isinstance(g, LineString) and g.length > 1e-6]
    merged = linemerge(parts) if len(parts) > 1 else (parts[0] if parts else None)
    return [] if merged is None else list(getattr(merged, "geoms", [merged]))


def _nested_wall(first: Polygon, second: Polygon) -> LineString | None:
    """The longest outline edge of a room that lies (mostly) inside another one, as in some OSM plans."""
    small, large = (first, second) if first.area <= second.area else (second, first)
    if small.intersection(large).area < NESTED_SHARE * small.area:
        return None
    coords = list(small.exterior.coords)
    edges = [LineString(pair) for pair in itertools.pairwise(coords)]
    return max(edges, key=lambda edge: edge.length, default=None)


def _candidates(spaces: list[dict]) -> dict[frozenset, _Pair]:
    """Every pair of rooms on one floor that share a wall stretch of at least MIN_WALL_M, scored."""
    by_floor: dict[str, list[tuple[dict, Polygon]]] = defaultdict(list)
    for space in spaces:
        polygon = _polygon(space)
        if polygon is not None:
            by_floor[space["floor_id"]].append((space, polygon))
    found: dict[frozenset, _Pair] = {}
    for floor_id in sorted(by_floor):
        items = sorted(by_floor[floor_id], key=lambda item: item[0]["id"])
        tree = STRtree([polygon for _, polygon in items])
        for index, (first, first_shape) in enumerate(items):
            for other in sorted(tree.query(first_shape.buffer(ADJACENT_DISTANCE_M))):
                if other <= index:
                    continue
                second, second_shape = items[other]
                if first_shape.distance(second_shape) > ADJACENT_DISTANCE_M:
                    continue
                stretches = _shared_wall(first_shape, second_shape)
                longest = max(stretches, key=lambda line: line.length, default=None)
                length = longest.length - WALL_TRIM_M if longest is not None else 0.0
                if length < MIN_WALL_M:
                    longest = _nested_wall(first_shape, second_shape)
                    length = longest.length if longest is not None else 0.0
                if longest is None or length < MIN_WALL_M:
                    continue
                score, reason = _score(first, second, length)
                position = _door_spot(first_shape, second_shape, longest)
                found[frozenset((first["id"], second["id"]))] = _Pair(
                    first["id"], second["id"], position, round(length, 2), score, reason
                )
    return found


class _Groups:
    """Union-find over spaces, `outside` and everything the openings and connectors join."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        while self.parent.setdefault(item, item) != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def join(self, first: str, second: str) -> None:
        self.parent[self.find(second)] = self.find(first)


def _groups(building: dict, ids: set[str], extra: list[tuple[str, str]]) -> _Groups:
    groups = _Groups()
    for space_id in sorted(ids):
        groups.find(space_id)
    for opening in building.get("openings") or []:
        ends = [end for end in opening.get("space_ids") or [] if end == OUTSIDE or end in ids]
        if len(ends) == 2:
            groups.join(*ends)
    for connector in building.get("vertical_connectors") or []:
        stops = [space_id for space_id in connector.get("space_ids") or [] if space_id in ids]
        for space_id in stops[1:]:
            groups.join(stops[0], space_id)
    for first, second in extra:
        groups.join(first, second)
    return groups


def _has_door(building: dict, first: str, second: str) -> bool:
    return any(set(o.get("space_ids") or []) == {first, second} for o in building.get("openings") or [])


def suggest_doors(building: dict, max_suggestions: int = 20) -> list[Suggestion]:
    """Doors that would give every unreachable room a way out, best first, at most `max_suggestions`."""
    try:
        spaces = [space for space in building["spaces"] if _polygon(space) is not None]
        ids = {space["id"] for space in spaces}
        by_id = {space["id"]: space for space in spaces}
        candidates = _candidates(spaces)
        has_entrance = any(OUTSIDE in (o.get("space_ids") or []) for o in building.get("openings") or [])
        chosen: list[_Pair] = []
        while len(chosen) < max_suggestions:
            groups = _groups(building, ids, [(pair.first, pair.second) for pair in chosen])
            members: dict[str, list[str]] = defaultdict(list)
            for space_id in sorted(ids):
                members[groups.find(space_id)].append(space_id)
            if has_entrance:
                reference = groups.find(OUTSIDE)
            else:
                reference = max(members, key=lambda root: (len(members[root]), root), default=None)
            isolated = [root for root in sorted(members, key=lambda r: members[r][0]) if root != reference]
            degree: dict[str, int] = defaultdict(int)
            for opening in building.get("openings") or []:
                for end in opening.get("space_ids") or []:
                    degree[end] += 1
            picks = []
            for root in isolated:
                best = None
                for pair in candidates.values():
                    roots = {groups.find(pair.first), groups.find(pair.second)}
                    if roots != {root, reference} or _has_door(building, pair.first, pair.second):
                        continue
                    reached = pair.first if groups.find(pair.first) == reference else pair.second
                    total = pair.score + DEGREE_WEIGHT * min(degree[reached], DEGREE_CAP)
                    key = (-total, -pair.wall, pair.first, pair.second)
                    if best is None or key < best[0]:
                        best = (key, pair, total)
                if best:
                    picks.append(dataclasses.replace(best[1], score=best[2]))
            if not picks:
                break
            picks.sort(key=lambda pair: (-pair.score, -pair.wall, pair.first, pair.second))
            chosen.extend(picks[: max_suggestions - len(chosen)])
    except (KeyError, TypeError, ValueError, AttributeError):
        return []
    result = []
    for pair in chosen:
        first, second = by_id[pair.first], by_id[pair.second]
        result.append(
            Suggestion(
                pair.first,
                pair.second,
                room_label(first),
                room_label(second),
                first["floor_id"],
                pair.position,
                pair.wall,
                round(pair.score, 3),
                pair.reason,
            )
        )
    return result


def apply_suggestions(building: dict, suggestions: list[Suggestion]) -> dict:
    """A copy of the building with one door per suggestion added (the input is not touched)."""
    result = copy.deepcopy(building)
    openings = result.setdefault("openings", [])
    taken = {opening.get("id") for opening in openings}
    for suggestion in suggestions:
        if _has_door(result, suggestion.first, suggestion.second):
            continue
        base, number = f"{suggestion.floor_id}-O-sug", len(openings) + 1
        while f"{base}{number}" in taken:
            number += 1
        opening_id = f"{base}{number}"
        taken.add(opening_id)
        openings.append(
            {
                "id": opening_id,
                "floor_id": suggestion.floor_id,
                "space_ids": [suggestion.first, suggestion.second],
                "kind": "door",
                "position": [suggestion.position[0], suggestion.position[1]],
                "width_m": SUGGESTED_DOOR_WIDTH_M,
                "step_free": True,
                "synthetic": True,
            }
        )
    return result


def describe_suggestions(suggestions: list[Suggestion], max_items: int = 8) -> str:
    """Plain-words proposal for the card, empty when there is nothing to propose."""
    if not suggestions:
        return ""
    shown = ", ".join(f"{s.first_ref} to {s.second_ref}" for s in suggestions[:max_items])
    more = f", and {len(suggestions) - max_items} more" if len(suggestions) > max_items else ""
    noun = "door" if len(suggestions) == 1 else "doors"
    return f"I suggest these {len(suggestions)} {noun}: {shown}{more}. Say yes to add them."
