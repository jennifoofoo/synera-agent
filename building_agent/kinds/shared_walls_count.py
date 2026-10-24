from building_agent.geometry import space_polygon
from building_agent.registry import Kind
from starter_agent.building_map import BuildingMap

_EXCLUDED_TYPES = {"corridor", "stair", "lift", "outdoor"}
_EXCLUDED_ROOM_TYPES = {"corridor", "stairwell", "lift"}
_WALL_THICKNESS_M = 0.35  # gap between neighbouring room outlines (wall thickness) that still counts as shared
_MIN_SHARED_M = 1.0


def shared_walls_count_with(
    bm: BuildingMap,
    start: str,
    *,
    wall_thickness_m: float = _WALL_THICKNESS_M,
    min_shared_m: float = _MIN_SHARED_M,
    also_excluded_types: frozenset[str] = frozenset(),
) -> dict:
    """shared_walls_count with alternative readings of the rules (scripts/rule_sensitivity.py).

    `also_excluded_types` drops spaces whose type (e.g. "hall") is listed on top of the README exclusions.
    The registered kind `shared_walls_count` is this with the defaults. The tool signature of the registered
    function is exposed to the LLM, so the readings do not live on it."""
    s = bm.spaces[start]
    outline = space_polygon(bm, start).exterior
    space_ids = []
    for oid, o in bm.spaces.items():
        if oid == start or o["floor_id"] != s["floor_id"]:
            continue
        if o["type"] in _EXCLUDED_TYPES or o["type"] in also_excluded_types:
            continue
        if o.get("room_type") in _EXCLUDED_ROOM_TYPES:
            continue
        if outline.intersection(space_polygon(bm, oid).exterior.buffer(wall_thickness_m)).length >= min_shared_m:
            space_ids.append(oid)
    return {"count": len(space_ids), "space_ids": sorted(space_ids)}


def shared_walls_count(bm: BuildingMap, start: str) -> dict:
    """Rooms on the same floor sharing a wall (>= 1 m of common boundary) with room `start`."""
    return shared_walls_count_with(bm, start)


KIND = Kind(
    name="shared_walls_count",
    fn=shared_walls_count,
    description=(
        "Count the other rooms on the same floor that share a wall with room `start` (space id): common wall "
        "of at least 1 m, door or not; corridors, stairwells, lifts and outdoor spaces are not counted. "
        "Returns count and space_ids."
    ),
)
