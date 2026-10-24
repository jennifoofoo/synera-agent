"""Second router: shortest routes under Synera's scoring model, not the kit model.

The kit model (README section 3, `BuildingMap.route`) labelled the dataset: anchor-to-door straight lines, 12 m per
stair floor, 15 + 6 m per lift floor. The organizers score route answers differently (announced on Discord):

- Walking is measured inside each space, door to door, about 15 cm off the walls, around corners, never through
  walls. Furniture is not an obstacle.
- Stairs: 2 m of walking per metre climbed. Lift: 15 m (waiting, doors) plus 1 m per metre of height.
- Step-free: no stairs, nothing with `step_free: false`.
- Forklift: forklift aisles and openings 3 m or wider only; pedestrian walkways do not count.
- Factory bays are destinations, never a shortcut: you may drive or walk into one, but not through one.
- Closed elements must be avoided. If no route exists, say so.
- The answer is the ordered list of spaces. The jury checks every step uses a real door, opening, stair or lift,
  then measures the route with its own distance rule; our length only matters for picking the sequence.

Nothing here touches `BuildingMap` or the kinds; `errand` keeps the kit numbers.

Assumptions (verified against the data in tests/test_judge_route.py, see the report there):
- The route starts and ends at the start/destination space's `representative_point` (`endpoint="centre"`), the same
  anchor the kit uses. `endpoint="door"` instead starts/ends at the space's best door (the start and end space
  cost nothing). Both are available; the default is "centre" because the jury says it measures walking inside
  each space, which includes the first and last one.
- "Outside" is one node, as in the kit; entrances are joined across it at their straight-line distance (walking
  around the building is at least that long), not for free.
- Inside a stairwell or lift space the connector sits at the space's representative point.
- A forklift aisle is a corridor/hall whose name or room_type mentions an aisle (keywords in FORKLIFT_AISLE_WORDS);
  the factory buildings name them "Main aisle H1B2". A bay is a hall that is not a lobby, or any space whose
  room_type/name mentions a bay or zone (BAY_WORDS). Unknown names on the Sunday building fall through these
  keyword lists; the lists are the single place to extend.
- A forklift never takes stairs; it may take a lift only if its doors are wide enough (never, in this data).
"""

from __future__ import annotations

import heapq
import itertools
import math
import weakref
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import nearest_points

from building_agent.geometry import repaired
from starter_agent.building_map import LIFT, OUTSIDE, BuildingMap, MapError

WALL_CLEARANCE_M = 0.15
STAIRS_M_PER_M_CLIMBED = 2.0
LIFT_WAIT_M = 15.0
LIFT_M_PER_M = 1.0
FORKLIFT_MIN_WIDTH_M = 3.0
DEFAULT_FLOOR_HEIGHT_M = 3.0
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


# ---------- geometry inside one space ----------


@dataclass
class SpaceGeometry:
    polygon: Polygon  # walkable area: outline shrunk by the wall clearance (or less, see shrink())
    convex: bool
    adjacent: dict[tuple[float, float], dict[tuple[float, float], float]]  # visibility graph: corners + points
    tolerant: Polygon  # polygon.buffer(EPS), prepared: visibility tests along the boundary must pass
    cache: dict[tuple[float, float], dict] = field(default_factory=dict)  # single-source distances

    def inside_point(self, point: tuple[float, float]) -> tuple[tuple[float, float], float]:
        """Nearest walkable point to `point` (doors sit on the wall, so 15 cm inside) and the offset to it."""
        p = Point(point)
        if self.polygon.covers(p):
            return point, 0.0
        inside = nearest_points(self.polygon, p)[0]
        return (inside.x, inside.y), p.distance(inside)

    def distances(self, points: list[tuple[float, float]]) -> dict[tuple, float]:
        """Shortest walks between all pairs of walkable points (geodesics in the shrunk polygon)."""
        result: dict[tuple, float] = {}
        if self.convex:
            for a, b in itertools.combinations(points, 2):
                result[(a, b)] = result[(b, a)] = math.dist(a, b)
            return result
        for point in points:
            self.add_node(point)
        for a in points:
            hidden = [b for b in points if b != a and b not in self.adjacent[a]]
            if hidden and a not in self.cache:
                self.cache[a] = self._dijkstra(a)
            for b in points:
                if b == a:
                    continue
                if b in hidden:
                    # No path: the walkable area is split by a neck thinner than the clearance; walk straight.
                    result[(a, b)] = self.cache[a].get(b, math.dist(a, b))
                else:
                    result[(a, b)] = math.dist(a, b)
        return result

    def _dijkstra(self, source: tuple[float, float]) -> dict[tuple[float, float], float]:
        done: dict[tuple[float, float], float] = {}
        heap = [(0.0, source)]
        while heap:
            cost, node = heapq.heappop(heap)
            if node in done:
                continue
            done[node] = cost
            for other, weight in self.adjacent[node].items():
                if other not in done:
                    heapq.heappush(heap, (cost + weight, other))
        return done

    def add_node(self, point: tuple[float, float]) -> None:
        if point in self.adjacent:
            return
        self.cache.clear()  # cached single-source distances must see the new node
        others = list(self.adjacent)
        self.adjacent[point] = {}
        if not others:
            return
        lines = shapely.linestrings(np.array([[point, other] for other in others]))
        for other, ok in zip(others, shapely.covers(self.tolerant, lines), strict=True):
            if ok:
                self.adjacent[point][other] = self.adjacent[other][point] = math.dist(point, other)


def shrink(outline: Polygon, clearance: float = WALL_CLEARANCE_M) -> Polygon:
    """Outline minus the wall clearance. If that vanishes or splits, use less clearance, down to the outline."""
    outline = repaired(outline)
    margin = clearance
    while margin > 0:
        shrunk = outline.buffer(-margin, join_style="mitre")
        if isinstance(shrunk, Polygon) and not shrunk.is_empty and shrunk.area > EPS:
            return shrunk
        if isinstance(shrunk, MultiPolygon) and shrunk.area > 0.9 * outline.area:
            return max(shrunk.geoms, key=lambda part: part.area)
        margin = round(margin - 0.05, 3)
    return outline


def reflex_corners(polygon: Polygon) -> list[tuple[float, float]]:
    """Concave corners: the only vertices a shortest path inside the polygon bends at."""
    corners = []
    for is_exterior, ring in ((True, polygon.exterior), *((False, hole) for hole in polygon.interiors)):
        coords = list(ring.coords)[:-1]
        ccw = ring.is_ccw if is_exterior else not ring.is_ccw  # interior of a hole lies on the other side
        n = len(coords)
        for i in range(n):
            (ax, ay), (bx, by), (cx, cy) = coords[i - 1], coords[i], coords[(i + 1) % n]
            cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
            if (cross < -EPS) if ccw else (cross > EPS):
                corners.append((bx, by))
    return corners


def space_geometry(outline: Polygon) -> SpaceGeometry:
    walkable = shrink(outline)
    convex = walkable.convex_hull.area <= walkable.area * (1 + 1e-6)
    tolerant = walkable.buffer(EPS)
    shapely.prepare(tolerant)
    geometry = SpaceGeometry(walkable, convex, {}, tolerant)
    if not convex:
        for corner in reflex_corners(walkable):
            geometry.add_node(corner)
    return geometry


# ---------- the router ----------

Node = tuple  # ("door", opening_id) | ("stop", connector_id, space_id) | ("end", space_id) | ("outside",)
OUTSIDE_NODE: Node = ("outside",)


class JudgeRouter:
    """Routes one BuildingMap under the jury's rules.

    The door-to-door graph is expanded lazily during the search, so a route only pays for the spaces it explores;
    per-space geometry is cached for the map's lifetime."""

    def __init__(self, bm: BuildingMap) -> None:
        self.bm = bm
        self._geometry: dict[str, SpaceGeometry] = {}
        self._anchor: dict[str, tuple[float, float]] = {}

    def geometry(self, space_id: str) -> SpaceGeometry:
        if space_id not in self._geometry:
            self._geometry[space_id] = space_geometry(Polygon(self.bm.spaces[space_id]["polygon"]))
        return self._geometry[space_id]

    def anchor(self, space_id: str) -> tuple[float, float]:
        """Where a route starts or ends inside a space: the kit's representative point, moved off the walls."""
        if space_id not in self._anchor:
            point = repaired(Polygon(self.bm.spaces[space_id]["polygon"])).representative_point()
            self._anchor[space_id] = self.geometry(space_id).inside_point((point.x, point.y))[0]
        return self._anchor[space_id]

    def elevation(self, floor_id: str) -> float:
        floor = self.bm.floors[floor_id]
        if floor.get("elevation_m") is not None:
            return float(floor["elevation_m"])
        return float(floor["level"]) * DEFAULT_FLOOR_HEIGHT_M

    # -- indexes over the building, rebuilt when openings or connectors change --

    def _index(self) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
        key = (tuple(self.bm.openings), tuple(self.bm.connectors))
        if getattr(self, "_index_key", None) != key:
            openings: dict[str, list[dict]] = {}
            connectors: dict[str, list[dict]] = {}
            for opening in self.bm.openings.values():
                for space_id in opening["space_ids"]:
                    openings.setdefault(space_id, []).append(opening)
            for connector in self.bm.connectors.values():
                for space_id in connector["space_ids"]:
                    connectors.setdefault(space_id, []).append(connector)
            self._index_key, self._openings_by_space, self._connectors_by_space = key, openings, connectors
        return self._openings_by_space, self._connectors_by_space

    # -- rules --

    def _space_allowed(self, space_id: str, forklift: bool) -> bool:
        if space_id in self.bm.closed or space_id not in self.bm.spaces:
            return False
        return forklift_may_use(self.bm.spaces[space_id]) if forklift else True

    def _opening_allowed(self, opening: dict, step_free: bool, forklift: bool) -> bool:
        if opening["id"] in self.bm.closed:
            return False
        if (step_free or forklift) and not opening["step_free"]:
            return False
        return not (forklift and opening["width_m"] < FORKLIFT_MIN_WIDTH_M - EPS)

    def _connector_allowed(self, connector: dict, step_free: bool, forklift: bool) -> bool:
        if connector["id"] in self.bm.closed:
            return False
        return connector["step_free"] or not (step_free or forklift)

    # -- lazy graph --

    def _portals(self, space_id: str, step_free: bool, forklift: bool, ends: dict) -> list[tuple[Node, tuple | None]]:
        """Every node inside a space with its position: doors, stair/lift stops, the leg endpoint if any."""
        openings_by_space, connectors_by_space = self._index()
        portals: list[tuple[Node, tuple | None]] = []
        for opening in openings_by_space.get(space_id, []):
            if self._opening_allowed(opening, step_free, forklift):
                other = self.bm.other_side(opening, space_id)
                if other == OUTSIDE or self._space_allowed(other, forklift):
                    portals.append((("door", opening["id"]), tuple(opening["position"])))
        for connector in connectors_by_space.get(space_id, []):
            if self._connector_allowed(connector, step_free, forklift):
                portals.append((("stop", connector["id"], space_id), self.anchor(space_id)))
        if space_id in ends:
            portals.append((("end", space_id), ends[space_id]))
        return portals

    def _space_edges(
        self, space_id: str, step_free: bool, forklift: bool, ends: dict
    ) -> list[tuple[Node, Node, float]]:
        """Walks between all portals of one space. In a bay only the endpoint is connected (no shortcuts)."""
        if space_id == OUTSIDE:
            portals = [
                (("door", opening["id"]), tuple(opening["position"]))
                for opening in self._index()[0].get(OUTSIDE, [])
                if self._opening_allowed(opening, step_free, forklift)
                and self._space_allowed(self.bm.other_side(opening, OUTSIDE), forklift)
            ]
            return [(a, b, math.dist(pa, pb)) for (a, pa), (b, pb) in itertools.combinations(portals, 2)]
        portals = self._portals(space_id, step_free, forklift, ends)
        bay = is_bay(self.bm.spaces[space_id])
        geometry = self.geometry(space_id)
        located = []
        for node, position in portals:
            if position is None:  # "door" endpoint mode: any door of the space is reached for free
                located.append((node, None, 0.0))
            else:
                inside, offset = geometry.inside_point(position)
                located.append((node, inside, offset))
        walks = geometry.distances(sorted({inside for _, inside, _ in located if inside is not None}))
        edges = []
        for (node_a, in_a, off_a), (node_b, in_b, off_b) in itertools.combinations(located, 2):
            is_end = (node_a[0] == "end", node_b[0] == "end")
            if bay and not any(is_end):
                continue
            if in_a is None or in_b is None:
                if is_end[0] == is_end[1]:
                    continue
                weight = 0.0
            elif in_a == in_b:
                weight = off_a + off_b
            else:
                weight = off_a + walks[(in_a, in_b)] + off_b
            edges.append((node_a, node_b, weight))
        return edges

    def _vertical_edges(self, connector: dict, forklift: bool) -> list[tuple[Node, Node, float]]:
        levels = {floor_id: self.elevation(floor_id) for floor_id in connector["floor_ids"]}
        stops = sorted(zip(connector["floor_ids"], connector["space_ids"], strict=True), key=lambda s: levels[s[0]])
        stops = [stop for stop in stops if self._space_allowed(stop[1], forklift)]
        edges = []
        for (low_floor, low_space), (high_floor, high_space) in itertools.pairwise(stops):
            climb = abs(levels[high_floor] - levels[low_floor])
            cost = LIFT_WAIT_M + LIFT_M_PER_M * climb if connector["kind"] == LIFT else STAIRS_M_PER_M_CLIMBED * climb
            edges.append((("stop", connector["id"], low_space), ("stop", connector["id"], high_space), cost))
        return edges

    def _search(self, source: Node, target: Node, step_free: bool, forklift: bool, ends: dict):
        """Dijkstra over portal nodes, expanding each space's walks the first time a node inside it is settled.

        Returns (length, nodes, edge info per step) or None. Edge info: (space walked through or None, element)."""
        _openings_by_space, connectors_by_space = self._index()
        adjacency: dict[Node, dict[Node, tuple[float, str | None, str | None]]] = {}
        expanded: set[str] = set()

        def expand(space_id: str) -> None:
            if space_id in expanded:
                return
            expanded.add(space_id)
            for a, b, weight in self._space_edges(space_id, step_free, forklift, ends):
                for x, y in ((a, b), (b, a)):
                    current = adjacency.setdefault(x, {}).get(y)
                    if current is None or current[0] > weight:  # two doors between the same rooms: keep the cheaper
                        adjacency[x][y] = (weight, space_id, None)
            for connector in connectors_by_space.get(space_id, []) if space_id in self.bm.spaces else []:
                if self._connector_allowed(connector, step_free, forklift):
                    for a, b, weight in self._vertical_edges(connector, forklift):
                        adjacency.setdefault(a, {})[b] = (weight, None, connector["id"])
                        adjacency.setdefault(b, {})[a] = (weight, None, connector["id"])

        def spaces_of(node: Node) -> list[str]:
            if node[0] == "door":
                return list(self.bm.openings[node[1]]["space_ids"])
            return [node[-1]]

        best: dict[Node, float] = {source: 0.0}
        previous: dict[Node, Node] = {}
        heap = [(0.0, 0, source)]
        counter = 1
        settled: set[Node] = set()
        while heap:
            cost, _, node = heapq.heappop(heap)
            if node in settled:
                continue
            settled.add(node)
            if node == target:
                break
            for space_id in spaces_of(node):
                if space_id == OUTSIDE or self._space_allowed(space_id, forklift):
                    expand(space_id)
            for other, (weight, _, _) in adjacency.get(node, {}).items():
                new_cost = cost + weight
                if other not in settled and new_cost < best.get(other, math.inf) - 1e-12:
                    best[other] = new_cost
                    previous[other] = node
                    heapq.heappush(heap, (new_cost, counter, other))
                    counter += 1
        if target not in settled:
            return None
        nodes = [target]
        while nodes[-1] != source:
            nodes.append(previous[nodes[-1]])
        nodes.reverse()
        info = [adjacency[a][b][1:] for a, b in itertools.pairwise(nodes)]
        return best[target], nodes, info

    # -- routing --

    def route(
        self,
        start: str,
        destination: str,
        step_free: bool = False,
        forklift: bool = False,
        via: list[str] | None = None,
        endpoint: str = "centre",
    ) -> RouteAnswer:
        """Shortest route under the jury's rules. `endpoint`: "centre" (representative point) or "door"."""
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
        spaces: list[str] = [stops[0]]
        elements: list[str] = []
        total = 0.0
        for leg_start, leg_end in itertools.pairwise(stops):
            if leg_start == leg_end:
                continue
            ends = {s: (None if endpoint == "door" else self.anchor(s)) for s in (leg_start, leg_end)}
            found = self._search(("end", leg_start), ("end", leg_end), step_free, forklift, ends)
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
            length, nodes, info = found
            total += length
            for (previous, current), (space, via_element) in zip(itertools.pairwise(nodes), info, strict=True):
                if via_element is not None:  # stairs or lift
                    elements.append(via_element)
                    spaces.append(current[2])
                elif space != spaces[-1]:
                    elements.append(previous[1] if previous[0] == "door" else current[1])
                    spaces.append(space)
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
    endpoint: str = "centre",
) -> dict:
    """Route under the jury's scoring rules; same inputs as BuildingMap.route plus `forklift`.

    Returns {"ok", "space_path", "length_m", "element_path", "reason"}; ok=False means no route and `reason` says why
    (the correct answer then is to say so). Respects bm.closed."""
    return router_for(bm).route(start, destination, step_free, forklift, via, endpoint).as_dict()
