"""Prototype geodesic route metric (spike, not production).

Models the distance rule Synera announced: walking inside each space from door to door, 0.15 m off
the walls, around corners; stairs 2 m per metre climbed; lifts 15 m + 1 m per metre of height.

Three in-space metrics share one graph builder so they can be compared:
  "geodesic": shortest path inside the shrunk polygon (visibility graph over reflex vertices)
  "straight": straight door-to-door distance inside the space
  "anchor":   door -> space anchor -> door (the kit's coarse model)
Vertical cost: "synera" (2 m per m / 15 m + 1 m per m) or "kit" (12 m per level / 15 m + 6 m per level).
Endpoints: "door" (the first and last space cost nothing, route is door to door) or "anchor"
(walk from/to the room's anchor point).
"""

import itertools
import math

import networkx as nx
import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import nearest_points
from shapely.prepared import prep

OUTSIDE = "outside"
WALL_OFFSET_M = 0.15
EPS = 1e-6
STAIR_M_PER_M = 2.0
LIFT_WAIT_M = 15.0
LIFT_M_PER_M = 1.0
KIT_STAIR_PER_LEVEL = 12.0
KIT_LIFT_WAIT = 15.0
KIT_LIFT_PER_LEVEL = 6.0


class SpaceGeometry:
    """Walkable area of one space plus a cached visibility graph over its reflex vertices."""

    def __init__(self, raw: Polygon) -> None:
        if not raw.is_valid:
            raw = raw.buffer(0)
            if raw.geom_type != "Polygon":
                raw = max(raw.geoms, key=lambda g: g.area)
        shrunk = raw.buffer(-WALL_OFFSET_M)
        # fall back to the raw polygon if shrinking empties or splits the room
        self.fallback = shrunk.is_empty or shrunk.geom_type != "Polygon"
        self.poly = orient(raw if self.fallback else shrunk, 1.0)
        self.cover = prep(self.poly.buffer(EPS))
        self.verts = self._reflex_vertices()
        n = len(self.verts)
        self.matrix = np.full((n, n), np.inf)
        for i in range(n):
            self.matrix[i, i] = 0.0
            for j in range(i + 1, n):
                if self.visible(self.verts[i], self.verts[j]):
                    self.matrix[i, j] = self.matrix[j, i] = math.dist(self.verts[i], self.verts[j])
        for k in range(n):  # Floyd-Warshall, vectorised
            self.matrix = np.minimum(self.matrix, self.matrix[:, k : k + 1] + self.matrix[k : k + 1, :])
        self.vis_cache: dict[tuple, np.ndarray] = {}
        self.dist_cache: dict[tuple, float] = {}
        self.fallback_hits = 0

    def _reflex_vertices(self) -> list[tuple[float, float]]:
        out = []
        for ring in [self.poly.exterior, *self.poly.interiors]:
            pts = list(ring.coords)[:-1]
            for i, cur in enumerate(pts):
                prev, nxt = pts[i - 1], pts[(i + 1) % len(pts)]
                cross = (cur[0] - prev[0]) * (nxt[1] - cur[1]) - (cur[1] - prev[1]) * (nxt[0] - cur[0])
                if cross < -1e-9:  # interior is on the left, so a right turn is reflex
                    out.append(cur)
        return out

    def visible(self, a: tuple[float, float], b: tuple[float, float]) -> bool:
        if math.dist(a, b) < 1e-9:
            return True
        return self.cover.covers(LineString([a, b]))

    def snap(self, p: tuple[float, float]) -> tuple[float, float]:
        point = Point(p)
        if self.cover.covers(point):
            return p
        q = nearest_points(self.poly, point)[0]
        return (q.x, q.y)

    def _vis_vector(self, p: tuple[float, float]) -> np.ndarray:
        cached = self.vis_cache.get(p)
        if cached is None:
            cached = np.array([math.dist(p, v) if self.visible(p, v) else np.inf for v in self.verts])
            self.vis_cache[p] = cached
        return cached

    def distance(self, p: tuple[float, float], q: tuple[float, float]) -> float:
        key = (p, q) if p <= q else (q, p)
        hit = self.dist_cache.get(key)
        if hit is not None:
            return hit
        a, b = self.snap(p), self.snap(q)
        if self.visible(a, b):
            result = math.dist(a, b)
        elif not self.verts:
            self.fallback_hits += 1
            result = math.dist(a, b)
        else:
            va, vb = self._vis_vector(a), self._vis_vector(b)
            best = float((va[:, None] + self.matrix + vb[None, :]).min())
            if not math.isfinite(best):
                self.fallback_hits += 1
                best = math.dist(a, b)
            result = best
        self.dist_cache[key] = result
        return result


class RouteModel:
    """Everything needed to route and measure on one building under one metric."""

    def __init__(
        self,
        bm,
        metric: str = "geodesic",
        vertical: str = "synera",
        endpoints: str = "door",
        step_free: bool = False,
        closed: set[str] | None = None,
    ) -> None:
        self.bm = bm
        self.metric = metric
        self.vertical = vertical
        self.endpoints = endpoints
        self.step_free = step_free
        self.closed = set(closed if closed is not None else bm.closed)
        self.geoms: dict[str, SpaceGeometry] = {}
        self.anchors: dict[str, tuple[float, float]] = {}
        self.graph: nx.Graph | None = None
        self.members: dict[str, list[tuple]] = {}

    # ---- geometry ----

    def anchor(self, space_id: str) -> tuple[float, float]:
        if space_id not in self.anchors:
            self.anchors[space_id] = self.bm.anchor(space_id)
        return self.anchors[space_id]

    def geom(self, space_id: str) -> SpaceGeometry:
        if space_id not in self.geoms:
            self.geoms[space_id] = SpaceGeometry(Polygon(self.bm.spaces[space_id]["polygon"]))
        return self.geoms[space_id]

    def inside(self, space_id: str, p: tuple[float, float], q: tuple[float, float]) -> float:
        if space_id == OUTSIDE or p == q:
            return 0.0
        if self.metric == "geodesic":
            return self.geom(space_id).distance(p, q)
        if self.metric == "straight":
            return math.dist(p, q)
        a = self.anchor(space_id)
        return math.dist(p, a) + math.dist(a, q)

    # ---- elements ----

    def opening_ok(self, opening: dict) -> bool:
        if opening["id"] in self.closed or (self.step_free and not opening["step_free"]):
            return False
        return not any(s in self.closed for s in opening["space_ids"])

    def connector_stops(self, connector: dict) -> list[tuple[str, str]]:
        """(floor_id, space_id) per stop in level order."""
        levels = {fid: f["level"] for fid, f in self.bm.floors.items()}
        stops = zip(connector["floor_ids"], connector["space_ids"], strict=True)
        return sorted(stops, key=lambda s: levels[s[0]])

    def connector_ok(self, connector: dict) -> bool:
        return not (connector["id"] in self.closed or (self.step_free and not connector["step_free"]))

    def vertical_cost(self, connector: dict, low_floor: str, high_floor: str) -> float:
        floors = self.bm.floors
        is_lift = connector["kind"] == "lift"
        if self.vertical == "kit":
            span = abs(floors[high_floor]["level"] - floors[low_floor]["level"])
            return KIT_LIFT_WAIT + KIT_LIFT_PER_LEVEL * span if is_lift else KIT_STAIR_PER_LEVEL * span
        height = abs(floors[high_floor]["elevation_m"] - floors[low_floor]["elevation_m"])
        return LIFT_WAIT_M + LIFT_M_PER_M * height if is_lift else STAIR_M_PER_M * height

    # ---- graph ----

    def build(self) -> nx.Graph:
        if self.graph is not None:
            return self.graph
        g = nx.Graph()
        members: dict[str, list[tuple]] = {}  # space -> [(node, position)]

        def add_member(space_id: str, node: tuple, pos: tuple[float, float]) -> None:
            members.setdefault(space_id, []).append((node, pos))

        for opening in self.bm.openings.values():
            if not self.opening_ok(opening):
                continue
            pos = tuple(opening["position"])
            first, second = opening["space_ids"]
            nodes = [("o", opening["id"], s) for s in (first, second)]
            g.add_edge(nodes[0], nodes[1], weight=0.0)
            add_member(first, nodes[0], pos)
            add_member(second, nodes[1], pos)
        for connector in self.bm.connectors.values():
            if not self.connector_ok(connector):
                continue
            stops = [s for s in self.connector_stops(connector) if s[1] not in self.closed]
            for (floor_a, space_a), (floor_b, space_b) in itertools.pairwise(stops):
                if space_a not in self.bm.spaces or space_b not in self.bm.spaces:
                    continue
                na, nb = ("c", connector["id"], space_a), ("c", connector["id"], space_b)
                g.add_edge(na, nb, weight=self.vertical_cost(connector, floor_a, floor_b))
                for space_id, node in ((space_a, na), (space_b, nb)):
                    if node not in [m[0] for m in members.get(space_id, [])]:
                        add_member(space_id, node, self.anchor(space_id))
        for space_id, items in members.items():
            for (na, pa), (nb, pb) in itertools.combinations(items, 2):
                weight = self.inside(space_id, pa, pb)
                if g.has_edge(na, nb):
                    weight = min(weight, g[na][nb]["weight"])
                g.add_edge(na, nb, weight=weight)
        self.graph = g
        self.members = members
        return g

    def best_route(self, start: str, end: str) -> tuple[list[str], float] | None:
        """Best space sequence and length, or None if there is no route."""
        if start in self.closed or end in self.closed:
            return None
        if start == end:
            return [start], 0.0
        g = self.build()
        h = g.copy()
        for tag, space_id in (("S", start), ("E", end)):
            h.add_node((tag, space_id))
            for node, pos in self.members.get(space_id, []):
                cost = 0.0 if self.endpoints == "door" else self.inside(space_id, self.anchor(space_id), pos)
                h.add_edge((tag, space_id), node, weight=cost)
        try:
            length, path = nx.single_source_dijkstra(h, ("S", start), ("E", end), weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        sequence = [start]
        for node in path[1:-1]:
            if node[2] != sequence[-1]:
                sequence.append(node[2])
        if sequence[-1] != end:
            sequence.append(end)
        return sequence, length

    # ---- measure an arbitrary sequence ----

    def links(self, a: str, b: str) -> list[tuple[tuple[float, float], tuple[float, float], float]]:
        """Ways to step from space a to space b: (position in a, position in b, extra cost)."""
        out = []
        for opening in self.bm.openings.values():
            if set(opening["space_ids"]) == {a, b} and a != b and self.opening_ok(opening):
                pos = tuple(opening["position"])
                out.append((pos, pos, 0.0))
        for connector in self.bm.connectors.values():
            if not self.connector_ok(connector):
                continue
            for (fa, sa), (fb, sb) in itertools.pairwise(self.connector_stops(connector)):
                if {sa, sb} == {a, b} and a != b:
                    cost = self.vertical_cost(connector, fa, fb)
                    out.append((self.anchor(a), self.anchor(b), cost))
        return out

    def measure(self, sequence: list[str]) -> float | None:
        """Length of the given space sequence, None if a step has no real door, opening or connector."""
        if not sequence or any(s in self.closed for s in sequence):
            return None
        if any(s != OUTSIDE and s not in self.bm.spaces for s in sequence):
            return None
        if len(sequence) == 1:
            return 0.0
        # layered DP over the choice of connection per step
        options = []
        for a, b in itertools.pairwise(sequence):
            found = self.links(a, b)
            if not found:
                return None
            options.append(found)
        first = sequence[0]
        start_pos = None if self.endpoints == "door" else self.anchor(first)
        costs = []
        for pos_a, _pos_b, extra in options[0]:
            walk = 0.0 if start_pos is None else self.inside(first, start_pos, pos_a)
            costs.append(walk + extra)
        for i in range(1, len(options)):
            space_id = sequence[i]
            nxt = []
            for pos_a, _pb, extra in options[i]:
                best = min(
                    c + self.inside(space_id, prev[1], pos_a) for c, prev in zip(costs, options[i - 1], strict=True)
                )
                nxt.append(best + extra)
            costs = nxt
        total = min(costs)
        if self.endpoints != "door":
            last = sequence[-1]
            end_pos = self.anchor(last)
            total = min(c + self.inside(last, prev[1], end_pos) for c, prev in zip(costs, options[-1], strict=True))
        return total


def model_for(bm, **kwargs) -> RouteModel:
    """Cached model per (metric options, step_free, closed set) on a BuildingMap."""
    cache = bm.__dict__.setdefault("_route_models", {})
    key = (
        kwargs.get("metric", "geodesic"),
        kwargs.get("vertical", "synera"),
        kwargs.get("endpoints", "door"),
        kwargs.get("step_free", False),
        frozenset(kwargs.get("closed", bm.closed)),
    )
    if key not in cache:
        cache[key] = RouteModel(bm, **kwargs)
    return cache[key]


def best_route(bm, start_space: str, end_space: str, step_free: bool = False, **kwargs):
    """(space_sequence, length_m) under the geodesic metric, or None if unreachable."""
    return model_for(bm, step_free=step_free, **kwargs).best_route(start_space, end_space)


def measure(bm, space_sequence: list[str], step_free: bool = False, **kwargs) -> float | None:
    """Length of an arbitrary space sequence under the geodesic metric, None if invalid."""
    return model_for(bm, step_free=step_free, **kwargs).measure(space_sequence)
