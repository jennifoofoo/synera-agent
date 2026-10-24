"""Building-wide impact of a change: which rooms get cut off, lose step-free access or walk further.

Works on a copy of the map and only uses BuildingMap.graph, so a new routing model needs one change: build_graph."""

import statistics
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

import networkx as nx
from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from starter_agent.building_map import OUTSIDE, BuildingMap, MapError
from starter_agent.tools import as_json

MIN_CHANGE_M = 1.0
WORST_COUNT = 5
SHOWN_ROOMS = 8


def build_graph(bm: BuildingMap, step_free: bool) -> nx.MultiGraph:
    return bm.graph(step_free)


@dataclass
class RoomChange:
    id: str
    name: str
    before_m: float
    after_m: float
    delta_m: float
    via: str | None = None


@dataclass
class ImpactReport:
    change: str
    reopening: bool = False
    lost_route: list[str] = field(default_factory=list)  # rooms with no way out any more
    lost_step_free: list[str] = field(default_factory=list)  # rooms that had step-free access and lost it
    gained_route: list[str] = field(default_factory=list)
    gained_step_free: list[str] = field(default_factory=list)
    other_lost_route: list[str] = field(default_factory=list)  # corridors, stairwells, lifts
    other_lost_step_free: list[str] = field(default_factory=list)
    floors_cut_off: list[str] = field(default_factory=list)
    floors_cut_off_step_free: list[str] = field(default_factory=list)
    floors_regained: list[str] = field(default_factory=list)
    floors_regained_step_free: list[str] = field(default_factory=list)
    longer_count: int = 0
    longer_median_m: float = 0.0
    longer_worst: list[RoomChange] = field(default_factory=list)
    shorter_count: int = 0
    shorter_median_m: float = 0.0
    shorter_best: list[RoomChange] = field(default_factory=list)
    room_names: dict[str, str] = field(default_factory=dict)
    verdict: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["sentences"] = self.sentences()
        return data

    def sentences(self) -> list[str]:
        subject = self.change[0].upper() + self.change[1:]
        out = []
        out += self.access_sentences(subject, self.lost_route, self.floors_cut_off, "loses every route out of")
        out += self.step_free_sentences(subject)
        out += self.walk_sentences(subject)
        if not out:
            return [f"{subject} changes nothing for the rooms.", "No rooms are affected."]
        return out[:5]

    def access_sentences(self, subject: str, rooms: list[str], floors: list[str], _verb: str) -> list[str]:
        if self.reopening:
            if not self.gained_route:
                return []
            lead = f"{subject} brings {len(self.gained_route)} {plural(len(self.gained_route), 'room')} back in reach"
            return [lead + self.floor_tail(self.floors_regained, "all of") + "."]
        if not rooms and not self.other_lost_route:
            return []
        parts = f"{subject} leaves {len(rooms)} {plural(len(rooms), 'room')} with no way out of the building"
        if floors:
            parts += f", {join(floors)} {'is' if len(floors) == 1 else 'are'} completely cut off"
        if rooms:
            parts += f" ({self.some_rooms(rooms)})"
        elif self.other_lost_route:
            parts += f" ({len(self.other_lost_route)} corridors or stairwells are cut off too)"
        return [parts + "."]

    def step_free_sentences(self, subject: str) -> list[str]:
        if self.reopening:
            if not self.gained_step_free:
                return []
            count = len(self.gained_step_free)
            floors = self.floors_regained_step_free
            where = f"{join(floors)} is reachable for wheelchair users again: " if floors else ""
            return [f"{where}{count} {plural(count, 'room')} can be reached step-free again.".capitalize_first()]
        if not self.lost_step_free:
            return []
        count = len(self.lost_step_free)
        floors = self.floors_cut_off_step_free
        if floors:
            return [
                f"{subject} cuts {join(floors)} off for wheelchair users: "
                f"{count} {plural(count, 'room')} can no longer be reached step-free."
            ]
        return [
            f"{subject} means {count} {plural(count, 'room')} can no longer be reached step-free "
            f"({self.some_rooms(self.lost_step_free)})."
        ]

    def walk_sentences(self, subject: str) -> list[str]:
        out = []
        if self.longer_count:
            worst = self.longer_worst[0]
            out.append(
                f"{self.longer_count} {plural(self.longer_count, 'room')} get a longer walk to the nearest "
                f"entrance (median +{self.longer_median_m:g} m), the worst is {worst.name} "
                f"(+{worst.delta_m:g} m{f' via {worst.via}' if worst.via else ''})."
            )
        if self.shorter_count:
            best = self.shorter_best[0]
            out.append(
                f"{self.shorter_count} {plural(self.shorter_count, 'room')} get a shorter walk to the nearest "
                f"entrance (median -{self.shorter_median_m:g} m), the best is {best.name} "
                f"(-{abs(best.delta_m):g} m{f' via {best.via}' if best.via else ''})."
            )
        return out

    def floor_tail(self, floors: list[str], _prefix: str) -> str:
        return f", {join(floors)} included" if floors else ""

    def some_rooms(self, ids: list[str]) -> str:
        names = [self.room_names.get(room, room) for room in ids[:SHOWN_ROOMS]]
        more = len(ids) - len(names)
        return ", ".join(names) + (f" and {more} more" if more > 0 else "")


def plural(count: int, word: str) -> str:
    return word if count == 1 else word + "s"


def join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def copy_map(bm: BuildingMap) -> BuildingMap:
    """Own closed set, openings dict and openings list; spaces and connectors are only read."""
    clone = object.__new__(BuildingMap)
    clone.__dict__.update(bm.__dict__)
    clone.data = {**bm.data, "openings": list(bm.data["openings"])}
    clone.openings = dict(bm.openings)
    clone.closed = set(bm.closed)
    clone.last_route = None
    clone.located_asset_ids = []
    return clone


def label(bm: BuildingMap, element: str) -> str:
    if element in bm.connectors:
        return bm.connectors[element]["name"]
    if element in bm.spaces:
        return bm.spaces[element]["name"]
    return element


def distances(graph: nx.MultiGraph) -> dict[str, float]:
    if OUTSIDE not in graph:
        return {}
    return nx.single_source_dijkstra_path_length(graph, OUTSIDE, weight="weight")


def connector_via(bm: BuildingMap, graph: nx.MultiGraph, space_id: str, avoid: set[str]) -> str | None:
    """Name of the first lift or staircase on the shortest way out that the old route did not use."""
    try:
        path = nx.dijkstra_path(graph, OUTSIDE, space_id, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    used = []
    for first, second in zip(path, path[1:], strict=False):
        edge = min(graph[first][second].values(), key=lambda candidate: candidate["weight"])
        if edge["via"] in bm.connectors:
            used.append(edge["via"])
    fresh = [item for item in used if item not in avoid] or used
    return label(bm, fresh[0]) if fresh else None


def route_connectors(bm: BuildingMap, graph: nx.MultiGraph, space_id: str) -> set[str]:
    return {item for item in connectors_on_path(bm, graph, space_id)}


def connectors_on_path(bm: BuildingMap, graph: nx.MultiGraph, space_id: str) -> list[str]:
    try:
        path = nx.dijkstra_path(graph, OUTSIDE, space_id, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []
    found = []
    for first, second in zip(path, path[1:], strict=False):
        edge = min(graph[first][second].values(), key=lambda candidate: candidate["weight"])
        if edge["via"] in bm.connectors:
            found.append(edge["via"])
    return found


def describe_change(bm: BuildingMap, closed_add, closed_remove, doors_add, doors_remove) -> str:
    parts = []
    if closed_add:
        parts.append("closing " + join([label(bm, item) for item in closed_add]))
    if closed_remove:
        parts.append("reopening " + join([label(bm, item) for item in closed_remove]))
    for first, second in doors_add:
        parts.append(f"adding a door between {label(bm, first)} and {label(bm, second)}")
    if doors_remove:
        parts.append("removing " + join([label(bm, item) for item in doors_remove]))
    return " and ".join(parts) if parts else "no change"


def is_room(bm: BuildingMap, space_id: str) -> bool:
    return bm.spaces[space_id]["type"] == "room"


def analyse(
    bm: BuildingMap,
    closed_add: Iterable[str] = (),
    closed_remove: Iterable[str] = (),
    doors_add: Iterable[tuple[str, str]] = (),
    doors_remove: Iterable[str] = (),
) -> ImpactReport:
    """Compare the building as it is with the building after the change. Never touches `bm`."""
    closed_add = [bm.find_element(item) for item in closed_add]
    closed_remove = [bm.find_element(item) for item in closed_remove]
    doors_add = [(bm.resolve_space(a), bm.resolve_space(b)) for a, b in doors_add]
    doors_remove = [bm.find_element(item) for item in doors_remove]
    for item in closed_add + doors_remove:
        if item in bm.closed:
            raise MapError(f"{label(bm, item)} is already closed.")
    for item in closed_remove:
        if item not in bm.closed:
            raise MapError(f"{label(bm, item)} is not closed, so it cannot be reopened.")
    for item in doors_remove:
        if item not in bm.openings:
            raise MapError(f"{item} is not a door or opening.")

    after_map = copy_map(bm)
    after_map.closed |= set(closed_add) | set(doors_remove)
    after_map.closed -= set(closed_remove)
    for first, second in doors_add:
        after_map.add_door(first, second)
    changed = set(closed_add) | set(closed_remove)

    report = ImpactReport(
        change=describe_change(bm, closed_add, closed_remove, doors_add, doors_remove),
        reopening=bool(closed_remove) and not (closed_add or doors_remove),
    )
    graphs = {}
    for step_free in (False, True):
        graphs[step_free] = (build_graph(bm, step_free), build_graph(after_map, step_free))
    before_any, after_any = (distances(graph) for graph in graphs[False])
    before_free, after_free = (distances(graph) for graph in graphs[True])

    def in_scope(space_id: str) -> bool:
        return space_id in bm.spaces and space_id not in changed

    for space_id in sorted(bm.spaces):
        if not in_scope(space_id):
            continue
        room = is_room(bm, space_id)
        report.room_names[space_id] = bm.spaces[space_id]["name"]
        if space_id in before_any and space_id not in after_any:
            (report.lost_route if room else report.other_lost_route).append(space_id)
        if space_id not in before_any and space_id in after_any:
            report.gained_route.append(space_id) if room else None
        if space_id in before_free and space_id not in after_free:
            (report.lost_step_free if room else report.other_lost_step_free).append(space_id)
        if space_id not in before_free and space_id in after_free and room:
            report.gained_step_free.append(space_id)
    report.floors_cut_off = floors_where(bm, in_scope, before_any, after_any, lost=True)
    report.floors_cut_off_step_free = floors_where(bm, in_scope, before_free, after_free, lost=True)
    report.floors_regained = floors_where(bm, in_scope, after_any, before_any, lost=True)
    report.floors_regained_step_free = floors_where(bm, in_scope, after_free, before_free, lost=True)

    changes = [
        (space_id, before_any[space_id], after_any[space_id])
        for space_id in sorted(bm.spaces)
        if in_scope(space_id)
        and is_room(bm, space_id)
        and space_id in before_any
        and space_id in after_any
        and abs(after_any[space_id] - before_any[space_id]) > MIN_CHANGE_M
    ]
    longer = sorted((c for c in changes if c[2] > c[1]), key=lambda c: (c[1] - c[2], c[0]))
    shorter = sorted((c for c in changes if c[2] < c[1]), key=lambda c: (c[2] - c[1], c[0]))
    report.longer_count = len(longer)
    report.longer_median_m = median_delta(longer)
    report.longer_worst = [room_change(bm, graphs[False], c) for c in longer[:WORST_COUNT]]
    report.shorter_count = len(shorter)
    report.shorter_median_m = median_delta(shorter)
    report.shorter_best = [room_change(bm, graphs[False], c) for c in shorter[:WORST_COUNT]]
    report.verdict = report.sentences()[0]
    return report


def floors_where(bm: BuildingMap, in_scope, before: dict, after: dict, lost: bool) -> list[str]:
    """Floors that had at least one reachable space in `before` and none in `after`."""
    names = []
    for floor in sorted(bm.floors.values(), key=lambda item: item["level"]):
        ids = [s for s, space in bm.spaces.items() if space["floor_id"] == floor["id"] and in_scope(s)]
        if any(s in before for s in ids) and not any(s in after for s in ids):
            names.append(floor["name"])
    return names


def median_delta(items: list[tuple[str, float, float]]) -> float:
    return round(statistics.median(abs(after - before) for _, before, after in items), 1) if items else 0.0


def room_change(bm: BuildingMap, graphs: tuple, entry: tuple[str, float, float]) -> RoomChange:
    space_id, before, after = entry
    old_graph, new_graph = graphs
    old_used = set(connectors_on_path(bm, old_graph, space_id))
    via = connector_via(bm, new_graph, space_id, old_used)
    return RoomChange(
        id=space_id,
        name=bm.spaces[space_id]["name"],
        before_m=round(before, 1),
        after_m=round(after, 1),
        delta_m=round(after - before, 1),
        via=via,
    )


def make_impact_tools(bm: BuildingMap, state=None) -> list:
    @beta_tool
    def what_changes(element: str, action: str = "close") -> str:
        """What changes for the whole building if a lift, staircase, door or room is closed or reopened.
        Use this for questions like "the east lift is closed for maintenance, what changes?" or "what happens if
        Staircase 2 is blocked / reopened?". Nothing is changed: it only compares the building before and after.
        Reports rooms with no way out, rooms that lose step-free access, longer walks and cut-off floors.
        Read the `sentences` out; they are already in plain words.

        Args:
            element: Name or id of the lift, staircase, door or room, for example "Lift 1".
            action: "close" (closed, blocked, out of service) or "reopen" (open again).
        """
        if action not in ("close", "reopen"):
            raise ToolError('action must be "close" or "reopen".')
        try:
            report = analyse(bm, closed_add=[element]) if action == "close" else analyse(bm, closed_remove=[element])
        except MapError as error:
            raise ToolError(str(error)) from error
        return as_json(report.to_dict())

    return [what_changes]
