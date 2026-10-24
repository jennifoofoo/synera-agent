from building_agent.geometry import largest_space_id, space_area
from building_agent.registry import Kind
from starter_agent.building_map import BuildingMap


def largest_room(bm: BuildingMap, floor_id: str, room_type: str) -> dict:
    """Largest room of `room_type` on floor `floor_id`, by polygon area."""
    space_id = largest_space_id(bm, floor_id, room_type)
    return {
        "space_id": space_id,
        "name": bm.spaces[space_id]["name"],
        "area_m2": round(space_area(bm, space_id), 2),
    }


KIND = Kind(
    name="largest_room",
    fn=largest_room,
    description=(
        "Largest room of type `room_type` (e.g. generic_room, office) on floor `floor_id`, by floor area. "
        "Returns space_id, name and area_m2 (square metres)."
    ),
)
