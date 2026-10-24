"""Read-only plan queries the model cannot answer today: list rooms with areas, whole-floor totals, doors by width,
room dimensions. NOT wired into tools.py (see docs/specs/question-coverage.md); plain functions plus an optional
`make_query_tools` factory, all computed from the building data, nothing is changed."""

import json

from anthropic import beta_tool
from anthropic.lib.tools import ToolError
from shapely.geometry import Polygon

from building_agent.geometry import space_area, space_polygon
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError

NON_ROOM_TYPES = {"corridor", "stairwell", "lift"}
ORDERS = {"area_desc", "area_asc", "name"}
MAX_ROWS = 60


def floor_ids(bm: BuildingMap, floor_level: int | None) -> set[str]:
    if floor_level is None:
        return set(bm.floors)
    found = {floor["id"] for floor in bm.floors.values() if floor["level"] == floor_level}
    if not found:
        raise MapError(f"No floor with level {floor_level}. Levels: {sorted(f['level'] for f in bm.floors.values())}.")
    return found


def rooms_table(
    bm: BuildingMap,
    floor_level: int | None = None,
    room_type: str | None = None,
    order: str = "area_desc",
    limit: int = MAX_ROWS,
    rooms_only: bool = True,
) -> dict:
    """Rooms with their area, sorted. `total` is the real count even when `rooms` is cut to `limit`."""
    if order not in ORDERS:
        raise MapError(f"order must be one of {sorted(ORDERS)}.")
    wanted_floors = floor_ids(bm, floor_level)
    wanted_type = room_type.strip().lower().replace(" ", "_") if room_type else None
    rows = []
    for space in bm.spaces.values():
        if space["id"] == OUTSIDE or space["floor_id"] not in wanted_floors:
            continue
        if wanted_type and space["room_type"] not in (wanted_type, wanted_type.removesuffix("s")):
            continue
        if rooms_only and not wanted_type and space["room_type"] in NON_ROOM_TYPES:
            continue
        rows.append(
            {
                "name": space["name"],
                "ref": space.get("ref"),
                "room_type": space["room_type"],
                "floor": bm.floor_name(space["floor_id"]),
                "area_m2": round(space_area(bm, space["id"]), 2),
                "space_id": space["id"],
            }
        )
    key = (lambda r: r["name"]) if order == "name" else (lambda r: r["area_m2"])
    rows.sort(key=key, reverse=order == "area_desc")
    return {
        "total": len(rows),
        "total_area_m2": round(sum(r["area_m2"] for r in rows), 2),
        "rooms": rows[: max(1, limit)],
    }


def floor_totals(bm: BuildingMap, floor_level: int) -> dict:
    """Whole-floor area (all spaces and rooms only) and the count and area per room type."""
    wanted = floor_ids(bm, floor_level)
    by_type: dict[str, dict] = {}
    for space in bm.spaces.values():
        if space["id"] != OUTSIDE and space["floor_id"] in wanted:
            entry = by_type.setdefault(space["room_type"], {"count": 0, "area_m2": 0.0})
            entry["count"] += 1
            entry["area_m2"] = round(entry["area_m2"] + space_area(bm, space["id"]), 2)
    rooms_area = sum(v["area_m2"] for t, v in by_type.items() if t not in NON_ROOM_TYPES)
    return {
        "floor": bm.floor_name(next(iter(wanted))),
        "total_area_m2": round(sum(v["area_m2"] for v in by_type.values()), 2),
        "rooms_area_m2": round(rooms_area, 2),
        "rooms_area_note": "rooms only: corridors, stairwells and lifts left out",
        "by_type": by_type,
    }


def doors_by_width(
    bm: BuildingMap,
    narrower_than: float | None = None,
    wider_than: float | None = None,
    floor_level: int | None = None,
    include_entrances: bool = False,
) -> dict:
    """Doors and openings filtered by width; entrances (openings to the outside) only when asked for."""
    wanted_floors = floor_ids(bm, floor_level)
    found = []
    for opening in sorted(bm.openings.values(), key=lambda o: o["id"]):
        if opening["floor_id"] not in wanted_floors:
            continue
        if OUTSIDE in opening["space_ids"] and not include_entrances:
            continue
        width = opening["width_m"]
        if (narrower_than is not None and width >= narrower_than) or (wider_than is not None and width <= wider_than):
            continue
        found.append(
            {
                "id": opening["id"],
                "between": [bm.spaces[i]["name"] if i in bm.spaces else "outside" for i in opening["space_ids"]],
                "floor": bm.floor_name(opening["floor_id"]),
                "width_m": width,
                "step_free": opening["step_free"],
            }
        )
    return {"count": len(found), "doors": found[:MAX_ROWS]}


def room_dimensions(bm: BuildingMap, room: str) -> dict:
    """Width and depth of a room: the axis-aligned box, and the true rectangle when the room is rotated."""
    space_id = bm.resolve_space(room)
    polygon = space_polygon(bm, space_id)
    min_x, min_y, max_x, max_y = polygon.bounds
    fitted = polygon.minimum_rotated_rectangle
    sides = []
    if isinstance(fitted, Polygon):
        points = list(fitted.exterior.coords)
        sides = sorted(
            round(((points[i][0] - points[i + 1][0]) ** 2 + (points[i][1] - points[i + 1][1]) ** 2) ** 0.5, 2)
            for i in range(2)
        )
    return {
        "name": bm.spaces[space_id]["name"],
        "area_m2": round(polygon.area, 2),
        "box_width_m": round(max_x - min_x, 2),
        "box_depth_m": round(max_y - min_y, 2),
        "fitted_rectangle_m": sides[::-1] if sides else None,
        "note": "box = east-west by north-south extent; fitted rectangle = long side, short side",
    }


def make_query_tools(bm: BuildingMap) -> list:
    def run(call):
        try:
            return json.dumps(call(), ensure_ascii=False, indent=1)
        except MapError as error:
            raise ToolError(str(error)) from error

    @beta_tool
    def list_rooms(
        floor_level: int | None = None, room_type: str | None = None, order: str = "area_desc", limit: int = 60
    ) -> str:
        """List rooms with their area in m2, sorted (area_desc, area_asc or name). Use it for 'list all offices on
        floor 1', 'smallest room', 'second largest', 'average size' and counts per type. `total` is the real count.

        Args:
            floor_level: Floor level (0 = ground floor, -1 = basement). Omit for the whole building.
            room_type: Room type such as office or toilet. Omit for all real rooms.
            order: area_desc (default), area_asc or name.
            limit: Most rows to return.
        """
        return run(lambda: rooms_table(bm, floor_level, room_type, order, limit))

    @beta_tool
    def floor_summary(floor_level: int) -> str:
        """Total area of a whole floor and the count and area per room type ('total area of floor 1')."""
        return run(lambda: floor_totals(bm, floor_level))

    @beta_tool
    def list_doors(
        narrower_than: float | None = None,
        wider_than: float | None = None,
        floor_level: int | None = None,
        include_entrances: bool = False,
    ) -> str:
        """Count and list doors by width in metres ('how many doors are narrower than 1 m', 'which doors are too
        narrow for a wheelchair'). Entrances only with include_entrances."""
        return run(lambda: doors_by_width(bm, narrower_than, wider_than, floor_level, include_entrances))

    @beta_tool
    def room_size(room: str) -> str:
        """Width, depth and area of one room ('how wide is Office 1.04')."""
        return run(lambda: room_dimensions(bm, room))

    return [list_rooms, floor_summary, list_doors, room_size]
