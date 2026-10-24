"""Score a route the way Synera announced it: validity first, then best length / our length under their rule.

Rules checked: every step of the ordered space list goes through a real door, opening, stair or lift that is
open (and step-free if asked), tours visit the stops in order, closures hold. The agent's own length numbers are
ignored: the sequence is measured with the kit's route model (README section 3: door to door, 15 cm clearance,
stairs 2 m per metre, lift 15 m per ride plus 1 m per metre, no way round the outside), the same model that
computed the labelled answers. Score = best possible length / measured length, capped at 1. An invalid route
scores 0. If no route exists the only correct answer is to report none.

The best length is the labelled `optimal_length_m` when the question carries one, else the shortest legs on the
same graph (a tour is the sum of its legs, each routed on its own)."""

import copy
import itertools
import math
from dataclasses import dataclass

from building_agent import routing
from starter_agent.building_map import DOOR_PREFIX, BuildingMap

FULL_MARKS = 0.99
ROUTE_KINDS = ("route", "route_step_free", "route_with_closure", "tour")
LABEL_TOLERANCE_M = 0.05  # the label is rounded to 2 decimals; a recomputed best may differ by rounding of legs


@dataclass(frozen=True)
class RouteScore:
    valid: bool
    score: float
    reason: str = ""


class RouteModel:
    """The kit graph of one building under given closures and step-free flag, with the judge's measures."""

    def __init__(self, bm: BuildingMap, closed: set[str], step_free: bool) -> None:
        self.bm = bm
        self.closed = set(closed)
        self.step_free = step_free
        view = copy.copy(bm)  # shares the walking lengths, so they are computed once per building
        view.closed = set(closed)
        self.view = view
        self.graph = routing.routing_graph(view, step_free).graph

    def walk(self, space: str, first: str, second: str) -> float | None:
        """Walking length between two nodes of one space (the space itself or one of its doors)."""
        if first == second:
            return 0.0
        if not self.graph.has_edge(first, second):
            return None
        lengths = [edge["weight"] for edge in self.graph[first][second].values() if edge.get("space") == space]
        return min(lengths, default=None)

    def doors_between(self, first: str, second: str) -> list[str]:
        return [
            DOOR_PREFIX + opening["id"]
            for opening in self.bm.openings.values()
            if set(opening["space_ids"]) == {first, second} and (DOOR_PREFIX + opening["id"]) in self.graph
        ]

    def connector_costs(self, first: str, second: str) -> list[float]:
        if not self.graph.has_edge(first, second):
            return []
        return [edge["weight"] for edge in self.graph[first][second].values() if "via" in edge]

    def links(self, first: str, second: str) -> bool:
        """Is there an open, usable door, opening, stair or lift between two spaces?"""
        if first not in self.graph or second not in self.graph:
            return False
        return bool(self.doors_between(first, second) or self.connector_costs(first, second))

    def measure(self, path: list[str], stops: list[str] | None = None) -> float | None:
        """Length of the space sequence, or None if a step has no usable link or the stops are not visited in order.

        The route is a walk from the centre of the first space to the centre of the last, and to the centre of every
        stop in between; elsewhere it crosses spaces door to door. Of several doors between two spaces the best one
        counts, and a stop that is also passed earlier on the path is visited at the best occurrence."""
        stops = stops or [path[0], path[-1]]
        if not path or path[0] != stops[0] or path[-1] != stops[-1] or any(s not in self.graph for s in path):
            return None
        if any(first == second for first, second in itertools.pairwise(path)):
            return None
        wanted = len(stops)
        states: dict[tuple[str, int], float] = {(path[0], 1): 0.0}
        for index, space in enumerate(path):
            states = self._visit(states, space, stops, wanted)
            if index + 1 == len(path):
                break
            following = path[index + 1]
            moved: dict[tuple[str, int], float] = {}
            for (node, visited), cost in states.items():
                for door in self.doors_between(space, following):
                    walked = self.walk(space, node, door)
                    if walked is not None:
                        key = (door, visited)
                        moved[key] = min(moved.get(key, math.inf), cost + walked)
                for ride in self.connector_costs(space, following):
                    walked = self.walk(space, node, space)
                    if walked is not None:
                        key = (following, visited)
                        moved[key] = min(moved.get(key, math.inf), cost + walked + ride)
            states = moved
            if not states:
                return None
        finals = []
        for (node, visited), cost in states.items():
            walked = self.walk(path[-1], node, path[-1]) if visited == wanted else None
            if walked is not None:
                finals.append(cost + walked)
        return min(finals) if finals else None

    def _visit(self, states: dict, space: str, stops: list[str], wanted: int) -> dict:
        """Add the option to visit the next stop here: walk to the centre of the space, count the stop."""
        states = dict(states)
        for _ in range(wanted):
            grown = False
            for (node, visited), cost in list(states.items()):
                if visited < wanted and stops[visited] == space:
                    walked = self.walk(space, node, space)
                    if walked is not None and cost + walked < states.get((space, visited + 1), math.inf):
                        states[(space, visited + 1)] = cost + walked
                        grown = True
            if not grown:
                break
        return states

    def best(self, stops: list[str]) -> float | None:
        """Best length through the stops in order: the sum of the shortest legs, or None if a leg has no route."""
        if any(stop in self.closed for stop in stops):
            return None
        total = 0.0
        rg = routing.routing_graph(self.view, self.step_free)
        for first, second in itertools.pairwise(stops):
            found = routing.shortest_leg(self.view, rg, first, second)
            if found is None:
                return None
            total += found[0]
        return total


def _unreachable(answer: dict) -> bool:
    legs = answer.get("legs") or []
    return answer.get("reachable") is False or any(leg.get("reachable") is False for leg in legs)


def _stops(question: dict) -> list[str]:
    answer = question["answer"]
    if question["kind"] == "tour":
        return list(answer["stops"])
    return [answer["from_space_id"], answer["to_space_id"]]


def _model(bm: BuildingMap, closed: set[str], step_free: bool) -> RouteModel:
    return RouteModel(bm, closed, step_free)


def _first_invalid_step(model: RouteModel, path: list[str]) -> str | None:
    for first, second in itertools.pairwise(path):
        if first == second:
            return f"space {first} repeated"
        if not model.links(first, second):
            return f"no usable door, opening, stair or lift between {first} and {second}"
    return None


def best_length(model: RouteModel, stops: list[str]) -> float | None:
    """Best length through the stops in order (see RouteModel.best)."""
    return model.best(stops)


def _visits_in_order(path: list[str], stops: list[str]) -> bool:
    if path[0] != stops[0] or path[-1] != stops[-1]:
        return False
    position = 0
    for previous, stop in itertools.pairwise(stops):
        if stop == previous:  # a repeated stop is visited once, where the walk already is
            continue
        try:
            position = path.index(stop, position + 1)
        except ValueError:
            return False
    return True


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
    if not path or any(space not in bm_before_closures.spaces for space in path):
        return RouteScore(False, 0.0, "unknown space in route")
    if not _visits_in_order(path, stops):
        return RouteScore(False, 0.0, "route does not start, end or visit the stops in order")
    if blocked := [space for space in path if space in closed]:
        return RouteScore(False, 0.0, f"route uses closed space {blocked[0]}")
    model = _model(bm_before_closures, closed, step_free)
    if problem := _first_invalid_step(model, path):
        return RouteScore(False, 0.0, problem)
    ours = model.measure(path, stops)
    best = answer.get("optimal_length_m")
    if best is None:
        best = best_length(model, stops)
    if ours is None or best is None:
        return RouteScore(False, 0.0, "route cannot be measured")
    value = 1.0 if ours <= 1e-9 else min(1.0, best / ours)
    return RouteScore(True, value, f"best {best:.2f} m, route {ours:.2f} m")
