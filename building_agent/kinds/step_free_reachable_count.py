import networkx as nx

from building_agent.registry import Kind
from starter_agent.building_map import BuildingMap, MapError


def step_free_reachable_count(bm: BuildingMap, closed: str, start: str, floor_id: str) -> dict:
    """Rooms on `floor_id` a wheelchair user can still reach from `start` while `closed` (a lift) is out of service.

    Step-free graph, no stairs or steps. Only spaces of type "room" count, not corridors, stairwells or lifts."""
    element = bm.find_element(closed)
    if floor_id not in bm.floors:
        raise MapError(f"Unknown floor {floor_id}.")
    was_closed = element in bm.closed
    bm.closed.add(element)
    try:
        graph = bm.graph(step_free=True)
        if start not in graph:
            raise MapError(f"{bm.describe_space(start)} cannot be entered step-free.")
        reachable = nx.node_connected_component(graph, start)
    finally:
        if not was_closed:
            bm.closed.discard(element)
    rooms = sorted(
        space_id
        for space_id in reachable
        if space_id in bm.spaces
        and bm.spaces[space_id]["floor_id"] == floor_id
        and bm.spaces[space_id]["type"] == "room"
    )
    return {"count": len(rooms), "space_ids": rooms}


KIND = Kind(
    name="step_free_reachable_count",
    fn=step_free_reachable_count,
    description=(
        "How many rooms on floor `floor_id` a wheelchair user can still reach step-free from `start` "
        "(the room the entrance leads into) when the lift or element `closed` is out of service. "
        "Counts only real rooms, not corridors, stairwells or lifts. Returns count and the room ids."
    ),
)
