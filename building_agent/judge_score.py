"""Score a route the way Synera announced it: validity first, then best length / our length under their rule.

Rules checked: every step of the ordered space list goes through a real door, opening, stair or lift that is
open (and step-free if asked), tours visit the stops in order, closures hold. The agent's own length numbers are
ignored: the sequence is measured with the geodesic door-to-door rule from the route spike (spikes/route).
Score = best possible length / measured length, capped at 1. An invalid route scores 0. If no route exists the
only correct answer is to report none.

The geodesic code stays in spikes/route/geodesic.py and is imported from there (see _load_geodesic).
"""

import itertools
import sys
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from starter_agent.building_map import OUTSIDE, BuildingMap

FULL_MARKS = 0.99
ROUTE_KINDS = ("route", "route_step_free", "route_with_closure", "tour")


def _load_geodesic():
    """spikes is a plain directory, not part of the installed wheel: fall back to the repo root on sys.path."""
    try:
        from spikes.route import geodesic
    except ImportError:
        root = str(Path(__file__).resolve().parent.parent)
        if root not in sys.path:
            sys.path.append(root)
        from spikes.route import geodesic
    return geodesic


geodesic = _load_geodesic()


@dataclass(frozen=True)
class RouteScore:
    valid: bool
    score: float
    reason: str = ""


def _unreachable(answer: dict) -> bool:
    legs = answer.get("legs") or []
    return answer.get("reachable") is False or any(leg.get("reachable") is False for leg in legs)


def _stops(question: dict) -> list[str]:
    answer = question["answer"]
    if question["kind"] == "tour":
        return list(answer["stops"])
    return [answer["from_space_id"], answer["to_space_id"]]


def _visits_in_order(path: list[str], stops: list[str]) -> bool:
    if path[0] != stops[0] or path[-1] != stops[-1]:
        return False
    position = 0
    for stop in stops[1:]:
        try:
            position = path.index(stop, position + 1)
        except ValueError:
            return False
    return True


def _model(bm: BuildingMap, closed: set[str], step_free: bool):
    model = geodesic.model_for(bm, step_free=step_free, closed=closed)
    model.geoms = bm.__dict__.setdefault("_shared_geoms", {})  # visibility graphs are costly, share them
    return model


def _first_invalid_step(model, path: list[str]) -> str | None:
    for first, second in itertools.pairwise(path):
        if first == second:
            return f"space {first} repeated"
        if not model.links(first, second):
            return f"no usable door, opening or connector between {first} and {second}"
    return None


def best_length(model, stops: list[str]) -> float | None:
    """Best length through the stops in order, door to door, including the walk across each stop's own space.

    One Dijkstra per stage: the doors of a stop space start with the cost to reach them from the previous stop."""
    if any(stop in model.closed for stop in stops):
        return None
    if len(set(stops)) == 1:
        return 0.0
    graph = model.build()
    reached: dict = {}  # node -> cost so far, restricted to the doors of the current stop
    for index, stop in enumerate(stops):
        members = [node for node, _ in model.members.get(stop, [])]
        if index == 0:
            reached = {node: 0.0 for node in members}
            continue
        if stop == stops[index - 1]:
            continue
        source = ("source", index)
        for node, cost in reached.items():
            graph.add_edge(source, node, weight=cost)
        if source not in graph:
            return None
        try:
            costs = nx.single_source_dijkstra_path_length(graph, source, weight="weight")
        finally:
            graph.remove_node(source)
        reached = {node: costs[node] for node in members if node in costs}
        if not reached:
            return None
    return min(reached.values()) if reached else None


def score_route(bm_before_closures: BuildingMap, route_entry: dict | None, question: dict) -> RouteScore:
    """Judge the agent's route entry (see structured.route_entry) for a route, step-free, closure or tour question."""
    answer = question["answer"]
    if _unreachable(answer):
        if route_entry is None:
            return RouteScore(True, 1.0, "correctly reported no route")
        return RouteScore(False, 0.0, "a route was given but none exists")
    if route_entry is None:
        return RouteScore(False, 0.0, "no route given")
    path = list(route_entry["space_path"])
    stops = _stops(question)
    closed = set(bm_before_closures.closed)
    if answer.get("closed_element_id"):
        closed.add(answer["closed_element_id"])
    step_free = question["kind"] == "route_step_free"
    if not path or any(space != OUTSIDE and space not in bm_before_closures.spaces for space in path):
        return RouteScore(False, 0.0, "unknown space in route")
    if not _visits_in_order(path, stops):
        return RouteScore(False, 0.0, "route does not start, end or visit the stops in order")
    if blocked := [space for space in path if space in closed]:
        return RouteScore(False, 0.0, f"route uses closed space {blocked[0]}")
    model = _model(bm_before_closures, closed, step_free)
    if problem := _first_invalid_step(model, path):
        return RouteScore(False, 0.0, problem)
    ours = model.measure(path)
    best = best_length(model, stops)
    if ours is None or best is None:
        return RouteScore(False, 0.0, "route cannot be measured")
    value = 1.0 if ours <= 1e-9 else min(1.0, best / ours)
    return RouteScore(True, value, f"best {best:.2f} m, route {ours:.2f} m")
