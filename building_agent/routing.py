"""Route model for people: the kit's door-to-door model (starter_agent.building_map), with the graph cached.

There is exactly one model in this repo. `BuildingMap.graph` builds it (README section 3): door-to-door walking
15 cm off the walls, doors landing 30 cm inside, stairs 2 m per metre climbed, a lift ride 15 m once plus 1 m per
metre climbed, every pair of lift stops joined, and no way round the outside. This module only adds what the kit
router lacks for an agent that answers many questions on one map:

- the graph is built once per set of closures and doors (not on every call) and kept per map;
- a failed route clears `bm.last_route`, so a stale route is never reported as the answer to an unreachable pair;
- tours are legs in order, each leg routed on its own like the labelled tours (their length is the sum of the legs).

Lengths, space paths and directions come from the kit's own functions on that graph, so `routing.route` and
`BuildingMap.route` agree to the centimetre (tests/test_routing.py checks this on random pairs)."""

import itertools
import math
import weakref
from pathlib import Path

import networkx as nx
from shapely.geometry import Point
from shapely.ops import nearest_points

from starter_agent.building_map import (
    COVER_TOLERANCE_M,
    DOOR_PREFIX,
    LENGTH_DECIMALS,
    WALL_CLEARANCE_M,
    BuildingMap,
    MapError,
    RouteResult,
    door_landing,
    outline,
    walking_lengths,
)

MAX_CACHED_GRAPHS = 6
POINT_INSIDE_M = 1e-6  # a point this close to the polygon counts as inside
MAX_SNAP_M = 1.0  # a point further outside its room than this is rejected instead of moved in

# building path -> walking lengths of the unchanged building, computed once per process (see load_map)
_WALKS: dict[Path, dict] = {}

# bm -> {signature: RoutingGraph}. Kept outside the map so deepcopy(bm) stays cheap.
_CACHE: "weakref.WeakKeyDictionary[BuildingMap, dict]" = weakref.WeakKeyDictionary()


def load_map(path: Path) -> BuildingMap:
    """A fresh map of the building at `path` that reuses its walking lengths from earlier loads in this process.

    The walking lengths are the one heavy computation (about 2 s for the largest building, 1600 spaces); every
    later map of the same building, also after edits like a new door, starts with them already filled in."""
    return BuildingMap.load_cached(Path(path), _WALKS)


def graph_signature(bm: BuildingMap, step_free: bool) -> tuple:
    """Changes whenever closures or doors change (same idea as guide_tools.building_signature)."""
    openings = hash(
        tuple(
            (o["id"], o["step_free"], o.get("width_m"), tuple(o["position"]), tuple(o["space_ids"]))
            for o in bm.openings.values()
        )
    )
    return (tuple(sorted(bm.closed)), len(bm.openings), openings, len(bm.connectors), len(bm.spaces), step_free)


class RoutingGraph:
    def __init__(self, graph: nx.MultiGraph, members: dict[str, list[str]]) -> None:
        self.graph = graph
        self.members = members  # space id -> its nodes (the space itself and the doors that touch it)


def build_graph(bm: BuildingMap, step_free: bool) -> RoutingGraph:
    graph = bm.graph(step_free)
    members: dict[str, list[str]] = {space_id: [space_id] for space_id in graph if space_id in bm.spaces}
    for node in graph:
        if node.startswith(DOOR_PREFIX):
            for space_id in bm.openings[node.removeprefix(DOOR_PREFIX)]["space_ids"]:
                if space_id in members:
                    members[space_id].append(node)
    return RoutingGraph(graph, members)


def routing_graph(bm: BuildingMap, step_free: bool) -> RoutingGraph:
    """Graph for the current closures and doors, cached per map and rebuilt when those change."""
    cache = _CACHE.setdefault(bm, {})
    key = graph_signature(bm, step_free)
    if key not in cache:
        if len(cache) >= MAX_CACHED_GRAPHS:
            cache.clear()
        cache[key] = build_graph(bm, step_free)
    return cache[key]


def shortest_leg(bm: BuildingMap, rg: RoutingGraph, start: str, end: str) -> tuple[float, list[str]] | None:
    """(length, node path) between two spaces, or None if there is no route (closed, cut off or only via outside)."""
    try:
        return nx.single_source_dijkstra(rg.graph, start, end, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def distances_from(bm: BuildingMap, rg: RoutingGraph, start: str, targets: list[str]) -> dict[str, float]:
    """Route length from one space to each reachable target space in one pass (same rule as shortest_leg)."""
    if start not in rg.graph:
        return {}
    reached = nx.single_source_dijkstra_path_length(rg.graph, start, weight="weight")
    return {target: reached[target] for target in targets if target in reached}


def check_point(bm: BuildingMap, space_id: str, point, floor_id: str | None = None) -> tuple[float, float]:
    """A point in model metres inside the polygon of `space_id`: as given when inside, moved to the nearest point
    inside when it is at most MAX_SNAP_M outside, else a MapError that says so."""
    try:
        x, y = (float(value) for value in point)
    except (TypeError, ValueError) as error:
        raise MapError("The start or end point must be two numbers [x, y] in metres.") from error
    if not (math.isfinite(x) and math.isfinite(y)):
        raise MapError("The start or end point must be two finite numbers in metres.")
    space = bm.spaces[space_id]
    if floor_id is not None and floor_id != space["floor_id"]:
        raise MapError(f"The point is given for another floor than {bm.describe_space(space_id)}.")
    polygon = outline(space["polygon"])
    here = Point(x, y)
    if polygon.buffer(POINT_INSIDE_M).covers(here):
        return x, y
    snapped = nearest_points(polygon, here)[0]
    outside = here.distance(snapped)
    if outside > MAX_SNAP_M:
        raise MapError(f"The point ({x:.1f}, {y:.1f}) is {outside:.1f} m outside {bm.describe_space(space_id)}.")
    return snapped.x, snapped.y


def room_walks(bm: BuildingMap, rg: RoutingGraph, space_id: str, point: tuple[float, float]) -> dict:
    """Walks inside one room from an exact point, the way BuildingMap.space_walks does it for the anchor: a
    visibility graph 15 cm off the walls, doors landing 30 cm inside. A point inside the wall clearance first
    steps to the nearest walkable spot. Returns {anchor: metres, doors: {door node: metres}}."""
    polygon = outline(bm.spaces[space_id]["polygon"])
    walkable = polygon.buffer(-WALL_CLEARANCE_M)
    if walkable.is_empty or walkable.geom_type != "Polygon":
        walkable = polygon
    entry, step_in = point, 0.0
    if not walkable.buffer(COVER_TOLERANCE_M).covers(Point(point)):
        nearest = nearest_points(walkable, Point(point))[0]
        entry, step_in = (nearest.x, nearest.y), math.dist(point, (nearest.x, nearest.y))
    doors = [node for node in rg.members[space_id] if node.startswith(DOOR_PREFIX)]
    landings = []
    for node in doors:
        door = bm.openings[node.removeprefix(DOOR_PREFIX)]["position"]
        landings.append((door_landing(polygon, (door[0], door[1])), (door[0], door[1])))
    lengths = walking_lengths(polygon, [entry, bm.anchor(space_id), *[landing for landing, _ in landings]])
    return {
        "anchor": lengths[(0, 1)] + step_in,
        "doors": {
            node: lengths[(0, 2 + index)] + step_in + math.dist(landing, door)
            for index, (node, (landing, door)) in enumerate(zip(doors, landings, strict=True))
        },
    }


def rewire_room(bm: BuildingMap, rg: RoutingGraph, graph: nx.MultiGraph, space_id: str, point) -> None:
    """On a COPY of the graph: the room's node stands for the exact point. Its door edges get the walk from the
    point, its stair and lift edges pay the walk from the point to the anchor where those stops sit."""
    walks = room_walks(bm, rg, space_id, point)
    for neighbour in list(graph.neighbors(space_id)):
        for key, edge in list(graph[space_id][neighbour].items()):
            if "via" in edge:
                edge["weight"] = round(edge["weight"] + walks["anchor"], LENGTH_DECIMALS)
            elif neighbour in walks["doors"]:
                graph.remove_edge(space_id, neighbour, key)
    for node, length in walks["doors"].items():
        graph.add_edge(space_id, node, weight=round(length, LENGTH_DECIMALS), space=space_id)


def same_room_walk(bm: BuildingMap, space_id: str, first, second) -> float:
    """In-room walk between two exact points of one room (None stands for the anchor)."""
    ends = [first or bm.anchor(space_id), second or bm.anchor(space_id)]
    if ends[0] == ends[1]:
        return 0.0
    return round(walking_lengths(outline(bm.spaces[space_id]["polygon"]), ends)[(0, 1)], LENGTH_DECIMALS)


def leg_search(
    bm: BuildingMap, rg: RoutingGraph, first: str, last: str, start_point=None, end_point=None
) -> tuple[float, list[str], nx.MultiGraph] | None:
    """One leg as (length, node path, graph the path was found in). Without points this is shortest_leg on the
    cached graph. With a point the search runs on a copy (the cached graph is never changed)."""
    if start_point is None and end_point is None:
        found = shortest_leg(bm, rg, first, last)
        return None if found is None else (found[0], found[1], rg.graph)
    if first not in rg.graph or last not in rg.graph:
        return None
    if first == last:
        return same_room_walk(bm, first, start_point, end_point), [first], rg.graph
    graph = rg.graph.copy()
    if start_point is not None:
        rewire_room(bm, rg, graph, first, start_point)
    if end_point is not None:
        rewire_room(bm, rg, graph, last, end_point)
    try:
        length, nodes = nx.single_source_dijkstra(graph, first, last, weight="weight")
    except nx.NetworkXNoPath:
        return None
    return length, nodes, graph


def stop_points(stops: list[str], start_point, via_points, destination_point) -> list:
    """One exact point (or None: the room's anchor) per stop: start, each via stop, destination."""
    middle = list(via_points or [])
    middle += [None] * (len(stops) - 2 - len(middle))
    return [start_point, *middle[: len(stops) - 2], destination_point]


def leg_portals(
    bm: BuildingMap,
    step_free: bool,
    stops: list[str],
    start_point=None,
    destination_point=None,
    via_points: list | None = None,
) -> list[list[tuple]] | None:
    """For drawing: per leg the doors crossed as ("o", opening id, space) pairs (from and into) and the stair or lift
    rides as ("c", connector id, space) pairs, in walking order. Same graph and search as `route`, including exact
    start, via and destination points (already checked); None if no route."""
    rg = routing_graph(bm, step_free)
    legs: list[list[tuple]] = []
    points = stop_points(stops, start_point, via_points, destination_point)
    for index, (leg_start, leg_end) in enumerate(itertools.pairwise(stops)):
        found = leg_search(bm, rg, leg_start, leg_end, points[index], points[index + 1])
        if found is None:
            return None
        graph = found[2]
        portals: list[tuple] = []
        for previous, current in itertools.pairwise(found[1]):
            edge = bm.cheapest(graph, previous, current)
            if "via" in edge:
                portals += [("c", edge["via"], previous), ("c", edge["via"], current)]
            elif current.startswith(DOOR_PREFIX):
                opening_id = current.removeprefix(DOOR_PREFIX)
                portals += [
                    ("o", opening_id, edge["space"]),
                    ("o", opening_id, bm.other_side(bm.openings[opening_id], edge["space"])),
                ]
        legs.append(portals)
    return legs


def unreachable(bm: BuildingMap, leg_start: str, leg_end: str, step_free: bool) -> MapError:
    reason = "step-free " if step_free else ""
    return MapError(
        f"No {reason}route from {bm.describe_space(leg_start)} to "
        f"{bm.describe_space(leg_end)} with the current closures {sorted(bm.closed)}. "
        "There is no way round the outside of the building."
    )


def route(
    bm: BuildingMap,
    start: str,
    destination: str,
    step_free: bool = False,
    via: list[str] | None = None,
    start_point=None,
    start_floor: str | None = None,
    destination_point=None,
    via_points: list | None = None,
) -> RouteResult:
    """Shortest walk start -> via... -> destination, one leg per pair of stops. Sets bm.last_route.

    via_points (one per via stop, None for the room's anchor) make a leg end and the next one start at that exact
    point, e.g. the devices of an inspection round: each leg is then the same walk as a route from point to point,
    and the length is the sum of those legs.

    start_point / destination_point (model metres) make the in-room leg run from the exact point (to the exact
    point) instead of the room's anchor: same visibility graph, 15 cm wall clearance and door landing as the kit's
    space walks, on a copy of the cached graph. A point slightly outside its room is moved in, a point far outside
    raises MapError. space_path and the direction lines stay room based; last_route_points start (end) at the point.
    Without points the result is the same as before.

    Raises MapError with a 'No route' message if any leg has no route; bm.last_route is then None."""
    stops = [bm.resolve_space(start), *[bm.resolve_space(stop) for stop in via or []], bm.resolve_space(destination)]
    if start_point is not None:
        start_point = check_point(bm, stops[0], start_point, start_floor)
    if destination_point is not None:
        destination_point = check_point(bm, stops[-1], destination_point)
    via_points = [
        None if point is None else check_point(bm, stop, point)
        for stop, point in zip(stops[1:-1], stop_points(stops, None, via_points, None)[1:-1], strict=True)
    ]
    points_at = stop_points(stops, start_point, via_points, destination_point)
    rg = routing_graph(bm, step_free)
    nodes: list[str] = []
    junctions: list[int] = [0]  # index in nodes where each stop is reached
    length = 0.0
    graph = rg.graph  # the graph that holds the exact points, if any: the direction text reads its edge lengths
    for index, (leg_start, leg_end) in enumerate(itertools.pairwise(stops)):
        found = leg_search(bm, rg, leg_start, leg_end, points_at[index], points_at[index + 1])
        if found is None:
            bm.last_route = None
            bm.last_route_points = []
            raise unreachable(bm, leg_start, leg_end, step_free)
        length += found[0]
        if len(found[1]) == 1 and points_at[index] != points_at[index + 1]:
            nodes += found[1] if nodes else found[1] * 2  # two points in one room: each keeps its own vertex
        else:
            nodes += found[1] if not nodes else found[1][1:]
        junctions.append(len(nodes) - 1)
        if found[2] is not rg.graph and graph is rg.graph:
            graph = found[2]
    same_room = len(set(nodes)) == 1
    result = RouteResult(
        start_space_id=stops[0],
        destination_space_id=stops[-1],
        length_m=round(length, 2),
        space_path=bm.spaces_passed(graph, deduplicated(nodes)),
        steps=same_room_steps(bm, nodes[0], length)
        if same_room and length
        else bm.directions(graph, deduplicated(nodes)),
        step_free=step_free,
        closed=sorted(bm.closed),
    )
    bm.last_route = result
    points = [bm.node_point(node) for node in nodes]
    if len(nodes) == 1 and (start_point or destination_point):
        floor_id, anchor = points[0]
        points = [(floor_id, start_point or anchor), (floor_id, destination_point or anchor)]
    else:
        for position, point in zip(junctions, points_at, strict=True):
            if point is not None:
                points[position] = (points[position][0], point)
    bm.last_route_points = points
    return result


def deduplicated(nodes: list[str]) -> list[str]:
    """The node path without a room repeated back to back (two exact points in one room)."""
    return [node for index, node in enumerate(nodes) if index == 0 or node != nodes[index - 1]]


def same_room_steps(bm: BuildingMap, space_id: str, length: float) -> list[str]:
    return [
        f"Start in {bm.describe_space(space_id)}.",
        f"Walk about {length:.0f} m. You have arrived at {bm.describe_space(space_id)}.",
    ]
