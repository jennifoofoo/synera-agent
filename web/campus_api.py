"""Level 3 on the page: the campus endpoints (GET /api/campus, POST /api/campus/{load,route,close}).

One CampusService per server holds the ONE CampusHolder that the page and the chat agent share, so a link closed
on the page shows up in the agent's campus_route and the other way round. Pure Python, no HTTP: the server only
dispatches here. Nothing from the browser is ever used as a path or a type: campus keys come from a list built
here, ids are checked against the loaded campus, bad input is a clean 400 (MapError), never a crash."""

from pathlib import Path

from building_agent import campus as campus_module
from building_agent.campus import CampusError, building_center, entrances, load_campus, load_maps, world_point
from building_agent.campus_routing import AmbiguousReference, CampusLeg, CampusRoute, entrance_labels
from building_agent.campus_tools import CampusHolder
from starter_agent.building_map import BuildingMap, MapError
from web import api

EXAMPLE_KEY = "example"
CAMPUS_FILE = "campus.json"
MAX_TEXT = 200
CAMPUS_FILE_SUFFIXES = (".json", ".csv")

NOT_LOADED = {"loaded": False, "key": None, "name": None, "route": None, "closed_links": []}


def idle_state() -> dict:
    """The `campus` field of state_view when no campus is loaded."""
    return {**NOT_LOADED, "closed_links": []}


def finding_view(finding) -> dict:
    return {"level": finding.level, "code": finding.code, "message": finding.message, "items": list(finding.items)}


def text_arg(body: dict, name: str, required: bool = True) -> str | None:
    value = body.get(name)
    if value is None or value == "":
        if required:
            raise MapError(f"'{name}' is needed.")
        return None
    if not isinstance(value, str):
        raise MapError(f"'{name}' must be text.")
    value = value.strip()
    if len(value) > MAX_TEXT or "\x00" in value:
        raise MapError(f"'{name}' is not a usable value.")
    return value


def flag_arg(body: dict, name: str, default: bool) -> bool:
    value = body.get(name, default)
    if not isinstance(value, bool):
        raise MapError(f"'{name}' must be true or false.")
    return value


def point_pair(point) -> list[float]:
    return api.rounded(point)


class CampusService:
    def __init__(self, data_root: Path, buildings_root: Path, extra_roots: tuple[Path, ...] = ()) -> None:
        self.data_root = Path(data_root)
        self.buildings_root = Path(buildings_root)
        self.roots = [self.data_root, *extra_roots]
        self.holder: CampusHolder | None = None
        self.key: str | None = None
        self.findings: list = []
        self.route_request: dict | None = None
        self.active_dir: Path | None = None  # the building the page shows (a Session directory)

    # ---------- which campuses can be loaded ----------

    def known(self) -> dict[str, dict]:
        """key -> {name, path (None for the example)}. The browser can only pick one of these keys."""
        found: dict[str, dict] = {}
        try:
            campus_module.make_example_campus(self.data_root)
            found[EXAMPLE_KEY] = {"name": "Example campus (three dev buildings)", "path": None}
        except (CampusError, OSError, ValueError, KeyError):
            pass
        for root in self.roots:
            if not root.is_dir():
                continue
            files = [*sorted(root.glob("campus*.json")), *sorted(root.glob(f"*/{CAMPUS_FILE}"))]
            if root != self.data_root:  # a dedicated campuses folder: any json or csv in it is a candidate
                files += [item for item in sorted(root.glob("*")) if item.suffix.lower() in CAMPUS_FILE_SUFFIXES]
            for path in files:
                if not path.is_file():
                    continue
                key = f"{root.name}:{path.relative_to(root).as_posix()}"
                found.setdefault(key, {"name": path.stem, "path": path})
        return found

    # ---------- views ----------

    def page_key(self, directory: Path | None) -> str | None:
        """The key /api/building understands for a building folder, or None if it is outside the known roots."""
        if directory is None:
            return None
        resolved = Path(directory).resolve()
        for root, prefix in ((self.data_root, ""), (self.buildings_root, "user/")):
            if root.exists() and resolved.is_relative_to(root.resolve()):
                return prefix + resolved.relative_to(root.resolve()).as_posix()
        return None

    def active_building_id(self) -> str | None:
        if self.holder is None or self.active_dir is None:
            return None
        active = Path(self.active_dir).resolve()
        for item in self.holder.campus.buildings:
            if item.path is not None and Path(item.path).exists() and Path(item.path).resolve() == active:
                return item.building_id
        return None

    def entrance_view(self, holder: CampusHolder, building_id: str, bm: BuildingMap, entrance: dict, labels: dict):
        building = holder.campus.building(building_id)
        world = world_point(building, entrance["position"]) if building else None
        opening = bm.openings.get(entrance["id"], {})
        return {
            "id": entrance["id"],
            "name": labels.get(entrance["id"], "entrance"),
            "room": entrance["room"],
            "space_id": entrance["space_id"],
            "floor_id": opening.get("floor_id"),
            "position": point_pair(entrance["position"]),
            "world_position": point_pair(world) if world else None,
            "step_free": entrance["step_free"],
        }

    def building_view(self, holder: CampusHolder, item) -> dict:
        bm = holder.maps.get(item.building_id)
        center = building_center(bm) if bm is not None else None
        world_center = world_point(item, center) if center is not None else None
        labels = entrance_labels(bm) if bm is not None else {}
        floors = sorted(bm.floors.values(), key=lambda floor: floor["level"]) if bm is not None else []
        return {
            "id": item.building_id,
            "name": holder.router.building_name(item.building_id),
            "map_loaded": bm is not None,
            "page_key": self.page_key(item.path) if bm is not None else None,
            "active": item.building_id == self.active_building_id(),
            "floors": [api.floor_view(floor) for floor in floors],
            "floor_count": len(floors),
            "origin": list(item.origin) if item.origin is not None else None,
            "rotation_deg": item.rotation_deg,
            "world_center": point_pair(world_center) if world_center else None,
            "entrances": [self.entrance_view(holder, item.building_id, bm, e, labels) for e in entrances(bm)]
            if bm is not None
            else [],
        }

    def link_view(self, holder: CampusHolder, link) -> dict:
        ends = []
        for building_id, entrance_id in (
            (link.from_building, link.from_entrance),
            (link.to_building, link.to_entrance),
        ):
            ends.append(self.endpoint(holder, building_id, entrance_id))
        return {
            "id": link.id,
            "kind": link.kind,
            "name": link.name,
            "from": ends[0],
            "to": ends[1],
            "level_delta": link.level_delta,
            "length_m": link.length_m,
            "length_estimated": link.length_estimated,
            "width_m": link.width_m,
            "step_free": link.step_free,
            "closed": link.closed,
        }

    def endpoint(self, holder: CampusHolder, building_id: str, entrance_id: str) -> dict:
        bm = holder.maps.get(building_id)
        building = holder.campus.building(building_id)
        found = next((e for e in entrances(bm) if e["id"] == entrance_id), None) if bm is not None else None
        point = found["position"] if found else None
        world = world_point(building, point) if building and point else None
        return {
            "building_id": building_id,
            "entrance_id": entrance_id,
            "point": point_pair(point) if point else None,
            "world_point": point_pair(world) if world else None,
        }

    def view(self) -> dict:
        available = [{"key": key, "name": item["name"]} for key, item in self.known().items()]
        if self.holder is None:
            return {"loaded": False, "available": available, "buildings": [], "links": [], "findings": []}
        holder = self.holder
        return {
            "loaded": True,
            "key": self.key,
            "name": holder.campus.name,
            "available": available,
            "buildings": [self.building_view(holder, item) for item in holder.campus.buildings],
            "links": [self.link_view(holder, link) for link in holder.campus.links],
            "findings": [finding_view(item) for item in self.findings],
            "state": self.state(),
        }

    def state(self) -> dict:
        """The `campus` field of state_view: loaded flag, the page's route (recomputed against closures), closed links."""
        if self.holder is None:
            return idle_state()
        route = None
        if self.route_request is not None:
            outcome = self.compute_route(self.route_request)
            route = {"request": self.route_request, "ok": outcome["ok"]}
            if outcome["ok"]:
                route.update(
                    length_m=outcome["length_m"], buildings=outcome["buildings"], links_used=outcome["links_used"]
                )
            else:
                route["error"] = outcome["error"]
        return {
            "loaded": True,
            "key": self.key,
            "name": self.holder.campus.name,
            "route": route,
            "closed_links": [link.id for link in self.holder.campus.links if link.closed],
        }

    # ---------- load ----------

    def load(self, body: dict) -> dict:
        key = body.get("key")
        known = self.known()
        if not isinstance(key, str) or key not in known:
            raise MapError("Unknown campus. Pick one of the keys from GET /api/campus (available).")
        entry = known[key]
        if entry["path"] is None:
            try:
                campus = campus_module.make_example_campus(self.data_root)
            except (CampusError, OSError, ValueError, KeyError) as error:
                raise MapError(f"The example campus could not be built: {error}") from error
            maps, findings = load_maps(campus)
            findings = [*findings, *campus_module.validate_campus(campus, maps)]
            path = None
        else:
            try:
                campus, loaded = load_campus(entry["path"], root=self.data_root)
            except CampusError as error:
                raise MapError(str(error)) from error
            maps, _ = load_maps(campus)
            findings = list(loaded.items)
            path = entry["path"] if entry["path"].name == CAMPUS_FILE else None  # never overwrite a csv or geo file
        self.holder = CampusHolder(campus, maps, path=path)
        self.key = key
        self.findings = findings
        self.route_request = None
        errors = [item for item in findings if item.level == "error"]
        return {
            "loaded": True,
            "key": key,
            "problems": len(errors),
            "findings": [finding_view(item) for item in findings],
            "summary": "No problems found." if not findings else " ".join(item.message for item in findings),
            "campus": self.view(),
        }

    # ---------- route ----------

    def require(self) -> CampusHolder:
        if self.holder is None:
            raise MapError("No campus is loaded. Load one with POST /api/campus/load first.")
        return self.holder

    def route(self, body: dict) -> dict:
        self.require()
        request = {
            "start": text_arg(body, "start"),
            "destination": text_arg(body, "destination"),
            "start_building": text_arg(body, "start_building", required=False),
            "destination_building": text_arg(body, "destination_building", required=False),
            "step_free": flag_arg(body, "step_free", False),
        }
        self.route_request = request  # remembered even if it fails, so the page shows 'no route', not a stale line
        return {**self.compute_route(request), "state": self.state()}

    def compute_route(self, request: dict) -> dict:
        holder = self.require()

        def stop(place: str, building: str | None):
            return (place, building) if building else place

        try:
            route = holder.router.route(
                stop(request["start"], request["start_building"]),
                stop(request["destination"], request["destination_building"]),
                request["step_free"],
            )
        except AmbiguousReference as error:
            return {"ok": False, "ambiguous": True, "error": str(error), "candidates": error.candidates}
        except MapError as error:
            return {"ok": False, "ambiguous": False, "error": str(error)}
        return {"ok": True, **self.route_payload(holder, route)}

    def route_payload(self, holder: CampusHolder, route: CampusRoute) -> dict:
        return {
            "length_m": route.length_m,
            "step_free": route.step_free,
            "buildings": list(route.buildings),
            "building_names": [holder.router.building_name(item) for item in route.buildings],
            "links_used": [link.id for link in route.links],
            "steps": list(route.steps),
            "legs": [self.leg_payload(holder, leg) for leg in route.legs],
        }

    def leg_payload(self, holder: CampusHolder, leg: CampusLeg) -> dict:
        if leg.kind == "link":
            link = leg.link
            return {
                "kind": "link",
                "link_id": link.id,
                "link_kind": link.kind,
                "name": link.name,
                "length_m": leg.length_m,
                "step_free": link.step_free,
                "level_delta": link.level_delta,
                "from": self.endpoint(holder, leg.from_building, leg.from_entrance),
                "to": self.endpoint(holder, leg.to_building, leg.to_entrance),
            }
        bm = holder.maps[leg.building_id]
        building = holder.campus.building(leg.building_id)
        segments, floor_changes = self.leg_geometry(holder, leg, bm)
        points = [point for segment in segments for point in segment["points"]]
        world = [world_point(building, point) for point in points] if building else []
        has_world = bool(points) and all(item is not None for item in world)
        return {
            "kind": "building",
            "building_id": leg.building_id,
            "building_name": holder.router.building_name(leg.building_id),
            "length_m": leg.length_m,
            "entry_entrance": leg.entry_entrance,
            "exit_entrance": leg.exit_entrance,
            "rooms": [
                {"id": space_id, "name": bm.spaces[space_id]["name"], "floor_id": bm.spaces[space_id]["floor_id"]}
                for space_id in leg.route.space_path
                if space_id in bm.spaces
            ],
            "segments": segments,
            "floor_changes": floor_changes,
            "points": points,
            "world_points": [point_pair(item) for item in world] if has_world else None,
        }

    def leg_geometry(self, holder: CampusHolder, leg: CampusLeg, bm: BuildingMap) -> tuple[list[dict], list[dict]]:
        """Per-floor polylines in the building's own metres: room anchor, doors, room anchor (as the page draws a
        route), and the entrance doors at the ends where the leg enters or leaves the building."""
        inner = holder.router._inner(leg.building_id)
        path = leg.route.space_path
        stops = [path[0], path[-1]]
        legs = api.route_legs(inner, stops, leg.route.step_free, path)
        legs = legs if legs is not None else api.anchor_legs(bm, path)
        geometry = api.route_geometry(bm, stops, legs)
        segments = geometry["segments"]
        for entrance_id, at_start in ((leg.entry_entrance, True), (leg.exit_entrance, False)):
            opening = bm.openings.get(entrance_id) if entrance_id else None
            if opening is None or not segments:
                continue
            segment = segments[0] if at_start else segments[-1]
            if segment["floor_id"] == opening["floor_id"]:
                point = point_pair(opening["position"])
                if segment["points"][0 if at_start else -1] == point:
                    continue
                if at_start:
                    segment["points"].insert(0, point)
                else:
                    segment["points"].append(point)
        return segments, geometry["floor_changes"]

    # ---------- close ----------

    def close(self, body: dict) -> dict:
        holder = self.require()
        link_id = text_arg(body, "link_id")
        if "closed" in body and not isinstance(body["closed"], bool):
            raise MapError("'closed' must be true or false.")
        closed = body.get("closed", True)
        link = next((item for item in holder.campus.links if item.id == link_id), None)  # exact id, no guessing
        if link is None:
            raise MapError(f"There is no link '{link_id}' in this campus.")
        effect = holder.router.link_effect(link, closed)
        link.closed = closed
        saved = self.save(holder)
        result = {
            "link": self.link_view(holder, link),
            "effect": effect,
            "saved": saved,
            "state": self.state(),
        }
        if self.route_request is not None:
            result["route"] = self.compute_route(self.route_request)
        return result

    def save(self, holder: CampusHolder) -> bool:
        """Persist like the chat does, but only into a campus.json that was loaded from a known root."""
        if holder.path is None:
            return False
        campus_module.save_campus(holder.campus, holder.path)
        return True

    # ---------- dispatch ----------

    def get(self, path: str, active_dir: Path | None) -> tuple[int, dict]:
        if path == "/api/campus":
            self.active_dir = active_dir if active_dir is not None else self.active_dir
            return 200, self.view()
        return 404, {"error": f"Unknown endpoint {path}"}

    def post(self, path: str, body: dict) -> tuple[int, dict]:
        if not isinstance(body, dict):
            raise MapError("The body must be a JSON object.")
        if path == "/api/campus/load":
            return 200, self.load(body)
        if path == "/api/campus/route":
            return 200, self.route(body)
        if path == "/api/campus/close":
            return 200, self.close(body)
        return 404, {"error": f"Unknown endpoint {path}"}
