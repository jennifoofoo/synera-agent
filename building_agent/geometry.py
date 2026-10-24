"""Shared geometry helpers on building.json spaces. Keep it small: add a helper only when two kinds need it.

Polygons are used exactly as given (no repair yet). If invalid OSM polygons turn out to break a kind,
fix it here once for everyone."""

from shapely.geometry import Polygon

from starter_agent.building_map import BuildingMap, MapError


def space_polygon(bm: BuildingMap, space_id: str) -> Polygon:
    return Polygon(bm.spaces[space_id]["polygon"])


def space_area(bm: BuildingMap, space_id: str) -> float:
    return space_polygon(bm, space_id).area


def largest_space_id(bm: BuildingMap, floor_id: str, room_type: str) -> str:
    """Largest space of one room_type on one floor, by polygon area."""
    candidates = [
        space["id"]
        for space in bm.spaces.values()
        if space["floor_id"] == floor_id and space["room_type"] == room_type
    ]
    if not candidates:
        raise MapError(f"No {room_type} on floor {floor_id}.")
    return max(candidates, key=lambda space_id: space_area(bm, space_id))
