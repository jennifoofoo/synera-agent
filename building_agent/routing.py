"""Route model for people: door to door inside each space, with Synera's vertical costs.

Synera scores a route by the ordered list of spaces and measures it with its own door-to-door rule. The kit's
model (one anchor per space, stairs 12 m, lift 15 + 6 m per floor) picks a worse sequence in about 8 percent of
cases, so routes handed to people use this model instead. Numbers labelled by the kit (errand, what_if_door,
optimal_length_m, step_free_reachable_count) stay on `BuildingMap.route`.

Graph: one node per (opening or connector, space it touches). Inside a space every pair of its nodes is joined by
the straight distance between the door positions (connector stops sit at the space anchor). Entrances and the
outside cost 0. The first and last space cost nothing (door to door): the spike found no real difference to
walking from or to the anchor. Stairs cost 2 m per metre of floor height, lifts 15 m plus 1 m per metre.
"""

import itertools
import math
import weakref

import networkx as nx

from starter_agent.building_map import LIFT, OUTSIDE, BuildingMap, MapError, RouteResult

STAIRS_M_PER_M = 2.0
LIFT_WAIT_M = 15.0
LIFT_M_PER_M = 1.0
MAX_CACHED_GRAPHS = 6
START, END = "start", "end"

# bm -> {(closed, opening count, step_free): RoutingGraph}. Kept outside the map so deepcopy(bm) stays cheap.
_CACHE: "weakref.WeakKeyDictionary[BuildingMap, dict]" = weakref.WeakKeyDictionary()


def graph_signature(bm: BuildingMap, step_free: bool) -> tuple:
    """Changes whenever closures or doors change (same idea as guide_tools.building_signature)."""
    openings = hash(
        tuple(
            (o["id"], o["step_free"], o.get("width_m"), tuple(o["position"]), tuple(o["space_ids"]))
            for o in bm.openings.values()
        )
    )
    return (tuple(sorted(bm.closed)), len(bm.openings), openings, step_free)


class RoutingGraph:
    def __init__(self, graph: nx.Graph, members: dict[str, list[tuple]]) -> None:
        self.graph = graph
        self.members = members  # space id -> its nodes


def vertical_cost(bm: BuildingMap, connector: dict, floor_a: str, floor_b: str) -> float:
    height = abs(bm.floors[floor_a]["elevation_m"] - bm.floors[floor_b]["elevation_m"])
    if connector["kind"] == LIFT:
        return LIFT_WAIT_M + LIFT_M_PER_M * height
    return STAIRS_M_PER_M * height


def build_graph(bm: BuildingMap, step_free: bool) -> RoutingGraph:
    graph = nx.Graph()
    members: dict[str, list[tuple]] = {}
    positions: dict[tuple, tuple[float, float]] = {}

    def add_member(space_id: str, node: tuple, position: tuple[float, float]) -> None:
        members.setdefault(space_id, []).append(node)
        positions[node] = position

    for opening in bm.openings.values():
        if opening["id"] in bm.closed or (step_free and not opening["step_free"]):
            continue
        first, second = opening["space_ids"]
        if first in bm.closed or second in bm.closed:
            continue
        position = (opening["position"][0], opening["position"][1])
        nodes = [("o", opening["id"], space_id) for space_id in (first, second)]
        graph.add_edge(nodes[0], nodes[1], weight=0.0)
        add_member(first, nodes[0], position)
        add_member(second, nodes[1], position)
    levels = {floor_id: floor["level"] for floor_id, floor in bm.floors.items()}
    for connector in bm.connectors.values():
        if connector["id"] in bm.closed or (step_free and not connector["step_free"]):
            continue
        stops = sorted(zip(connector["floor_ids"], connector["space_ids"], strict=True), key=lambda s: levels[s[0]])
        stops = [stop for stop in stops if stop[1] in bm.spaces and stop[1] not in bm.closed]
        for (floor_a, space_a), (floor_b, space_b) in itertools.pairwise(stops):
            node_a, node_b = ("c", connector["id"], space_a), ("c", connector["id"], space_b)
            graph.add_edge(node_a, node_b, weight=vertical_cost(bm, connector, floor_a, floor_b))
            for space_id, node in ((space_a, node_a), (space_b, node_b)):
                if node not in positions:
                    add_member(space_id, node, bm.anchor(space_id))
    for space_id, nodes in members.items():
        for node_a, node_b in itertools.combinations(nodes, 2):
            weight = 0.0 if space_id == OUTSIDE else math.dist(positions[node_a], positions[node_b])
            if graph.has_edge(node_a, node_b):
                weight = min(weight, graph[node_a][node_b]["weight"])
            graph.add_edge(node_a, node_b, weight=weight)
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


def shortest_leg(bm: BuildingMap, rg: RoutingGraph, start: str, end: str) -> tuple[float, list[tuple]] | None:
    """(length, node path without the virtual start and end nodes), or None if there is no route."""
    if start in bm.closed or end in bm.closed:
        return None
    if start == end:
        return 0.0, []
    graph = rg.graph
    start_node, end_node = (START, start), (END, end)
    try:
        for tag_node, space_id in ((start_node, start), (end_node, end)):
            for node in rg.members.get(space_id, []):
                graph.add_edge(tag_node, node, weight=0.0)
        if start_node not in graph or end_node not in graph:
            return None
        try:
            length, path = nx.single_source_dijkstra(graph, start_node, end_node, weight="weight")
        except nx.NetworkXNoPath:
            return None
    finally:
        graph.remove_nodes_from([start_node, end_node])
    return length, path[1:-1]


def leg_spaces(start: str, end: str, nodes: list[tuple]) -> list[str]:
    """Ordered spaces of one leg; consecutive nodes of the same space count once."""
    spaces = [start]
    for node in nodes:
        if node[2] != spaces[-1]:
            spaces.append(node[2])
    if spaces[-1] != end:
        spaces.append(end)
    return spaces


def describe_steps(bm: BuildingMap, rg: RoutingGraph, spaces: list[str], legs: list[list[tuple]]) -> list[str]:
    """Steps worded like BuildingMap.directions: one line per room change or floor change."""
    steps = [f"Start in {bm.describe_space(spaces[0])}."]
    for nodes in legs:
        steps += describe_leg(bm, rg, nodes)
    steps.append(f"You have arrived at {bm.describe_space(spaces[-1])}.")
    return steps


def describe_leg(bm: BuildingMap, rg: RoutingGraph, nodes: list[tuple]) -> list[str]:
    steps: list[str] = []
    walked = 0.0
    for previous, current in itertools.pairwise(nodes):
        weight = rg.graph[previous][current]["weight"]
        same_element = previous[:2] == current[:2] and previous[2] != current[2]
        if not same_element:
            walked += weight
            continue
        target = current[2]
        if current[0] == "c":
            connector = bm.connectors[current[1]]
            verb = "Take" if connector["kind"] == LIFT else "Use"
            floor = bm.floor_name(bm.spaces[target]["floor_id"])
            steps.append(f"{verb} {connector['name']} ({connector['kind']}) to {floor}.")
        elif target == OUTSIDE:
            steps.append(f"Walk about {walked:.0f} m and leave the building through the entrance.")
        else:
            kind = bm.openings[current[1]]["kind"]
            passage = {"door": "through the door", "entrance": "outside to the entrance and in"}.get(
                kind, "through the opening"
            )
            steps.append(f"Walk about {walked:.0f} m {passage} into {bm.spaces[target]['name']}.")
        walked = 0.0
    return steps


def route(
    bm: BuildingMap, start: str, destination: str, step_free: bool = False, via: list[str] | None = None
) -> RouteResult:
    """Shortest walk start -> via... -> destination in the door-to-door model. Sets bm.last_route."""
    stops = [bm.resolve_space(start), *[bm.resolve_space(stop) for stop in via or []], bm.resolve_space(destination)]
    rg = routing_graph(bm, step_free)
    length = 0.0
    spaces: list[str] = []
    legs: list[list[tuple]] = []
    for leg_start, leg_end in itertools.pairwise(stops):
        found = shortest_leg(bm, rg, leg_start, leg_end)
        if found is None:
            reason = "step-free " if step_free else ""
            raise MapError(
                f"No {reason}route from {bm.describe_space(leg_start)} to "
                f"{bm.describe_space(leg_end)} with the current closures {sorted(bm.closed)}."
            )
        leg_length, nodes = found
        length += leg_length
        leg = leg_spaces(leg_start, leg_end, nodes)
        spaces += leg if not spaces else leg[1:]
        legs.append(nodes)
    if len(stops) == 1:
        spaces = [stops[0]]
    result = RouteResult(
        start_space_id=stops[0],
        destination_space_id=stops[-1],
        length_m=round(length, 2),
        space_path=spaces,
        steps=describe_steps(bm, rg, spaces, legs),
        step_free=step_free,
        closed=sorted(bm.closed),
    )
    bm.last_route = result
    return result
