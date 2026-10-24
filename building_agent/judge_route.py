"""Forklift routes on the kit's route model.

There is one route model (README section 3, `BuildingMap.graph`, cached by building_agent.routing): door-to-door
walking 15 cm off the walls, stairs 2 m per metre climbed, a lift ride 15 m plus 1 m per metre climbed, no way round
the outside. A forklift route is that graph with the vehicle's restrictions cut out of it:

- Forklift: forklift aisles and openings 3 m or wider only; pedestrian walkways do not count. Never stairs (and
  nothing with `step_free: false`).
- Factory bays are destinations, never a shortcut: you may drive or walk into one, but not through one.
- Closed elements must be avoided. If no route exists, say so.

Nothing here touches the kit router; `routing.route` serves people, `errand` keeps the kit numbers.

Assumptions (verified against the data in tests/test_judge_route.py):
- A forklift aisle is a corridor/hall whose name or room_type mentions an aisle (keywords in FORKLIFT_AISLE_WORDS);
  the factory buildings name them "Main aisle H1B2". A bay is a hall that is not a lobby, or any space whose
  room_type/name mentions a bay or zone (BAY_WORDS). Unknown names on the Sunday building fall through these
  keyword lists; the lists are the single place to extend.
- A forklift never takes stairs; it may take a lift between two aisle or bay spaces.
"""

import itertools
import weakref
from dataclasses import dataclass, field

import networkx as nx

from building_agent import routing
from starter_agent.building_map import DOOR_PREFIX, BuildingMap, MapError

FORKLIFT_MIN_WIDTH_M = 3.0
EPS = 1e-6

FORKLIFT_AISLE_WORDS = ("aisle", "forklift", "driveway", "drive lane", "lane")
BAY_WORDS = ("bay", "zone", "production", "assembly", "warehouse", "logistics", "additive", "workshop")
LOBBY_WORDS = ("lobby", "foyer", "atrium", "entrance", "reception", "hall")
PEDESTRIAN_CORRIDOR_WORDS = ("walkway", "pedestrian")


@dataclass
class RouteAnswer:
    ok: bool
    space_path: list[str]
    length_m: float
    element_path: list[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "space_path": self.space_path,
            "length_m": self.length_m,
            "element_path": self.element_path,
            "reason": self.reason,
        }


# ---------- classification (data-driven, keyword based) ----------


def _words(space: dict) -> str:
    return f"{space.get('room_type', '')} {space.get('name', '')} {space.get('type', '')}".lower().replace("_", " ")


def is_bay(space: dict) -> bool:
    """Factory bay: a hall that is not a lobby, or anything named like a bay/zone. Destination only."""
    text = _words(space)
    if space.get("type") == "hall":
        return not any(word in text for word in LOBBY_WORDS if word != "hall")
    return any(word in text for word in BAY_WORDS)


def is_forklift_aisle(space: dict) -> bool:
    text = _words(space)
    if any(word in text for word in PEDESTRIAN_CORRIDOR_WORDS):
        return False
    return any(word in text for word in FORKLIFT_AISLE_WORDS)


def forklift_may_use(space: dict) -> bool:
    return is_forklift_aisle(space) or is_bay(space)


# ---------- the router ----------


class JudgeRouter:
    """Forklift (and plain) routes of one BuildingMap on the shared kit graph; restricted graphs are cached."""

    def __init__(self, bm: BuildingMap) -> None:
        self.bm = bm
        self._forklift: tuple | None = None  # (signature, restricted graph)

    def forklift_graph(self) -> nx.MultiGraph:
        """The step-free kit graph without narrow doors and without spaces a forklift may not enter."""
        signature = routing.graph_signature(self.bm, True)
        if self._forklift is None or self._forklift[0] != signature:
            graph = routing.routing_graph(self.bm, True).graph.copy()
            graph.remove_nodes_from(
                [
                    node
                    for node in list(graph)
                    if (node in self.bm.spaces and not forklift_may_use(self.bm.spaces[node]))
                    or (
                        node.startswith(DOOR_PREFIX)
                        and self.bm.openings[node.removeprefix(DOOR_PREFIX)]["width_m"] < FORKLIFT_MIN_WIDTH_M - EPS
                    )
                ]
            )
            graph.remove_edges_from(
                [
                    (first, second, key)
                    for first, second, key, space in list(graph.edges(keys=True, data="space"))
                    if space is not None and not forklift_may_use(self.bm.spaces[space])
                ]
            )
            self._forklift = (signature, graph)
        return self._forklift[1]

    @staticmethod
    def _edge(graph: nx.MultiGraph, first: str, second: str, bays: set[str]) -> dict | None:
        """The cheapest edge between two nodes that does not cross a bay other than the leg's own ends."""
        allowed = [edge for edge in graph[first][second].values() if edge.get("space") not in bays]
        return min(allowed, key=lambda edge: edge["weight"], default=None)

    def _leg(self, graph: nx.MultiGraph, start: str, end: str, forklift: bool):
        """(length, nodes, edges) of one leg, or None. In a forklift leg only its two end bays may be entered."""
        if start not in graph or end not in graph:
            return None
        bays = (
            {space for space in graph if space in self.bm.spaces and is_bay(self.bm.spaces[space])} - {start, end}
            if forklift
            else set()
        )

        def weight(first: str, second: str, edges: dict) -> float | None:
            costs = [edge["weight"] for edge in edges.values() if edge.get("space") not in bays]
            return min(costs, default=None)

        try:
            length, nodes = nx.single_source_dijkstra(graph, start, end, weight=weight)
        except nx.NetworkXNoPath:
            return None
        return length, nodes, [self._edge(graph, first, second, bays) for first, second in itertools.pairwise(nodes)]

    def route(
        self,
        start: str,
        destination: str,
        step_free: bool = False,
        forklift: bool = False,
        via: list[str] | None = None,
    ) -> RouteAnswer:
        """Shortest route under the jury's rules: the kit graph, restricted for a forklift."""
        try:
            stops = [self.bm.resolve_space(start), *[self.bm.resolve_space(s) for s in via or []]]
            stops.append(self.bm.resolve_space(destination))
        except MapError as error:
            return RouteAnswer(False, [], 0.0, reason=str(error))
        for space_id in stops:
            if space_id in self.bm.closed:
                return RouteAnswer(False, [], 0.0, reason=f"{self.bm.describe_space(space_id)} is closed.")
            if forklift and not forklift_may_use(self.bm.spaces[space_id]):
                return RouteAnswer(
                    False, [], 0.0, reason=f"{self.bm.describe_space(space_id)} is not a forklift aisle or bay."
                )
        graph = self.forklift_graph() if forklift else routing.routing_graph(self.bm, step_free).graph
        spaces: list[str] = [stops[0]]
        elements: list[str] = []
        total = 0.0
        for leg_start, leg_end in itertools.pairwise(stops):
            found = self._leg(graph, leg_start, leg_end, forklift)
            if found is None:
                mode = "forklift " if forklift else "step-free " if step_free else ""
                return RouteAnswer(
                    False,
                    [],
                    0.0,
                    reason=(
                        f"No {mode}route from {self.bm.describe_space(leg_start)} to "
                        f"{self.bm.describe_space(leg_end)} with the current closures {sorted(self.bm.closed)}."
                    ),
                )
            length, nodes, edges = found
            total += length
            for node, edge in zip(nodes[1:], edges, strict=True):
                if "via" in edge:  # stairs or lift
                    elements.append(edge["via"])
                if node.startswith(DOOR_PREFIX):
                    elements.append(node.removeprefix(DOOR_PREFIX))
                for space_id in (edge.get("space"), None if node.startswith(DOOR_PREFIX) else node):
                    if space_id is not None and spaces[-1] != space_id:
                        spaces.append(space_id)
        return RouteAnswer(True, spaces, round(total, 2), elements)


_routers: weakref.WeakKeyDictionary[BuildingMap, JudgeRouter] = weakref.WeakKeyDictionary()


def router_for(bm: BuildingMap) -> JudgeRouter:
    if bm not in _routers:
        _routers[bm] = JudgeRouter(bm)
    return _routers[bm]


def judge_route(
    bm: BuildingMap,
    start: str,
    destination: str,
    step_free: bool = False,
    forklift: bool = False,
    via: list[str] | None = None,
) -> dict:
    """Route under the jury's scoring rules; same inputs as BuildingMap.route plus `forklift`.

    Returns {"ok", "space_path", "length_m", "element_path", "reason"}; ok=False means no route and `reason` says why
    (the correct answer then is to say so). Respects bm.closed."""
    return router_for(bm).route(start, destination, step_free, forklift, via).as_dict()
