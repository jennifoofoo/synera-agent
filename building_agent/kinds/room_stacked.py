from shapely.geometry import Polygon

from building_agent.registry import Kind
from starter_agent.building_map import BuildingMap, MapError

# Sources whose floors share one XY frame. Swiss Dwellings and ResPlan floors are centred per floor,
# so overlap between their floors means nothing.
STACKED_SOURCES = {"osm_indoor", "procedural"}


def _polygon(space: dict) -> Polygon:
    polygon = Polygon(space["polygon"])
    return polygon if polygon.is_valid else polygon.buffer(0)


def room_stacked(bm: BuildingMap, start: str, direction: str) -> dict:
    """Space on the next existing floor up/down whose outline overlaps `start` the most."""
    if direction not in ("above", "below"):
        raise MapError("direction must be 'above' or 'below'.")
    source = bm.data["building"].get("source")
    if source not in STACKED_SOURCES:
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
    if target_level is None:
        raise MapError(f"There is no floor {direction} {bm.describe_space(start)}.")

    outline = _polygon(space)
    overlaps = {
        other["id"]: outline.intersection(_polygon(other)).area
        for other in bm.spaces.values()
        if bm.floors[other["floor_id"]]["level"] == target_level
    }
    best = max(overlaps, key=overlaps.get, default=None)
    if best is None or overlaps[best] <= 0:
        raise MapError(f"No space on the floor {direction} overlaps {bm.describe_space(start)}.")
    return {
        "space_id": best,
        "name": bm.spaces[best]["name"],
        "floor": bm.floor_name(bm.spaces[best]["floor_id"]),
        "overlap_share": round(overlaps[best] / outline.area, 2),
    }


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
