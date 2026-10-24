"""JSON views of a BuildingMap for the 2D page. Pure functions, no HTTP, so tests can call them directly.

Every number the page shows comes from starter_agent.building_map (same route model as the benchmark)."""

import csv
import itertools
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
from shapely.geometry import Polygon

from starter_agent.building_map import DOOR_PREFIX, OUTSIDE, BuildingMap, MapError

COORD_DIGITS = 2


class RecordingMap(BuildingMap):
    """A BuildingMap that also remembers the arguments of its last route, so the page can redraw the chat
    agent's route with its via stops (RouteResult does not keep them). Survives deepcopy like any attribute."""

    last_route_request: dict | None = None

    def route(self, start: str, destination: str, step_free: bool = False, via: list[str] | None = None):
        result = super().route(start, destination, step_free, via)
        self.last_route_request = {
            "start": start,
            "destination": destination,
            "step_free": step_free,
            "via": [str(stop) for stop in via or [] if stop],
            "result": result,
        }
        return result


@dataclass
class Session:
    """One loaded building plus what the page needs to remember about it."""

    key: str
    directory: Path
    map: BuildingMap
    route_request: dict | None = None
    route_version: int = 0  # bumped by every route the page asks for or clears; newer page routes win
    original_opening_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.original_opening_ids = set(self.map.openings)

    @property
    def added_door_ids(self) -> list[str]:
        """Doors added on the page or by the chat agent (both edit the same BuildingMap)."""
        return [opening_id for opening_id in self.map.openings if opening_id not in self.original_opening_ids]

    def adopt_agent_route(self, previous_route: object, version_before_chat: int) -> bool:
        """If the chat agent routed, show its route on the map, with its via stops when the map recorded them.
        A route the page asked for while the agent was thinking is newer and stays. Returns whether it adopted."""
        route = self.map.last_route
        if route is None or route is previous_route or self.route_version != version_before_chat:
            return False
        recorded = getattr(self.map, "last_route_request", None)
        via = recorded["via"] if recorded and recorded.get("result") is route else []
        self.route_request = {
            "start": route.start_space_id,
            "destination": route.destination_space_id,
            "step_free": route.step_free,
            "via": via,
        }
        self.route_version += 1
        return True


# ---------- building list ----------


def list_buildings(data_root: Path) -> list[dict]:
    """Every directory under data_root that holds a building.json, as {key, name, split, source, floors}."""
    manifest: dict[str, dict] = {}
    manifest_file = data_root / "manifest.csv"
    if manifest_file.exists():
        with manifest_file.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                manifest[row.get("path") or ""] = row
    found = []
    for building_file in sorted(data_root.rglob("building.json")):
        key = building_file.parent.relative_to(data_root).as_posix()
        row = manifest.get(key, {})
        found.append(
            {
                "key": key,
                "name": row.get("name") or building_file.parent.name,
                "split": key.split("/")[0] if "/" in key else "",
                "source": row.get("source", ""),
                "floors": int(row["floors"]) if row.get("floors", "").isdigit() else None,
            }
        )
    return found


def resolve_building_dir(data_root: Path, key: str) -> Path:
    """Map a page key like 'dev/proc-campus-dev-000' to a directory, refusing anything outside data_root."""
    root = data_root.resolve()
    directory = (data_root / key).resolve()
    if root not in directory.parents and directory != root:
        raise MapError(f"Unknown building '{key}'.")
    if not (directory / "building.json").exists():
        raise MapError(f"Unknown building '{key}'.")
    return directory


# ---------- building geometry ----------


def rounded(point: list[float] | tuple[float, float]) -> list[float]:
    return [round(point[0], COORD_DIGITS), round(point[1], COORD_DIGITS)]


def building_view(session: Session) -> dict:
    """Everything the page draws: floors, spaces with polygons and label points, openings, connectors, assets."""
    bm = session.map
    floors = sorted(bm.floors.values(), key=lambda floor: floor["level"])
    spaces = []
    for space in bm.spaces.values():
        polygon = Polygon(space["polygon"])
        spaces.append(
            {
                "id": space["id"],
                "floor_id": space["floor_id"],
                "type": space["type"],
                "room_type": space["room_type"],
                "name": space["name"],
                "ref": space.get("ref"),
                "polygon": [rounded(point) for point in space["polygon"]],
                "anchor": rounded(bm.anchor(space["id"])),
                "area_m2": round(polygon.area, 1),
            }
        )
    openings = [
        {
            "id": opening["id"],
            "floor_id": opening["floor_id"],
            "space_ids": opening["space_ids"],
            "kind": opening["kind"],
            "position": rounded(opening["position"]),
            "width_m": opening.get("width_m"),
            "step_free": opening["step_free"],
            "added": opening["id"] in session.added_door_ids,
        }
        for opening in bm.openings.values()
    ]
    connectors = [
        {
            "id": connector["id"],
            "kind": connector["kind"],
            "name": connector["name"],
            "floor_ids": connector["floor_ids"],
            "space_ids": connector["space_ids"],
            "step_free": connector["step_free"],
        }
        for connector in bm.connectors.values()
    ]
    assets = [
        {
            "id": asset["id"],
            "name": asset["name"],
            "type": asset["type"],
            "category": asset.get("category"),
            "space_id": asset["space_id"],
            "floor_id": asset["floor_id"],
            "position": rounded(asset["position"]),
        }
        for asset in bm.assets.values()
        if asset.get("position")
    ]
    info = bm.data["building"]
    return {
        "key": session.key,
        "name": info["name"],
        "source": info.get("source"),
        "floors": [{"id": floor["id"], "level": floor["level"], "name": floor["name"]} for floor in floors],
        "spaces": spaces,
        "openings": openings,
        "connectors": connectors,
        "assets": assets,
        "state": state_view(session),
    }


def state_view(session: Session) -> dict:
    """The mutable part: closures, added doors and the current route (recomputed against the closures)."""
    bm = session.map
    return {
        "closed": sorted(bm.closed),
        "added_doors": [opening_summary(bm, opening_id) for opening_id in session.added_door_ids],
        "route": current_route(session),
        **edit_state(bm),
    }


def edit_state(bm: BuildingMap) -> dict:
    """Asset and door edits since loading; only keys with content are present. Positions: model metres, +y north.

    added_assets   {id: {space_id, floor_id, position, name, rotation_deg, type, category}} (latest position)
    moved_assets   {id: {space_id, floor_id, position, name, rotation_deg}} (also restored values after undo)
    removed_assets [ids] that no longer exist (an added asset after undo)
    removed_openings [ids], widened_openings {id: width_m}"""
    moved = {
        key: {**item, "position": rounded(item["position"])} for key, item in getattr(bm, "moved_assets", {}).items()
    }
    added = {}
    for key, item in getattr(bm, "added_assets", {}).items():
        added[key] = {**item, **moved.get(key, {}), "position": rounded(moved.get(key, item)["position"])}
    found = {
        "added_assets": added,
        "moved_assets": {key: item for key, item in moved.items() if key not in added},
        "removed_assets": [str(item) for item in getattr(bm, "removed_assets", [])],
        "removed_openings": [str(item) for item in getattr(bm, "removed_openings", [])],
        "widened_openings": {str(key): float(width) for key, width in getattr(bm, "widened_openings", {}).items()},
    }
    return {key: value for key, value in found.items() if value}


def opening_summary(bm: BuildingMap, opening_id: str) -> dict:
    opening = bm.openings[opening_id]
    return {
        "id": opening_id,
        "floor_id": opening["floor_id"],
        "space_ids": opening["space_ids"],
        "position": rounded(opening["position"]),
        "step_free": opening["step_free"],
    }


# ---------- routing ----------


def route_view(session: Session, start: str, destination: str, step_free: bool = False, via=None) -> dict:
    """A route the page asks for: remembered (newest wins over the chat agent's), then drawn."""
    via = [stop for stop in via or [] if stop]
    # Remember the request even if it fails, so the page shows "no route" instead of a stale line.
    session.route_request = {"start": start, "destination": destination, "step_free": step_free, "via": via}
    session.route_version += 1
    return draw_route(session, start, destination, step_free, via)


def draw_route(session: Session, start: str, destination: str, step_free: bool, via: list[str]) -> dict:
    """Shortest route plus per-floor polylines (room anchor -> door -> room anchor) and floor changes.
    Leaves map.last_route alone: that slot belongs to the chat agent, so redrawing never looks like a new agent route."""
    bm = session.map
    kept_route, kept_request = bm.last_route, getattr(bm, "last_route_request", None)
    try:
        result = bm.route(start, destination, step_free=step_free, via=via)
    finally:
        bm.last_route = kept_route
        if isinstance(bm, RecordingMap):
            bm.last_route_request = kept_request
    stops = [result.start_space_id, *[bm.resolve_space(stop) for stop in via], result.destination_space_id]
    nodes = route_nodes(bm, stops, step_free)
    geometry = route_geometry(bm, nodes, step_free)
    return {
        "ok": True,
        "start": result.start_space_id,
        "destination": result.destination_space_id,
        "via": [bm.resolve_space(stop) for stop in via],
        "step_free": step_free,
        "length_m": result.length_m,
        "space_path": result.space_path,
        "steps": compact_steps(result.steps),
        **geometry,
        "floors": list(dict.fromkeys(segment["floor_id"] for segment in geometry["segments"])),
    }


def current_route(session: Session) -> dict | None:
    """Recompute the remembered route request; after a closure this is the new route or the reason none exists."""
    if session.route_request is None:
        return None
    request = session.route_request
    try:
        return draw_route(session, request["start"], request["destination"], request["step_free"], request["via"])
    except MapError as error:
        return {"ok": False, "error": str(error), **request}


def compact_steps(steps: list[str]) -> list[str]:
    """'Take Lift 2 (lift) to Floor 1.' ... 'to Floor 4.' becomes one line: only the last floor matters."""
    compact: list[str] = []
    for step in steps:
        ride = step.rsplit(" to ", 1)[0]
        if (
            compact
            and " to " in step
            and compact[-1].rsplit(" to ", 1)[0] == ride
            and ride.startswith(("Take ", "Use "))
        ):
            compact[-1] = step
        else:
            compact.append(step)
    return compact


def route_nodes(bm: BuildingMap, stops: list[str], step_free: bool) -> list[str]:
    """Same Dijkstra as BuildingMap.route, but keeping the door nodes so the line can pass through doors."""
    graph = bm.graph(step_free)
    nodes: list[str] = []
    for leg_start, leg_end in itertools.pairwise(stops):
        _, leg_nodes = nx.single_source_dijkstra(graph, leg_start, leg_end, weight="weight")
        nodes += leg_nodes if not nodes else leg_nodes[1:]
    return nodes


def route_geometry(bm: BuildingMap, nodes: list[str], step_free: bool) -> dict:
    """Split the node path into drawable segments per floor, plus markers where the route changes floor."""
    graph = bm.graph(step_free)
    segments: list[dict] = []
    floor_changes: list[dict] = []
    current: dict | None = None

    def point_of(node: str) -> tuple[str, list[float]] | None:
        if node.startswith(DOOR_PREFIX):
            opening = bm.openings[node[len(DOOR_PREFIX) :]]
            return opening["floor_id"], rounded(opening["position"])
        if node in bm.spaces:
            return bm.spaces[node]["floor_id"], rounded(bm.anchor(node))
        return None  # outside

    def add_point(node: str, kind: str = "walk") -> None:
        nonlocal current
        located = point_of(node)
        if located is None:
            return
        floor_id, point = located
        if current is None or current["floor_id"] != floor_id or current["kind"] != kind:
            current = {"floor_id": floor_id, "kind": kind, "points": []}
            segments.append(current)
        current["points"].append(point)

    add_point(nodes[0])
    for previous, node in itertools.pairwise(nodes):
        edge = min(graph[previous][node].values(), key=lambda candidate: candidate["weight"])
        element = edge["via"]
        if element in bm.connectors:
            connector = bm.connectors[element]
            from_floor, to_floor = bm.spaces[previous]["floor_id"], bm.spaces[node]["floor_id"]
            last = floor_changes[-1] if floor_changes else None
            if last and last["connector_id"] == element and last["to_floor"] == from_floor:
                # Riding on past a floor: one change F0 -> F4, no stub drawn on the floors in between.
                if current is not None and len(current["points"]) == 1:
                    segments.remove(current)
                last.update(to_floor=to_floor, to_point=rounded(bm.anchor(node)))
                current = None
                add_point(node)
                continue
            floor_changes.append(
                {
                    "connector_id": element,
                    "kind": connector["kind"],
                    "name": connector["name"],
                    "from_floor": from_floor,
                    "to_floor": to_floor,
                    "from_point": rounded(bm.anchor(previous)),
                    "to_point": rounded(bm.anchor(node)),
                }
            )
            current = None
            add_point(node)
        elif node == OUTSIDE or previous == OUTSIDE:
            # Leaving through one entrance and coming back in through another: draw that part dashed.
            if node == OUTSIDE:
                continue
            if current is not None:
                last_point = current["points"][-1]
                current = None
                add_point(node, "outside")
                current["points"].insert(0, last_point)
                current = None
            add_point(node)
        else:
            add_point(node)
    for change in floor_changes:
        going_up = bm.floors[change["to_floor"]]["level"] > bm.floors[change["from_floor"]]["level"]
        change["direction"] = "up" if going_up else "down"
    return {"segments": segments, "floor_changes": floor_changes}


# ---------- changes ----------


def set_closed(session: Session, element: str, closed: bool) -> dict:
    element_id = session.map.set_closed(element, closed)
    return {"element": element_id, "closed": closed, "state": state_view(session)}


def add_door(session: Session, first: str, second: str, step_free: bool = True) -> dict:
    opening = session.map.add_door(first, second, step_free=step_free)
    return {"door": opening_summary(session.map, opening["id"]), "state": state_view(session)}


def clear_route(session: Session) -> dict:
    session.route_request = None
    session.route_version += 1
    session.map.last_route = None
    return {"state": state_view(session)}
