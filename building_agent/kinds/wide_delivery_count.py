import networkx as nx

from building_agent.registry import Kind
from starter_agent.building_map import DOOR_PREFIX, BuildingMap

ROOM_TYPE = "room"


def wide_delivery_count(bm: BuildingMap, start: str, floor_id: str, min_width: float) -> dict:
    """Rooms on `floor_id` reachable from `start` step-free (no stairs, lifts fine) through openings >= min_width."""
    graph = bm.graph(step_free=True)
    narrow = [
        DOOR_PREFIX + opening["id"]
        for opening in bm.openings.values()
        if opening["width_m"] < min_width - 1e-9
    ]
    graph.remove_nodes_from(narrow)
    reachable = nx.node_connected_component(graph, start)
    space_ids = sorted(
        space_id
        for space_id in reachable
        if space_id in bm.spaces
        and bm.spaces[space_id]["floor_id"] == floor_id
        and bm.spaces[space_id]["type"] == ROOM_TYPE
    )
    return {"count": len(space_ids), "space_ids": space_ids}


KIND = Kind(
    name="wide_delivery_count",
    fn=wide_delivery_count,
    description=(
        "How many rooms on floor `floor_id` a wide item (min_width metres, e.g. a pallet or machine) can be "
        "delivered into, starting from space `start` (the room the entrance leads into). No stairs or steps, "
        "lifts are fine, every door/opening passed must be at least min_width wide. Counts only spaces of type "
        "room (not corridors, halls/lobbies, stairwells, lifts or balconies). Returns count and space_ids."
    ),
)
