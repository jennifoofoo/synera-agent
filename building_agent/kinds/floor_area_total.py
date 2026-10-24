from building_agent.geometry import space_area
from building_agent.registry import Kind
from starter_agent.building_map import BuildingMap, MapError


def floor_area_total(bm: BuildingMap, floor_id: str, room_type: str) -> dict:
    """Sum of polygon areas (m2) of all spaces of `room_type` on floor `floor_id`."""
    space_ids = [
        space["id"] for space in bm.spaces.values() if space["floor_id"] == floor_id and space["room_type"] == room_type
    ]
    if not space_ids:
        raise MapError(f"No {room_type} on floor {floor_id}.")
    return {
        "total_m2": round(sum(space_area(bm, space_id) for space_id in space_ids), 2),
        "count": len(space_ids),
        "space_ids": space_ids,
    }


KIND = Kind(
    name="floor_area_total",
    fn=floor_area_total,
    description=(
        "Total floor area in m2 of all rooms of one `room_type` on floor `floor_id`, added together. "
        "Returns total_m2, the number of rooms (count) and their ids (space_ids)."
    ),
)
