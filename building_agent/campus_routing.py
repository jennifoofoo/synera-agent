"""Level 3, routes across buildings: one Dijkstra over (building, entrance) nodes on top of routing.py.

Inside a building the legs are routing.py's model (the kit's door-to-door model, which has no outside node). The
outside is never a free shortcut: legs of a campus route are computed on a view of each map with the space `outside`
closed, so a leg cannot leave the building and re-enter somewhere else. Buildings are only joined by links (cost
length_m) between two entrances.
A route inside one building is delegated to routing.route unchanged."""

import copy
import heapq
import itertools
import math
import re
from dataclasses import dataclass, field

from building_agent import routing
from building_agent.campus import Campus, Link, building_center, entrances
from building_agent.directions import turn_directions
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError, RouteResult

COMPASS = ("east", "north", "west", "south")
LINK_VERBS = {"walkway": "follow", "bridge": "cross", "tunnel": "take"}
MIN_OFFSET_M = 0.5
BRACKET = re.compile(r"\[([^\[\]]+)\]\s*$")


class AmbiguousReference(MapError):
    """A name that fits more than one place. `candidates` carry building names so the agent can ask."""

    def __init__(self, reference: str, candidates: list[dict]) -> None:
        self.candidates = candidates
        places = "; ".join(f"{item['name']} in {item['building']} ({item['floor']})" for item in candidates[:8])
        super().__init__(f"'{reference}' fits more than one place: {places}. Ask which one is meant.")


@dataclass
class CampusLeg:
    """One piece of a route: a walk inside one building (`route`) or a link between two entrances."""

    kind: str  # "building" or "link"
    length_m: float
    building_id: str = ""
    route: RouteResult | None = None
    entry_entrance: str | None = None  # building leg: entrance used to come in (None at the start)
    exit_entrance: str | None = None  # building leg: entrance used to leave (None at the end)
    end: str = "exit"  # building leg: "exit", "stop" or "destination"
    link: Link | None = None
    from_building: str = ""
    from_entrance: str = ""
    to_building: str = ""
    to_entrance: str = ""

    @property
    def id(self) -> str:
        return self.link.id if self.link else ""


@dataclass
class CampusRoute:
    space_path: list[str]
    buildings: list[str]
    legs: list[CampusLeg]
    length_m: float
    step_free: bool = False
    steps: list[str] = field(default_factory=list)
    maps: dict = field(default_factory=dict, repr=False, compare=False)
    names: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def links(self) -> list[Link]:
        return [leg.link for leg in self.legs if leg.link]


def _finite_positive(value) -> bool:
    return isinstance(value, int | float) and math.isfinite(value) and value > 0


def entrance_labels(bm: BuildingMap) -> dict[str, str]:
    """Spoken name per entrance id: 'main entrance' if alone, else the compass side (+y is north)."""
    found = entrances(bm)
    if len(found) == 1:
        return {found[0]["id"]: "main entrance"}
    cx, cy = building_center(bm)
    labels = {}
    for item in found:
        dx, dy = item["position"][0] - cx, item["position"][1] - cy
        side = COMPASS[round(math.atan2(dy, dx) / (math.pi / 2)) % 4] if math.hypot(dx, dy) > MIN_OFFSET_M else ""
        labels[item["id"]] = f"{side} entrance" if side else "entrance"
    counts = {label: list(labels.values()).count(label) for label in labels.values()}
    for item in found:
        if counts[labels[item["id"]]] > 1 and item["room"]:
            labels[item["id"]] += f" by {item['room']}"
    return labels


class CampusRouter:
    def __init__(self, campus: Campus, maps: dict[str, BuildingMap | None]) -> None:
        self.campus = campus
        self.maps = maps
        self._inner_maps: dict[str, tuple] = {}
        self._costs: dict[tuple, float | None] = {}

    # ---------- names and references ----------

    def building_name(self, building_id: str) -> str:
        bm = self.maps.get(building_id)
        name = bm.data.get("building", {}).get("name") if bm is not None else None
        return name or building_id

    def find_building(self, reference: str) -> str:
        wanted = str(reference).strip().lower()
        ids = [item.building_id for item in self.campus.buildings]
        for building_id in ids:
            if wanted in (building_id.lower(), self.building_name(building_id).lower()):
                return building_id
        close = [
            building_id
            for building_id in ids
            if wanted and (wanted in building_id.lower() or wanted in self.building_name(building_id).lower())
        ]
        if len(close) == 1:
            return close[0]
        if len(close) > 1:
            raise MapError(
                f"'{reference}' fits several buildings: {', '.join(self.building_name(item) for item in close)}."
            )
        known = ", ".join(self.building_name(item) for item in ids)
        raise MapError(f"No building matches '{reference}'. Buildings of this campus: {known}.")

    def _map(self, building_id: str) -> BuildingMap:
        bm = self.maps.get(building_id)
        if bm is None:
            raise MapError(
                f"The map of building {self.building_name(building_id)} is not loaded, so I cannot route in it."
            )
        return bm

    def _hits(self, building_id: str, reference: str) -> list[dict]:
        bm = self.maps.get(building_id)
        if bm is None:
            return []
        spaces: dict[str, None] = {}
        lowered = reference.strip().lower()
        if reference in bm.spaces:
            spaces[reference] = None
        elif reference in bm.assets:
            spaces[bm.assets[reference]["space_id"]] = None
        else:
            for space in bm.spaces.values():
                if lowered in ((space.get("ref") or "").lower(), space["name"].lower()):
                    spaces[space["id"]] = None
            for asset in bm.assets.values():
                if lowered == asset["name"].lower():
                    spaces[asset["space_id"]] = None
        return [
            {
                "building_id": building_id,
                "building": self.building_name(building_id),
                "space_id": space_id,
                "name": bm.spaces[space_id]["name"],
                "floor": bm.floor_name(bm.spaces[space_id]["floor_id"]),
            }
            for space_id in spaces
        ]

    def resolve(self, reference: str, building: str | None = None) -> tuple[str, str]:
        """(building_id, space_id) for an id or name. Raises AmbiguousReference with candidates if unclear."""
        reference = str(reference).strip()
        if not reference:
            raise MapError("A place is needed, but the name is empty.")
        if (bracketed := BRACKET.search(reference)) and any(
            bracketed.group(1) in bm.spaces for bm in self.maps.values() if bm
        ):
            reference = bracketed.group(1)
        if building:
            building_id = self.find_building(building)
            hits = self._hits(building_id, reference)
            if not hits:
                bm = self._map(building_id)
                try:
                    return building_id, bm.resolve_space(reference)
                except MapError as error:
                    raise MapError(f"{error} (in {self.building_name(building_id)})") from error
        else:
            hits = [hit for item in self.campus.buildings for hit in self._hits(item.building_id, reference)]
        if not hits:
            unloaded = [
                self.building_name(item.building_id)
                for item in self.campus.buildings
                if not self.maps.get(item.building_id)
            ]
            note = f" The map of {', '.join(unloaded)} is not loaded." if unloaded else ""
            raise MapError(f"No room matches '{reference}' in any building of this campus.{note}")
        if len(hits) > 1:
            raise AmbiguousReference(reference, hits)
        return hits[0]["building_id"], hits[0]["space_id"]

    def _stop(self, value) -> tuple[str, str]:
        if isinstance(value, tuple | list):
            return self.resolve(value[0], value[1])
        return self.resolve(value)

    # ---------- links and entrances ----------

    def _inner(self, building_id: str) -> BuildingMap:
        """The map with `outside` closed: legs cannot cross the outside for free."""
        bm = self._map(building_id)
        token = (id(bm), id(bm.openings), id(bm.spaces), id(bm.connectors), id(bm.floors))
        entry = self._inner_maps.get(building_id)
        if entry is None or entry[0] != token:
            entry = (token, copy.copy(bm))
            self._inner_maps[building_id] = entry
        entry[1].closed = set(bm.closed) | {OUTSIDE}
        return entry[1]

    def usable_entrances(self, building_id: str, step_free: bool) -> dict[str, str]:
        """entrance id -> room behind it, for entrances that are open (and step-free if asked)."""
        bm = self.maps.get(building_id)
        if bm is None:
            return {}
        return {
            item["id"]: item["space_id"]
            for item in entrances(bm)
            if item["space_id"]
            and item["id"] not in bm.closed
            and item["space_id"] not in bm.closed
            and (item["step_free"] or not step_free)
        }

    def link_usable(self, link: Link, step_free: bool, ignore_closed: bool = False) -> bool:
        if (link.closed and not ignore_closed) or (step_free and not link.step_free):
            return False
        if not _finite_positive(link.length_m) or link.from_building == link.to_building:
            return False
        for building_id, entrance in ((link.from_building, link.from_entrance), (link.to_building, link.to_entrance)):
            if entrance not in self.usable_entrances(building_id, step_free):
                return False
        return True

    def _leg_cost(self, building_id: str, first: str, second: str, step_free: bool) -> float | None:
        inner = self._inner(building_id)
        key = (building_id, routing.graph_signature(inner, step_free), first, second)
        if key not in self._costs:
            if len(self._costs) > 200_000:
                self._costs.clear()
            found = routing.shortest_leg(inner, routing.routing_graph(inner, step_free), first, second)
            self._costs[key] = None if found is None else found[0]
        return self._costs[key]

    # ---------- search ----------

    def _search(self, start: tuple[str, str], dest: tuple[str, str], step_free: bool, ignore_closed: bool = False):
        """Cheapest (length, [edge infos]) from start to dest across buildings, or None."""
        start_building, start_space = start
        dest_building, dest_space = dest
        free = {item.building_id: self.usable_entrances(item.building_id, step_free) for item in self.campus.buildings}
        adjacency: dict[tuple, list[tuple]] = {}
        for link in self.campus.links:
            if self.link_usable(link, step_free, ignore_closed):
                first, second = (link.from_building, link.from_entrance), (link.to_building, link.to_entrance)
                adjacency.setdefault(first, []).append((second, link))
                adjacency.setdefault(second, []).append((first, link))

        def neighbours(node):
            if node == "S":
                for entrance, space in free.get(start_building, {}).items():
                    cost = self._leg_cost(start_building, start_space, space, step_free)
                    if cost is not None:
                        yield (
                            (start_building, entrance),
                            cost,
                            ("leg", start_building, start_space, space, None, entrance),
                        )
                return
            building_id, entrance = node
            space = free[building_id][entrance]
            through = building_id not in (start_building, dest_building)  # crossing only pays off in between
            for other, other_space in free[building_id].items():
                if through and other != entrance:
                    cost = self._leg_cost(building_id, space, other_space, step_free)
                    if cost is not None:
                        yield (building_id, other), cost, ("leg", building_id, space, other_space, entrance, other)
            for target, link in adjacency.get(node, []):
                yield target, float(link.length_m), ("link", link, node, target)
            if building_id == dest_building:
                cost = self._leg_cost(building_id, space, dest_space, step_free)
                if cost is not None:
                    yield "D", cost, ("leg", building_id, space, dest_space, entrance, None)

        best = {"S": 0.0}
        previous: dict = {}
        counter = itertools.count()
        heap = [(0.0, next(counter), "S")]
        while heap:
            cost, _, node = heapq.heappop(heap)
            if cost > best.get(node, math.inf):
                continue
            if node == "D":
                break
            for target, weight, info in neighbours(node):
                if cost + weight < best.get(target, math.inf) - 1e-12:
                    best[target] = cost + weight
                    previous[target] = (node, info)
                    heapq.heappush(heap, (best[target], next(counter), target))
        if "D" not in best:
            return None
        infos = []
        node = "D"
        while node != "S":
            node, info = previous[node]
            infos.append(info)
        return best["D"], infos[::-1]

    def _explain(self, start: tuple[str, str], dest: tuple[str, str], step_free: bool) -> MapError:
        first, second = self.building_name(start[0]), self.building_name(dest[0])
        links = [link for link in self.campus.links if _finite_positive(link.length_m)]
        if dest[0] not in self._reachable(start[0], links):
            return MapError(f"There is no link between {first} and {second}: the buildings are not connected.")
        open_links = [link for link in links if not link.closed]
        if dest[0] not in self._reachable(start[0], open_links):
            closed = sorted({f"{link.kind} {link.id}" for link in links if link.closed})
            return MapError(f"The {' and the '.join(closed)} is closed, so {first} and {second} are cut off.")
        if step_free:
            ok = [link for link in open_links if self.link_usable(link, True)]
            if dest[0] not in self._reachable(start[0], ok):
                return MapError(
                    f"No step-free route from {first} to {second}: every link between them, or its entrance, has steps."
                )
        return MapError(
            f"No {'step-free ' if step_free else ''}route from {first} to {second} with the current closures."
        )

    def _reachable(self, building_id: str, links: list[Link]) -> set[str]:
        """Ids of the buildings reachable from building_id over these links (including itself)."""
        seen, todo = {building_id}, [building_id]
        while todo:
            current = todo.pop()
            for link in links:
                for here, there in ((link.from_building, link.to_building), (link.to_building, link.from_building)):
                    if here == current and there not in seen:
                        seen.add(there)
                        todo.append(there)
        return seen

    # ---------- public routing ----------

    def route(self, start, destination, step_free: bool = False, via: list | None = None) -> CampusRoute:
        """Shortest walk start -> via... -> destination. Each place is a reference string or (reference, building)."""
        stops = [self._stop(item) for item in [start, *(via or []), destination]]
        for building_id, _ in stops:
            self._map(building_id)
        if len({building_id for building_id, _ in stops}) == 1:
            return self._single_building(stops, step_free)
        legs: list[CampusLeg] = []
        runs = [(key, [space for _, space in group]) for key, group in itertools.groupby(stops, lambda s: s[0])]
        for index, (building_id, spaces) in enumerate(runs):
            if len(spaces) > 1:
                inner = self._inner(building_id)
                result = routing.route(inner, spaces[0], spaces[-1], step_free, spaces[1:-1])
                result.closed = sorted(self.maps[building_id].closed)
                legs.append(
                    self._building_leg(
                        building_id, result, None, None, "destination" if index + 1 == len(runs) else "stop"
                    )
                )
            if index + 1 < len(runs):
                next_building, next_spaces = runs[index + 1]
                found = self._search((building_id, spaces[-1]), (next_building, next_spaces[0]), step_free)
                if found is None:
                    raise self._explain((building_id, spaces[-1]), (next_building, next_spaces[0]), step_free)
                ends = "destination" if index + 2 == len(runs) and len(next_spaces) == 1 else "stop"
                legs += self._legs_from(found[1], step_free, ends)
        return self._assemble(legs, step_free)

    def _single_building(self, stops: list[tuple[str, str]], step_free: bool) -> CampusRoute:
        building_id = stops[0][0]
        result = routing.route(
            self.maps[building_id], stops[0][1], stops[-1][1], step_free, [space for _, space in stops[1:-1]]
        )
        leg = self._building_leg(building_id, result, None, None, "destination")
        return self._assemble([leg], step_free)

    def _building_leg(self, building_id, result, entry, exit_, end) -> CampusLeg:
        return CampusLeg("building", result.length_m, building_id, result, entry, exit_, end=end)

    def _legs_from(self, infos: list[tuple], step_free: bool, last_end: str) -> list[CampusLeg]:
        legs: list[CampusLeg] = []
        for index, info in enumerate(infos):
            if info[0] == "leg":
                _, building_id, first, second, entry, exit_ = info
                legs.append(self._inner_leg(building_id, first, second, entry, exit_, step_free, last_end))
                continue
            _, link, source, target = info
            if legs and legs[-1].kind == "link":  # two links meet at one entrance
                space = self.usable_entrances(source[0], step_free)[source[1]]
                legs.append(self._inner_leg(source[0], space, space, source[1], source[1], step_free, "exit"))
            legs.append(
                CampusLeg(
                    "link",
                    float(link.length_m),
                    link=link,
                    from_building=source[0],
                    from_entrance=source[1],
                    to_building=target[0],
                    to_entrance=target[1],
                )
            )
        return legs

    def _inner_leg(self, building_id, first, second, entry, exit_, step_free, last_end) -> CampusLeg:
        result = routing.route(self._inner(building_id), first, second, step_free)
        result.closed = sorted(self.maps[building_id].closed)
        return self._building_leg(building_id, result, entry, exit_, last_end if exit_ is None else "exit")

    def _assemble(self, legs: list[CampusLeg], step_free: bool) -> CampusRoute:
        spaces: list[str] = []
        buildings: list[str] = []
        for leg in legs:
            if leg.kind == "building":
                for space in leg.route.space_path:
                    if not spaces or spaces[-1] != space:
                        spaces.append(space)
                if leg.building_id not in buildings:
                    buildings.append(leg.building_id)
        route = CampusRoute(
            spaces,
            buildings,
            legs,
            round(sum(leg.length_m for leg in legs), 2),
            step_free,
            maps=self.maps,
            names={item: self.building_name(item) for item in buildings},
        )
        route.steps = campus_directions(route)
        return route

    # ---------- connectivity and effects ----------

    def components(self, links: list[Link] | None = None) -> list[set[str]]:
        """Groups of buildings joined by links that are not closed."""
        ids = [item.building_id for item in self.campus.buildings]
        parent = {item: item for item in ids}

        def find(item: str) -> str:
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        for link in self.campus.links if links is None else links:
            if link.closed or link.from_building not in parent or link.to_building not in parent:
                continue
            parent[find(link.from_building)] = find(link.to_building)
        groups: dict[str, set[str]] = {}
        for item in ids:
            groups.setdefault(find(item), set()).add(item)
        return list(groups.values())

    def connected_pairs(self, links: list[Link] | None = None) -> set[frozenset]:
        return {
            frozenset(pair) for group in self.components(links) for pair in itertools.combinations(sorted(group), 2)
        }

    def link_effect(self, link: Link, closed: bool) -> list[str]:
        """Plain sentences: which building pairs lose (or regain) their connection when `link` is closed (reopened)."""
        before = self.connected_pairs()
        changed = copy.copy(link)
        changed.closed = closed
        after = self.connected_pairs([changed if item.id == link.id else item for item in self.campus.links])
        label = f"{link.kind} {link.id}" + (f" ({link.name})" if link.name else "")
        verb = "closed" if closed else "reopened"
        lost, gained = (
            sorted(tuple(sorted(pair)) for pair in before - after),
            sorted(tuple(sorted(pair)) for pair in after - before),
        )
        pairs = lost if closed else gained
        if link.closed == closed:
            return [f"The {label} is already {verb}, so nothing changes."]
        if not pairs:
            if closed:
                return [
                    f"If the {label} is closed, no building loses its connection. Routes that used it take a detour."
                ]
            return [f"If the {label} is reopened, nothing new gets connected."]
        names = "; ".join(f"{self.building_name(a)} and {self.building_name(b)}" for a, b in pairs)
        what = "are no longer connected" if closed else "are connected again"
        return [f"If the {label} is {verb}, these buildings {what}: {names}."]


def entrance_text(route: CampusRoute, building_id: str, entrance: str) -> str:
    bm = route.maps[building_id]
    return entrance_labels(bm).get(entrance, "entrance")


def _link_phrase(link: Link) -> str:
    name = (link.name or link.kind).strip()
    if len(name) > 1 and name[1].islower():
        name = name[0].lower() + name[1:]
    return f"the {name}"


def campus_directions(route: CampusRoute) -> list[str]:
    """Spoken steps across buildings: turn directions inside each building, one step per building change."""
    steps: list[str] = []
    for index, leg in enumerate(route.legs):
        if leg.kind == "link":
            link = leg.link
            origin = route.names.get(leg.from_building) or leg.from_building
            target = route.names.get(leg.to_building) or leg.to_building
            leave = entrance_text(route, leg.from_building, leg.from_entrance)
            arrive = entrance_text(route, leg.to_building, leg.to_entrance)
            verb = LINK_VERBS.get(link.kind, "follow")
            steps.append(
                f"Leave {origin} through the {leave}, {verb} {_link_phrase(link)} ({leg.length_m:.0f} m) "
                f"and enter {target} through its {arrive}."
            )
            continue
        bm = route.maps[leg.building_id]
        path = leg.route.space_path
        if len(path) < 2:
            if leg.end in ("stop", "destination") and (index > 0 or leg.end == "destination"):
                steps.append(f"You have arrived at {bm.describe_space(path[0])}.")
            continue
        own = turn_directions(bm, leg.route)
        if leg.end == "exit" and own and own[-1].startswith("You have arrived"):
            own = own[:-1]
        steps += own
    return steps
