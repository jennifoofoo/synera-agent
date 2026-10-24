from collections.abc import Callable

import networkx as nx

from building_agent.registry import Kind
from starter_agent.building_map import DOOR_PREFIX, BuildingMap

ROOM_TYPE = "room"


def _is_room(space: dict) -> bool:
    return space["type"] == ROOM_TYPE


def wide_delivery_count_with(
    bm: BuildingMap,
    start: str,
    floor_id: str,
    min_width: float,
    *,
    strict: bool = False,
    counted: Callable[[dict], bool] = _is_room,
) -> dict:
    """wide_delivery_count with alternative readings (scripts/rule_sensitivity.py).

    `strict` demands openings wider than min_width, `counted` decides which spaces on the floor are counted.
    The registered kind is this with the defaults. The tool signature of the registered function is exposed to
    the LLM, so the readings do not live on it."""
    graph = bm.graph(step_free=True)
    narrow = [
        DOOR_PREFIX + opening["id"]
        for opening in bm.openings.values()
        if (opening["width_m"] <= min_width + 1e-9 if strict else opening["width_m"] < min_width - 1e-9)
    ]
    graph.remove_nodes_from(narrow)
    reachable = nx.node_connected_component(graph, start)
    space_ids = sorted(
        space_id
        for space_id in reachable
        if space_id in bm.spaces and bm.spaces[space_id]["floor_id"] == floor_id and counted(bm.spaces[space_id])
    )
    return {"count": len(space_ids), "space_ids": space_ids}


def wide_delivery_count(bm: BuildingMap, start: str, floor_id: str, min_width: float) -> dict:
    """Rooms on `floor_id` reachable from `start` step-free (no stairs, lifts fine) through openings >= min_width."""
    return wide_delivery_count_with(bm, start, floor_id, min_width)


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
