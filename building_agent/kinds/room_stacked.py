from shapely.geometry import Polygon

from building_agent.registry import Kind
from starter_agent.building_map import BuildingMap, MapError

# Sources whose floors share one XY frame. Swiss Dwellings and ResPlan floors are centred per floor,
# so overlap between their floors means nothing.
STACKED_SOURCES = {"osm_indoor", "procedural"}


def _polygon(space: dict) -> Polygon:
    polygon = Polygon(space["polygon"])
    return polygon if polygon.is_valid else polygon.buffer(0)


def _overlap(outline: Polygon, other: Polygon, metric: str) -> float:
    shared = outline.intersection(other).area
    if metric == "iou":
        union = outline.union(other).area
        return shared / union if union > 0 else 0.0
    return shared


def room_stacked_with(
    bm: BuildingMap,
    start: str,
    direction: str,
    *,
    metric: str = "intersection",
    adjacent_level_only: bool = False,
    excluded_types: frozenset[str] = frozenset(),
) -> dict:
    """room_stacked with alternative readings (scripts/rule_sensitivity.py).

    `metric` "iou" ranks by intersection over union instead of intersection area, `adjacent_level_only` demands
    level +1/-1 instead of the next existing level, `excluded_types` drops candidate spaces by type.
    The registered kind is this with the defaults. The tool signature of the registered function is exposed to
    the LLM, so the readings do not live on it."""
    if direction not in ("above", "below"):
        raise MapError("direction must be 'above' or 'below'.")
    source = bm.data["building"].get("source")
    # a building built from plans has no source of its own; its floors share a frame when the build lined them up
    # by their stairs and lifts (level4/align.py sets source_ref.floors_aligned)
    lined_up = (bm.data["building"].get("source_ref") or {}).get("floors_aligned") is True
    if source not in STACKED_SOURCES and not lined_up:
        raise MapError(f"Floors of this building ({source}) do not share one XY frame; stacking is undefined.")
    start = bm.resolve_space(start)
    space = bm.spaces[start]
    level = bm.floors[space["floor_id"]]["level"]
    levels = [floor["level"] for floor in bm.floors.values()]
    if direction == "above":
        target_levels = [other for other in levels if other > level]
        target_level = min(target_levels, default=None)
    else:
        target_levels = [other for other in levels if other < level]
        target_level = max(target_levels, default=None)
    if adjacent_level_only and target_level is not None and abs(target_level - level) != 1:
        target_level = None
    if target_level is None:
        raise MapError(f"There is no floor {direction} {bm.describe_space(start)}.")

    outline = _polygon(space)
    overlaps = {
        other["id"]: _overlap(outline, _polygon(other), metric)
        for other in bm.spaces.values()
        if bm.floors[other["floor_id"]]["level"] == target_level and other["type"] not in excluded_types
    }
    best = max(overlaps, key=overlaps.get, default=None)
    if best is None or overlaps[best] <= 0:
        raise MapError(f"No space on the floor {direction} overlaps {bm.describe_space(start)}.")
    return {
        "space_id": best,
        "name": bm.spaces[best]["name"],
        "floor": bm.floor_name(bm.spaces[best]["floor_id"]),
        "overlap_share": round(outline.intersection(_polygon(bm.spaces[best])).area / outline.area, 2),
    }


def room_stacked(bm: BuildingMap, start: str, direction: str) -> dict:
    """Space on the next existing floor up/down whose outline overlaps `start` the most."""
    return room_stacked_with(bm, start, direction)


KIND = Kind(
    name="room_stacked",
    fn=room_stacked,
    description=(
        "Space directly above or below a room: on the next existing floor up (direction='above') or down "
        "(direction='below'), the space whose outline overlaps the start room's outline the most. "
        "`start` is a space id (or exact room name/ref). Returns space_id, name, floor and overlap_share (fraction of the start room covered). "
        "Only valid for OSM and procedural buildings; raises an error for Swiss Dwellings/ResPlan."
    ),
)
