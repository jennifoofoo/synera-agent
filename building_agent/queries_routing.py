"""Routing-based question kinds (Jennifer). Pure functions over a BuildingMap, tested against train/dev inputs."""

import networkx as nx
from shapely.geometry import Polygon

from starter_agent.building_map import BuildingMap, MapError


def space_area(bm: BuildingMap, space_id: str) -> float:
    return Polygon(bm.spaces[space_id]["polygon"]).area


def largest_space_id(bm: BuildingMap, floor_id: str, room_type: str) -> str:
    candidates = [
        space["id"]
        for space in bm.spaces.values()
        if space["floor_id"] == floor_id and space["room_type"] == room_type
    ]
    if not candidates:
        raise MapError(f"No {room_type} on floor {floor_id}.")
    return max(candidates, key=lambda space_id: space_area(bm, space_id))


def errand(bm: BuildingMap, start: str, asset_type: str, floor_id: str, room_type: str) -> dict:
    """Walk to the nearest room holding `asset_type`, then carry it to the largest `room_type` room on the floor.

    Stairs are allowed (every errand question says so). Nearest means shortest route length from `start`."""
    holders = {asset["space_id"] for asset in bm.assets.values() if asset["type"] == asset_type}
    if not holders:
        raise MapError(f"No {asset_type} in this building.")
    target = largest_space_id(bm, floor_id, room_type)
    graph = bm.graph(step_free=False)
    from_start = nx.single_source_dijkstra_path_length(graph, start, weight="weight")
    reachable = [space_id for space_id in holders if space_id in from_start]
    if not reachable:
        raise MapError(f"No {asset_type} is reachable from {bm.describe_space(start)}.")
    via = min(reachable, key=lambda space_id: from_start[space_id])
    to_target = nx.single_source_dijkstra_path_length(graph, via, weight="weight")
    if target not in to_target:
        raise MapError(f"{bm.describe_space(target)} is not reachable from {bm.describe_space(via)}.")
    return {
        "length_m": round(from_start[via] + to_target[target], 2),
        "via": via,
        "target": target,
    }
