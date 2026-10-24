"""JSON views of a BuildingMap for the 2D page. Pure functions, no HTTP, so tests can call them directly.

Routes on the page come from building_agent.routing (the people model the chat agent's find_route and
give_directions use), so map and chat show the same rooms. Every other number comes from starter_agent.building_map."""

import csv
import itertools
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import Polygon

from building_agent import routing
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError

COORD_DIGITS = 2
KEPT_ROUTE_REQUESTS = 8
DEFAULT_FLOOR_HEIGHT_M = 3.0


class RecordingMap(BuildingMap):
    """A BuildingMap that also remembers the arguments of its recent routes, so the page can redraw the chat
    agent's route with its via stops (RouteResult does not keep them). Records kit routes (BuildingMap.route) and
    people-model routes (building_agent.routing.route, see record_people_routes). Survives deepcopy."""

    last_route_request: dict | None = None
    route_requests: list[dict] | None = None

    def route(self, start: str, destination: str, step_free: bool = False, via: list[str] | None = None):
        result = super().route(start, destination, step_free, via)
        self.remember_route(start, destination, step_free, via, result)
        return result

    def remember_route(self, start: str, destination: str, step_free: bool, via, result) -> None:
        request = {
            "start": start,
            "destination": destination,
            "step_free": step_free,
            "via": [str(stop) for stop in via or [] if stop],
            "result": result,
        }
        self.last_route_request = request
        # Helpers like compare_normal_length route again and put the older result back into last_route,
        # so the request is looked up by its result, not just taken as the newest.
        self.route_requests = [*(self.route_requests or [])[-(KEPT_ROUTE_REQUESTS - 1) :], request]

    def request_for(self, result) -> dict | None:
        return next((r for r in reversed(self.route_requests or []) if r["result"] is result), None)


people_route = routing.route  # unwrapped: the page's own routes are never recorded as the agent's


def record_people_routes() -> None:
    """Wrap building_agent.routing.route so a RecordingMap remembers via stops of the agent's routes.
    Workaround until RouteResult carries its via stops; other maps pass straight through."""
    if getattr(routing.route, "records_route_requests", False):
        return

    def recorded_route(bm, start, destination, step_free=False, via=None):
        result = people_route(bm, start, destination, step_free, via)
        if isinstance(bm, RecordingMap):
            bm.remember_route(start, destination, step_free, via, result)
        return result

    recorded_route.records_route_requests = True
    recorded_route.__doc__ = people_route.__doc__
    routing.route = recorded_route


record_people_routes()


@dataclass
class Session:
    """One loaded building plus what the page needs to remember about it."""

    key: str
    directory: Path
    map: BuildingMap
    route_request: dict | None = None
    position: dict | None = None  # where the chat thinks the person is: {space_id, floor_id, point, source}
    guide_info: dict | None = None  # the leg being guided (rooms), from the chat; state_view draws it
    route_version: int = 0  # bumped by every route the page asks for or clears; newer page routes win
    campus: object | None = None  # web.campus_api.CampusService (shared by all sessions), or None
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
        recorded = self.map.request_for(route) if isinstance(self.map, RecordingMap) else None
        via = recorded["via"] if recorded else []
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
            "footprint": footprint_view(asset.get("footprint")),
        }
        for asset in bm.assets.values()
        if asset.get("position")
    ]
    info = bm.data["building"]
    return {
        "key": session.key,
        "name": info["name"],
        "source": info.get("source"),
        "floors": [floor_view(floor) for floor in floors],
        "spaces": spaces,
        "openings": openings,
        "connectors": connectors,
        "assets": assets,
        "state": state_view(session),
    }


def floor_view(floor: dict) -> dict:
    """Level, name and the heights the 3D view stacks floors with (drafts without heights get 3 m per level)."""
    height = floor.get("height_m") or DEFAULT_FLOOR_HEIGHT_M
    elevation = floor.get("elevation_m")
    return {
        "id": floor["id"],
        "level": floor["level"],
        "name": floor["name"],
        "elevation_m": round(elevation if elevation is not None else floor["level"] * height, COORD_DIGITS),
        "height_m": round(height, COORD_DIGITS),
    }


def footprint_view(footprint: dict | None) -> dict | None:
    """Asset size for the 3D view: width along x before rotation, depth along y, rotation counter-clockwise."""
    if not footprint or not footprint.get("width_m") or not footprint.get("depth_m"):
        return None
    return {
        "width_m": round(footprint["width_m"], COORD_DIGITS),
        "depth_m": round(footprint["depth_m"], COORD_DIGITS),
        "rotation_deg": round(footprint.get("rotation_deg") or 0.0, 1),
    }


def state_view(session: Session) -> dict:
    """The mutable part: closures, added doors and the current route (recomputed against the closures)."""
    bm = session.map
    return {
        "closed": sorted(bm.closed),
        "added_doors": [opening_summary(bm, opening_id) for opening_id in session.added_door_ids],
        "route": current_route(session),
        "position": session.position,
        "guide": guide_view(session),
        "campus": campus_state(session),
        **edit_state(bm),
    }


def campus_state(session: Session) -> dict:
    """Level 3: {loaded, key, name, route, closed_links}, see web/campus_api.py. Not loaded: loaded false."""
    if session.campus is None:
        return {"loaded": False, "key": None, "name": None, "route": None, "closed_links": []}
    return session.campus.state()


def guide_view(session: Session) -> dict | None:
    """The current leg while guided walking is active, else None (also after arrival: the page then shows the
    destination only). points: the leg's polyline in model metres, the same line the route would draw for it."""
    info = session.guide_info
    if not info:
        return None
    try:
        leg = draw_route(session, info["from"], info["to"], info["step_free"], info["between"])
        points = [point for segment in leg["segments"] for point in segment["points"]]
        segments = leg["segments"]
    except MapError:
        points, segments = [], []
    return {
        "active": True,
        "step_index": info["step_index"],
        "step_count": info["step_count"],
        "leg": {"from_space_id": info["from"], "to_space_id": info["to"], "points": points, "segments": segments},
        "target_space_id": info["target"],
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

PEOPLE_MODEL = "people"  # building_agent.routing: door to door, Synera's vertical costs (what the agent tells people)


def route_view(session: Session, start: str, destination: str, step_free: bool = False, via=None) -> dict:
    """A route the page asks for: remembered (newest wins over the chat agent's), then drawn."""
    via = [stop for stop in via or [] if stop]
    # Remember the request even if it fails, so the page shows "no route" instead of a stale line.
    session.route_request = {"start": start, "destination": destination, "step_free": step_free, "via": via}
    session.route_version += 1
    return draw_route(session, start, destination, step_free, via)


def draw_route(session: Session, start: str, destination: str, step_free: bool, via: list[str]) -> dict:
    """Shortest route in the people model (the one the agent's find_route and give_directions use), plus per-floor
    polylines (start anchor -> doors -> end anchor) and floor changes.
    Leaves map.last_route alone: that slot belongs to the chat agent, so redrawing never looks like a new agent route."""
    bm = session.map
    kept = (bm.last_route, getattr(bm, "last_route_request", None), list(getattr(bm, "route_requests", None) or []))
    try:
        result = people_route(bm, start, destination, step_free, via)
        kit = kit_route(bm, start, destination, step_free, via)
    finally:
        bm.last_route = kept[0]
        if isinstance(bm, RecordingMap):
            bm.last_route_request, bm.route_requests = kept[1], kept[2]
    stops = [result.start_space_id, *[bm.resolve_space(stop) for stop in via], result.destination_space_id]
    legs = route_legs(bm, stops, step_free, result.space_path)
    line_stops = stops if legs is not None else [stops[0], stops[-1]]
    geometry = route_geometry(bm, line_stops, legs if legs is not None else anchor_legs(bm, result.space_path))
    return {
        "ok": True,
        "model": PEOPLE_MODEL,
        "start": result.start_space_id,
        "destination": result.destination_space_id,
        "via": stops[1:-1],
        "step_free": step_free,
        "length_m": result.length_m,
        "space_path": result.space_path,
        "kit": kit,
        "differs_from_kit": kit is not None and kit["space_path"] != result.space_path,
        "steps": compact_steps(result.steps),
        **geometry,
        "floors": list(dict.fromkeys(segment["floor_id"] for segment in geometry["segments"])),
    }


def kit_route(bm: BuildingMap, start: str, destination: str, step_free: bool, via: list[str]) -> dict | None:
    """The same trip in the kit model (README section 3), which the labelled numbers use. None if it finds no route.
    The caller restores last_route; BuildingMap.route is called unbound so a RecordingMap does not record it."""
    try:
        result = BuildingMap.route(bm, start, destination, step_free=step_free, via=via)
    except MapError:
        return None
    return {"space_path": result.space_path, "length_m": result.length_m}


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


def route_legs(bm: BuildingMap, stops: list[str], step_free: bool, space_path: list[str]) -> list[list[tuple]] | None:
    """The door and connector nodes of each leg, from the same graph and search as routing.route (which only
    returns spaces). None if they do not give the route's space_path; the line then runs through room anchors."""
    rg = routing.routing_graph(bm, step_free)
    try:
        if len(stops) == 2:
            found = routing.shortest_leg(bm, rg, stops[0], stops[1])
            legs = None if found is None else [found[1]]
        else:
            legs = routing.tour_legs(bm, rg, stops, step_free)[1]
    except MapError:
        return None
    if legs is None:
        return None
    spaces: list[str] = []
    for (leg_start, leg_end), nodes in zip(itertools.pairwise(stops), legs, strict=True):
        leg = routing.leg_spaces(leg_start, leg_end, nodes)
        spaces += leg if not spaces else leg[1:]
    return legs if spaces == space_path else None


def anchor_legs(bm: BuildingMap, space_path: list[str]) -> list[list[tuple]]:
    """Fallback, one leg: a stop at every room anchor, and a connector crossing wherever the floor changes."""
    nodes: list[tuple] = []
    for previous, space_id in itertools.pairwise(space_path):
        if space_id == OUTSIDE or previous == OUTSIDE:
            continue
        if bm.spaces[previous]["floor_id"] != bm.spaces[space_id]["floor_id"]:
            connector = next(
                (c for c in bm.connectors.values() if previous in c["space_ids"] and space_id in c["space_ids"]), None
            )
            if connector is not None:
                nodes += [("c", connector["id"], previous), ("c", connector["id"], space_id)]
                continue
        nodes.append(("a", None, space_id))
    return [nodes]


def route_geometry(bm: BuildingMap, stops: list[str], legs: list[list[tuple]]) -> dict:
    """Drawable segments per floor plus markers where the route changes floor.

    The people model walks door to door: the line starts at the start room's anchor, runs through every door
    (and connector stop, which sits at its room's anchor), touches the anchor of each via stop, and ends at the
    destination's anchor. Walking outside between two entrances is its own dashed segment."""
    path: list[tuple] = [("a", None, stops[0])]
    for stop, nodes in zip(stops[1:], legs, strict=True):
        path += [*nodes, ("a", None, stop)]
    segments: list[dict] = []
    floor_changes: list[dict] = []
    current: dict | None = None

    def point_of(node: tuple) -> tuple[str, list[float]] | None:
        kind, element, space_id = node
        if kind == "o":
            opening = bm.openings[element]
            return opening["floor_id"], rounded(opening["position"])
        if space_id == OUTSIDE or space_id not in bm.spaces:
            return None
        return bm.spaces[space_id]["floor_id"], rounded(bm.anchor(space_id))

    def add_point(node: tuple, kind: str = "walk") -> None:
        nonlocal current
        located = point_of(node)
        if located is None:
            return
        floor_id, point = located
        if current is not None and current["floor_id"] == floor_id and current["points"][-1] == point:
            return
        if current is None or current["floor_id"] != floor_id or current["kind"] != kind:
            joined = [current["points"][-1]] if current is not None and current["floor_id"] == floor_id else []
            current = {"floor_id": floor_id, "kind": kind, "points": joined}
            segments.append(current)
        current["points"].append(point)

    add_point(path[0])
    for previous, node in itertools.pairwise(path):
        crossing = previous[0] == node[0] and previous[0] in "oc" and previous[1] == node[1] and previous[2] != node[2]
        if crossing and node[0] == "c":
            connector = bm.connectors[node[1]]
            from_floor, to_floor = bm.spaces[previous[2]]["floor_id"], bm.spaces[node[2]]["floor_id"]
            last = floor_changes[-1] if floor_changes else None
            if last and last["connector_id"] == node[1] and last["to_floor"] == from_floor:
                # Riding on past a floor: one change F0 -> F4, no stub drawn on the floors in between.
                if current is not None and len(current["points"]) == 1:
                    segments.remove(current)
                last.update(to_floor=to_floor, to_point=rounded(bm.anchor(node[2])))
            else:
                floor_changes.append(
                    {
                        "connector_id": node[1],
                        "kind": connector["kind"],
                        "name": connector["name"],
                        "from_floor": from_floor,
                        "to_floor": to_floor,
                        "from_point": rounded(bm.anchor(previous[2])),
                        "to_point": rounded(bm.anchor(node[2])),
                    }
                )
            current = None
            add_point(node)
        elif not crossing and previous[2] == OUTSIDE and node[2] == OUTSIDE:
            add_point(node, "outside")  # from one entrance to another, outside the building
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
