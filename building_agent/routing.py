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
import weakref
from pathlib import Path

import networkx as nx

from starter_agent.building_map import DOOR_PREFIX, BuildingMap, MapError, RouteResult

MAX_CACHED_GRAPHS = 6

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


def leg_portals(bm: BuildingMap, step_free: bool, stops: list[str]) -> list[list[tuple]] | None:
    """For drawing: per leg the doors crossed as ("o", opening id, space) pairs (from and into) and the stair or lift
    rides as ("c", connector id, space) pairs, in walking order. Same graph and search as `route`; None if no route."""
    rg = routing_graph(bm, step_free)
    legs: list[list[tuple]] = []
    for leg_start, leg_end in itertools.pairwise(stops):
        found = shortest_leg(bm, rg, leg_start, leg_end)
        if found is None:
            return None
        portals: list[tuple] = []
        for previous, current in itertools.pairwise(found[1]):
            edge = bm.cheapest(rg.graph, previous, current)
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
    bm: BuildingMap, start: str, destination: str, step_free: bool = False, via: list[str] | None = None
) -> RouteResult:
    """Shortest walk start -> via... -> destination, one leg per pair of stops. Sets bm.last_route.

    Raises MapError with a 'No route' message if any leg has no route; bm.last_route is then None."""
    stops = [bm.resolve_space(start), *[bm.resolve_space(stop) for stop in via or []], bm.resolve_space(destination)]
    rg = routing_graph(bm, step_free)
    nodes: list[str] = []
    length = 0.0
    for leg_start, leg_end in itertools.pairwise(stops):
        found = shortest_leg(bm, rg, leg_start, leg_end)
        if found is None:
            bm.last_route = None
            bm.last_route_points = []
            raise unreachable(bm, leg_start, leg_end, step_free)
        length += found[0]
        nodes += found[1] if not nodes else found[1][1:]
    result = RouteResult(
        start_space_id=stops[0],
        destination_space_id=stops[-1],
        length_m=round(length, 2),
        space_path=bm.spaces_passed(rg.graph, nodes),
        steps=bm.directions(rg.graph, nodes),
        step_free=step_free,
        closed=sorted(bm.closed),
    )
    bm.last_route = result
    bm.last_route_points = [bm.node_point(node) for node in nodes]
    return result
