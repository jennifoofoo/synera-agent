import math

import networkx as nx
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge, nearest_points

from building_agent.geometry import space_polygon
from building_agent.registry import Kind
from starter_agent.building_map import ADJACENT_DISTANCE_M, DOOR_PREFIX, OUTSIDE, BuildingMap, MapError

WALL_BUFFER_M = 0.35
MIN_GAIN_M = 1.0
NOT_ROOM_TYPES = {"corridor", "stair", "lift", "outdoor"}
NOT_ROOM_ROOM_TYPES = {"corridor", "stairwell", "lift"}


def shared_wall_midpoint(bm: BuildingMap, first: str, second: str) -> tuple[float, float]:
    """Middle of the wall `first` shares with `second`: the longest stretch of first's outline
    within 0.35 m of second, halfway along it. Falls back to the closest points between the two."""
    first_polygon, second_polygon = space_polygon(bm, first), space_polygon(bm, second)
    if first_polygon.distance(second_polygon) > ADJACENT_DISTANCE_M:
        raise MapError(f"{bm.describe_space(first)} and {bm.describe_space(second)} do not share a wall.")
    overlap = first_polygon.exterior.intersection(second_polygon.buffer(WALL_BUFFER_M))
    lines = [
        line
        for part in getattr(overlap, "geoms", [overlap])
        if isinstance(part, (LineString, MultiLineString))
        for line in getattr(part, "geoms", [part])
    ]
    if lines:
        merged = linemerge(MultiLineString(lines))
        wall = max(getattr(merged, "geoms", [merged]), key=lambda line: line.length)
        middle = wall.interpolate(0.5, normalized=True)
        return (middle.x, middle.y)
    point_a, point_b = nearest_points(first_polygon, second_polygon)
    return ((point_a.x + point_b.x) / 2, (point_a.y + point_b.y) / 2)


def is_room(space: dict) -> bool:
    return space["type"] not in NOT_ROOM_TYPES and space["room_type"] not in NOT_ROOM_ROOM_TYPES


def what_if_door(bm: BuildingMap, first: str, second: str, door_floor_id: str, floor_id: str) -> dict:
    """Rooms on `floor_id` whose walk to the nearest entrance gets more than 1 m shorter
    once a door joins `first` and `second` (on `door_floor_id`) in the middle of their shared wall."""
    if bm.spaces[first]["floor_id"] != door_floor_id or bm.spaces[second]["floor_id"] != door_floor_id:
        raise MapError(f"Both spaces must be on {door_floor_id}.")
    position = shared_wall_midpoint(bm, first, second)
    before_graph = bm.graph(step_free=False)
    after_graph = before_graph.copy()
    door = DOOR_PREFIX + "what-if"
    for space_id in (first, second):
        after_graph.add_edge(space_id, door, weight=math.dist(bm.anchor(space_id), position), via="what-if")
    before = nx.single_source_dijkstra_path_length(before_graph, OUTSIDE, weight="weight")
    after = nx.single_source_dijkstra_path_length(after_graph, OUTSIDE, weight="weight")
    space_ids = sorted(
        space_id
        for space_id, space in bm.spaces.items()
        if space["floor_id"] == floor_id
        and is_room(space)
        and space_id in after
        and before.get(space_id, math.inf) - after[space_id] > MIN_GAIN_M
    )
    return {
        "count": len(space_ids),
        "space_ids": space_ids,
        "door_position": [round(position[0], 3), round(position[1], 3)],
    }


KIND = Kind(
    name="what_if_door",
    fn=what_if_door,
    description=(
        "What-if: add a door between spaces `first` and `second` (both on floor `door_floor_id`) in the middle "
        "of their shared wall. Counts rooms on another floor `floor_id` whose walk out of the building "
        "(route distance to the nearest entrance, stairs allowed) gets shorter by more than 1 m. "
        "Corridors, stairwells, lifts and balconies are not rooms. Returns count, space_ids, door_position."
    ),
)
