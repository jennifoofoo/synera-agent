"""Building-wide impact of a change: which rooms get cut off, lose step-free access or walk further.

Works on a copy of the map. Only `build_graph` knows how the building becomes a graph, so a new
routing model is a one-line change there."""

import itertools
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
SHOWN_ROOMS = 6
MAX_SENTENCES = 5


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
    lost_route: list[str] = field(default_factory=list)  # rooms with no way out of the building any more
    lost_step_free: list[str] = field(default_factory=list)  # had step-free access, lost it, still reachable by stairs
    gained_route: list[str] = field(default_factory=list)
    gained_step_free: list[str] = field(default_factory=list)
    other_lost_route: list[str] = field(default_factory=list)  # corridors, stairwells, lifts cut off
    other_lost_step_free: list[str] = field(default_factory=list)
    floors_cut_off: list[str] = field(default_factory=list)
    floors_cut_off_step_free: list[str] = field(default_factory=list)
    floors_regained: list[str] = field(default_factory=list)
    floors_regained_step_free: list[str] = field(default_factory=list)
    step_free_rooms_by_floor: dict[str, dict[str, int]] = field(default_factory=dict)  # floor id -> before/after
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
        out = self.route_sentences(subject) + self.step_free_sentences(subject)
        out += self.walk_sentences(None if out else subject)
        if not out:
            return [f"{subject} changes nothing for any room.", "No rooms are affected."]
        if len(out) == 1:
            out.append(
                "Every room still has a way out of the building."
                if not self.lost_route and not self.reopening
                else "No other room's walk to the entrance changes by more than 1 m."
            )
        return out[:MAX_SENTENCES]

    def route_sentences(self, subject: str) -> list[str]:
        if self.reopening:
            count = len(self.gained_route)
            if not count:
                return []
            floors = f", {join(self.floors_regained)} included" if self.floors_regained else ""
            return [f"{subject} brings {count} {plural(count, 'room')} back in reach{floors}."]
        count = len(self.lost_route)
        if not count and not self.other_lost_route:
            return []
        if not count:
            extra = len(self.other_lost_route)
            return [
                f"{subject} cuts off {extra} {'corridor or stairwell' if extra == 1 else 'corridors or stairwells'}, but no room loses its way out."
            ]
        floors = f"{join(self.floors_cut_off)} is completely cut off. " if self.floors_cut_off else ""
        text = (
            f"{subject} leaves {count} {plural(count, 'room')} with no way out of the building. "
            f"{floors}Affected: {self.some_rooms(self.lost_route)}."
        )
        return [text]

    def step_free_sentences(self, subject: str) -> list[str]:
        if self.reopening:
            count = len(self.gained_step_free)
            if not count:
                return []
            where = (
                f"{join(self.floors_regained_step_free)} is open to wheelchair users again: "
                if self.floors_regained_step_free
                else ""
            )
            return [f"{where}{count} {plural(count, 'room')} can be reached step-free again."]
        count = len(self.lost_step_free)
        if not count:
            return []
        if self.floors_cut_off_step_free:
            text = (
                f"{subject} cuts {join(self.floors_cut_off_step_free)} off for wheelchair users: "
                f"{count} {plural(count, 'room')} can no longer be reached step-free."
            )
            return [text]
        text = (
            f"{subject} means {count} {plural(count, 'room')} can no longer be reached step-free "
            f"({self.some_rooms(self.lost_step_free)})."
        )
        return [text]

    def walk_sentences(self, subject: str | None) -> list[str]:
        out = []
        for count, median, items, sign, noun in (
            (self.longer_count, self.longer_median_m, self.longer_worst, "+", "longer"),
            (self.shorter_count, self.shorter_median_m, self.shorter_best, "-", "shorter"),
        ):
            if not count:
                continue
            top = items[0]
            via = f" via {top.via}" if top.via else ""
            lead = f"{subject}: " if subject and not out else ""
            out.append(
                f"{lead}{count} {plural(count, 'room')} {'gets' if count == 1 else 'get'} a {noun} walk to the nearest entrance "
                f"(median {sign}{median:g} m), the {'worst' if noun == 'longer' else 'best'} is {top.name} "
                f"({sign}{abs(top.delta_m):g} m{via})."
            )
        return out

    def some_rooms(self, ids: list[str]) -> str:
        names = [self.room_names.get(room, room) for room in ids[:SHOWN_ROOMS]]
        more = len(ids) - len(names)
        return ", ".join(names) + (f" and {more} more" if more > 0 else "")


def plural(count: int, word: str) -> str:
    return word if count == 1 else word + "s"


def join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def copy_map(bm: BuildingMap) -> BuildingMap:
    """Own closed set, openings dict and openings list; everything else is only read."""
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


def describe_change(bm, closed_add, closed_remove, doors_add, doors_remove) -> str:
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


def distances(graph: nx.MultiGraph) -> dict[str, float]:
    if OUTSIDE not in graph:
        return {}
    return nx.single_source_dijkstra_path_length(graph, OUTSIDE, weight="weight")


def first_connector(bm: BuildingMap, graph: nx.MultiGraph, space_id: str) -> str | None:
    """Name of the first lift or staircase on the shortest way out of `space_id`."""
    try:
        path = nx.dijkstra_path(graph, space_id, OUTSIDE, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    for first, second in itertools.pairwise(path):
        edge = min(graph[first][second].values(), key=lambda candidate: candidate["weight"])
        if edge["via"] in bm.connectors:
            return bm.connectors[edge["via"]]["name"]
    return None


def cut_off_floors(bm: BuildingMap, before: dict, after: dict, skip: set[str]) -> list[str]:
    """Floors with at least one space reachable before and none reachable after."""
    names = []
    for floor in sorted(bm.floors.values(), key=lambda item: item["level"]):
        ids = [s for s, space in bm.spaces.items() if space["floor_id"] == floor["id"] and s not in skip]
        if any(s in before for s in ids) and not any(s in after for s in ids):
            names.append(floor["name"])
    return names


def median_delta(items: list[tuple[str, float, float]]) -> float:
    return round(statistics.median(abs(after - before) for _, before, after in items), 1) if items else 0.0


def validate(bm: BuildingMap, closed_add, closed_remove, doors_remove) -> None:
    for item in [*closed_add, *doors_remove]:
        if item in bm.closed:
            raise MapError(f"{label(bm, item)} is already closed.")
    for item in closed_remove:
        if item not in bm.closed:
            raise MapError(f"{label(bm, item)} is not closed, so it cannot be reopened.")
    for item in doors_remove:
        if item not in bm.openings:
            raise MapError(f"{item} is not a door or opening.")


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
    doors_add = [(bm.resolve_space(first), bm.resolve_space(second)) for first, second in doors_add]
    doors_remove = [bm.find_element(item) for item in doors_remove]
    validate(bm, closed_add, closed_remove, doors_remove)

    after_map = copy_map(bm)
    after_map.closed |= {*closed_add, *doors_remove}
    after_map.closed -= set(closed_remove)
    for first, second in doors_add:
        after_map.add_door(first, second)
    skip = {*closed_add, *closed_remove, *doors_remove}  # a closed room is not "cut off", it is closed

    report = ImpactReport(
        change=describe_change(bm, closed_add, closed_remove, doors_add, doors_remove),
        reopening=bool(closed_remove) and not (closed_add or doors_remove or doors_add),
    )
    old_any, new_any = build_graph(bm, False), build_graph(after_map, False)
    old_free, new_free = build_graph(bm, True), build_graph(after_map, True)
    before_any, after_any = distances(old_any), distances(new_any)
    before_free, after_free = distances(old_free), distances(new_free)

    for space_id, space in sorted(bm.spaces.items()):
        if space_id in skip:
            continue
        room = space["type"] == "room"
        report.room_names[space_id] = space["name"]
        lost_any = space_id in before_any and space_id not in after_any
        lost_free = space_id in before_free and space_id not in after_free
        if lost_any:
            (report.lost_route if room else report.other_lost_route).append(space_id)
        elif lost_free:
            (report.lost_step_free if room else report.other_lost_step_free).append(space_id)
        if room and space_id not in before_any and space_id in after_any:
            report.gained_route.append(space_id)
        if room and space_id not in before_free and space_id in after_free:
            report.gained_step_free.append(space_id)
        if room:
            counts = report.step_free_rooms_by_floor.setdefault(space["floor_id"], {"before": 0, "after": 0})
            counts["before"] += space_id in before_free
            counts["after"] += space_id in after_free

    report.floors_cut_off = cut_off_floors(bm, before_any, after_any, skip)
    report.floors_cut_off_step_free = cut_off_floors(bm, before_free, after_free, skip)
    report.floors_regained = cut_off_floors(bm, after_any, before_any, skip)
    report.floors_regained_step_free = cut_off_floors(bm, after_free, before_free, skip)

    changes = [
        (space_id, before_any[space_id], after_any[space_id])
        for space_id, space in sorted(bm.spaces.items())
        if space_id not in skip
        and space["type"] == "room"
        and space_id in before_any
        and space_id in after_any
        and abs(after_any[space_id] - before_any[space_id]) > MIN_CHANGE_M
    ]
    longer = sorted((c for c in changes if c[2] > c[1]), key=lambda c: (c[1] - c[2], c[0]))[:]
    shorter = sorted((c for c in changes if c[2] < c[1]), key=lambda c: (c[2] - c[1], c[0]))

    def room_change(entry: tuple[str, float, float]) -> RoomChange:
        space_id, before, after = entry
        return RoomChange(
            id=space_id,
            name=bm.spaces[space_id]["name"],
            before_m=round(before, 1),
            after_m=round(after, 1),
            delta_m=round(after - before, 1),
            via=first_connector(bm, new_any, space_id) if after > before else None,
        )

    report.longer_count, report.longer_median_m = len(longer), median_delta(longer)
    report.longer_worst = [room_change(entry) for entry in longer[:WORST_COUNT]]
    report.shorter_count, report.shorter_median_m = len(shorter), median_delta(shorter)
    report.shorter_best = [room_change(entry) for entry in shorter[:WORST_COUNT]]
    report.verdict = report.sentences()[0]
    return report


def make_impact_tools(bm: BuildingMap, state=None) -> list:
    @beta_tool
    def what_changes(element: str, action: str = "close") -> str:
        """What changes for the whole building if a lift, staircase, door or room is closed or reopened.
        Use this for questions like "the east lift is closed for maintenance, what changes?" or "what happens if
        Staircase 2 is blocked / opened again?". Nothing is changed: it only compares the building before and after.
        Reports rooms with no way out, rooms that lose step-free access, longer walks and cut-off floors.
        Read the `sentences` out; they are already in plain words.

        Args:
            element: Name or id of the lift, staircase, door or room, for example "Lift 1".
            action: "close" (closed, blocked, out of service) or "reopen" (open again).
        """
        if action not in ("close", "reopen"):
            raise ToolError('action must be "close" or "reopen".')
        try:
            args: dict[str, list[str]] = {"closed_add" if action == "close" else "closed_remove": [element]}
            return as_json(analyse(bm, **args).to_dict())
        except MapError as error:
            raise ToolError(str(error)) from error
        except (KeyError, ValueError, nx.NetworkXException) as error:
            raise ToolError(f"Cannot analyse '{element}': {error}") from error

    return [what_changes]
