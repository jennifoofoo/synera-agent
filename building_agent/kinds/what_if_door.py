import math
from collections.abc import Callable

from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge, nearest_points

from building_agent.entrance_distance import distances_to_exit
from building_agent.geometry import space_polygon
from building_agent.impact import copy_map
from building_agent.registry import Kind
from starter_agent.building_map import ADJACENT_DISTANCE_M, BuildingMap, MapError

WALL_BUFFER_M = 0.35
MIN_GAIN_M = 1.0
NOT_ROOM_TYPES = {"corridor", "stair", "lift", "outdoor"}
NOT_ROOM_ROOM_TYPES = {"corridor", "stairwell", "lift"}


def shared_wall_midpoint(bm: BuildingMap, first: str, second: str, mode: str = "longest") -> tuple[float, float]:
    """Middle of the wall `first` shares with `second`: the longest stretch of first's outline
    within 0.35 m of second, halfway along it. Falls back to the closest points between the two.

    Other `mode`s are for scripts/rule_sensitivity.py: "combined" is halfway along all shared stretches laid end
    to end (in the order they appear on first's outline), "centroid" the centroid of all of them."""
    first_polygon, second_polygon = space_polygon(bm, first), space_polygon(bm, second)
    if first_polygon.distance(second_polygon) > ADJACENT_DISTANCE_M:
        raise MapError(f"{bm.describe_space(first)} and {bm.describe_space(second)} do not share a wall.")
    overlap = first_polygon.exterior.intersection(second_polygon.buffer(WALL_BUFFER_M))
    lines = [
        line
        for part in getattr(overlap, "geoms", [overlap])
        if isinstance(part, (LineString, MultiLineString))
        for line in getattr(part, "geoms", [part])
        if not line.is_empty
    ]
    if lines:
        merged = linemerge(MultiLineString(lines))
        parts = list(getattr(merged, "geoms", [merged]))
        if mode == "centroid":
            centre = MultiLineString(parts).centroid
            return (centre.x, centre.y)
        if mode == "combined":
            ring = first_polygon.exterior
            parts.sort(key=lambda line: ring.project(line.interpolate(0.5, normalized=True)))
            half = sum(line.length for line in parts) / 2
            for line in parts:
                if half <= line.length:
                    middle = line.interpolate(half)
                    return (middle.x, middle.y)
                half -= line.length
        wall = max(parts, key=lambda line: line.length)
        middle = wall.interpolate(0.5, normalized=True)
        return (middle.x, middle.y)
    point_a, point_b = nearest_points(first_polygon, second_polygon)
    return ((point_a.x + point_b.x) / 2, (point_a.y + point_b.y) / 2)


def is_room(space: dict) -> bool:
    return space["type"] not in NOT_ROOM_TYPES and space["room_type"] not in NOT_ROOM_ROOM_TYPES


def _gains(gain: float, inclusive: bool) -> bool:
    return gain >= MIN_GAIN_M - 1e-9 if inclusive else gain > MIN_GAIN_M


def what_if_door_with(
    bm: BuildingMap,
    first: str,
    second: str,
    door_floor_id: str,
    floor_id: str,
    *,
    door_mode: str = "longest",
    inclusive: bool = False,
    counted: Callable[[dict], bool] = is_room,
) -> dict:
    """what_if_door with alternative readings (scripts/rule_sensitivity.py).

    `door_mode` see shared_wall_midpoint, `inclusive` counts a gain of exactly 1 m, `counted` decides which
    spaces on the floor are counted. The registered kind is this with the defaults. The tool signature of the
    registered function is exposed to the LLM, so the readings do not live on it."""
    if bm.spaces[first]["floor_id"] != door_floor_id or bm.spaces[second]["floor_id"] != door_floor_id:
        raise MapError(f"Both spaces must be on {door_floor_id}.")
    position = shared_wall_midpoint(bm, first, second, door_mode)
    after_map = copy_map(bm)
    after_map.add_door(first, second, position=position)
    before = distances_to_exit(bm, bm.graph(step_free=False))
    after = distances_to_exit(after_map, after_map.graph(step_free=False))
    space_ids = sorted(
        space_id
        for space_id, space in bm.spaces.items()
        if space["floor_id"] == floor_id
        and counted(space)
        and space_id in after
        and _gains(before.get(space_id, math.inf) - after[space_id], inclusive)
    )
    return {
        "count": len(space_ids),
        "space_ids": space_ids,
        "door_position": [round(position[0], 3), round(position[1], 3)],
    }


def what_if_door(bm: BuildingMap, first: str, second: str, door_floor_id: str, floor_id: str) -> dict:
    """Rooms on `floor_id` whose walk to the nearest entrance gets more than 1 m shorter
    once a door joins `first` and `second` (on `door_floor_id`) in the middle of their shared wall."""
    return what_if_door_with(bm, first, second, door_floor_id, floor_id)


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
