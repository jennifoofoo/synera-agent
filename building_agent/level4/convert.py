"""Level 4 conversion: Extraction (pixels, per floor) + Scale -> a complete building.json dict (metres).

Deterministic, no API. Odd input becomes Findings and dropped parts; only unusable input raises ConvertError
(no floors, scale zero/negative/NaN, nothing left to build)."""

import itertools
import math
import statistics
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import linemerge, nearest_points, unary_union

from building_agent.geometry import repaired
from building_agent.level4.schema import DOOR_KINDS, OUTSIDE, ROOM_TYPES, Extraction, Findings, Scale
from building_agent.level4.validate import Collector, room_label
from starter_agent.building_map import ADJACENT_DISTANCE_M

MIN_DOOR_WIDTH_M = 0.7
MAX_DOOR_WIDTH_M = 2.5
DEFAULT_DOOR_WIDTH_M = 0.9
SNAP_TOLERANCE_M = 0.05
DOOR_MOVED_WARN_M = 0.5
MAX_DOOR_SNAP_M = ADJACENT_DISTANCE_M
DOOR_CLAMP_SHARE = 0.1
WALL_BUFFER_M = 0.25
SHARED_WALL_GAP_M = 0.1
MIN_EXTERIOR_STRETCH_M = 0.3
MIN_ROOM_AREA_M2 = 0.05
FLOOR_HEIGHT_M = 3.0
MIN_STAIR_OVERLAP = 0.3
CONNECTOR_KIND = {"stair": "stairs", "lift": "lift"}
TYPE_ROOM_TYPE = {"stair": "stairwell", "lift": "lift", "corridor": "corridor", "hall": "lobby"}


class ConvertError(ValueError):
    """The input cannot be converted at all (the message says why, in plain words)."""


@dataclass
class FloorInput:
    level: int
    extraction: Extraction
    scale: Scale


@dataclass
class _Room:
    space_id: str
    ref: str | None
    name: str
    type: str
    given_name: str | None
    polygon: Polygon


# ---------- scale ----------


def _finite(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _point(value: object) -> tuple[float, float] | None:
    try:
        x, y = _finite(value[0]), _finite(value[1])  # type: ignore[index]
    except (TypeError, IndexError, KeyError):
        return None
    return None if x is None or y is None else (x, y)


def _ring(room: object) -> list[tuple[float, float]] | None:
    try:
        points = [_point(point) for point in room.polygon_px]  # type: ignore[attr-defined]
    except (TypeError, AttributeError):
        return None
    if len(points) < 3 or any(point is None for point in points):
        return None
    return points  # type: ignore[return-value]


def _x_extent(rings: list[list[tuple[float, float]]]) -> float:
    xs = [x for ring in rings for x, _ in ring]
    return max(xs) - min(xs) if xs else 0.0


def scale_from_known_length(
    extraction: Extraction, known_length_m: float, along: str = "building_width", room_id: str | None = None
) -> Scale:
    """Metres per pixel from one length the person knows.

    along: "building_width" (x extent of all rooms), "room" (shorter side of the room `room_id`) or
    "door" (median door width, or the width of the door of `room_id`)."""
    length = _finite(known_length_m)
    if length is None or length <= 0:
        raise ConvertError("The known length must be a positive number of metres.")
    rooms = [room for room in extraction.rooms if _ring(room)]
    if along == "building_width":
        pixels = _x_extent([_ring(room) for room in rooms])  # type: ignore[misc]
        label = "building width"
    elif along == "room":
        match = [room for room in rooms if str(room.id) == room_id or room.ref == room_id]
        if not match:
            raise ConvertError(f"No room '{room_id}' in the plan to measure with.")
        ring = _ring(match[0])
        pixels = min(_x_extent([ring]), _x_extent([[(y, x) for x, y in ring]]))  # type: ignore[misc]
        label = f"width of room {room_id}"
    elif along == "door":
        doors = [
            door
            for door in extraction.doors
            if _finite(door.width_px)
            and door.width_px > 0  # type: ignore[operator]
            and (room_id is None or room_id in map(str, door.rooms))
        ]
        if not doors:
            raise ConvertError("No door with a measured width in the plan to use as a ruler.")
        pixels = statistics.median(float(door.width_px) for door in doors)  # type: ignore[arg-type]
        label = "door width"
    else:
        raise ConvertError(f"Unknown way to measure: '{along}'.")
    if pixels <= 0:
        raise ConvertError("The plan has nothing wide enough to measure with.")
    return Scale(length / pixels, "known_length", f"{length:g} m taken as the {label}")


def scale_from_bar(extraction: Extraction) -> Scale | None:
    """Scale from the printed bar, or None when the plan has none."""
    pixels, metres = _finite(extraction.scale_bar_px), _finite(extraction.scale_bar_m)
    if pixels is None or metres is None or pixels <= 0 or metres <= 0:
        return None
    return Scale(metres / pixels, "scale_bar", f"printed bar of {metres:g} m")


# ---------- one floor ----------


def _snap(rings: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Merge corners of different rooms that lie within SNAP_TOLERANCE_M, so tiny gaps close."""
    cell = SNAP_TOLERANCE_M
    anchors: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
    snapped = []
    for ring in rings:
        out: list[tuple[float, float]] = []
        for x, y in ring:
            cx, cy = math.floor(x / cell), math.floor(y / cell)
            target = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for ax, ay in anchors.get((cx + dx, cy + dy), ()):
                        if math.hypot(ax - x, ay - y) <= SNAP_TOLERANCE_M:
                            target = (ax, ay)
                            break
                    if target:
                        break
                if target:
                    break
            if target is None:
                target = (x, y)
                anchors[(cx, cy)].append(target)
            if not out or out[-1] != target:
                out.append(target)
        if len(out) > 1 and out[0] == out[-1]:
            out.pop()
        snapped.append(out)
    return snapped


def _usable(ring: list[tuple[float, float]]) -> Polygon | None:
    if len(ring) < 3:
        return None
    polygon = Polygon(ring)
    if not polygon.is_valid:
        polygon = repaired(polygon)
    if not polygon.is_valid or polygon.area < MIN_ROOM_AREA_M2:
        return None
    return polygon


# ---------- door snapping ----------


def _lines(geometry) -> list[LineString]:
    """The line parts of a shapely result, merged where they continue each other."""
    parts = [g for g in getattr(geometry, "geoms", [geometry]) if isinstance(g, LineString) and g.length > 1e-6]
    merged = linemerge(parts) if len(parts) > 1 else (parts[0] if parts else None)
    if merged is None:
        return []
    return list(merged.geoms) if isinstance(merged, MultiLineString) else [merged]


def shared_wall(first: Polygon, second: Polygon) -> list[LineString]:
    """The stretches of first's outline that run along second (where the two polygons are closest)."""
    reach = first.distance(second) + WALL_BUFFER_M
    return _lines(first.boundary.intersection(second.boundary.buffer(reach)))


def exterior_wall(room: Polygon, others: list[Polygon]) -> list[LineString]:
    """The stretches of the room's outline that no other room touches."""
    boundary = room.boundary
    near = [other.buffer(SHARED_WALL_GAP_M) for other in others if other.distance(room) <= SHARED_WALL_GAP_M]
    if near:
        boundary = boundary.difference(unary_union(near))
    lines = _lines(boundary)
    return [line for line in lines if line.length >= MIN_EXTERIOR_STRETCH_M] or lines


def point_on_wall(stretches: list[LineString], point: Point, width_m: float = 0.0) -> Point | None:
    """The spot on the nearest stretch closest to `point`, pulled slightly in from the stretch ends."""
    if not stretches:
        return None
    line = min(stretches, key=lambda item: item.distance(point))
    along = line.project(point)
    margin = width_m * DOOR_CLAMP_SHARE
    if line.length > 2 * margin:
        along = min(max(along, margin), line.length - margin)
    return line.interpolate(along)


def pixel_to_metres(extraction: Extraction, scale: float) -> Callable[[float, float], tuple[float, float]]:
    """Image pixels (y down) to building metres (y up), the frame the converter uses."""
    ys = [y for room in extraction.rooms or [] for ring in [_ring(room)] if ring for _, y in ring]
    height = _finite(extraction.height_px)
    flip = height if height is not None and height > 0 else (max(ys) if ys else 0.0)
    return lambda x, y: (x * scale, (flip - y) * scale)


def _door_width(width_px: object, scale: float) -> float:
    pixels = _finite(width_px)
    if pixels is None or pixels <= 0:
        return DEFAULT_DOOR_WIDTH_M
    return round(min(max(pixels * scale, MIN_DOOR_WIDTH_M), MAX_DOOR_WIDTH_M), 2)


def _convert_floor(
    floor_input: FloorInput, floor_id: str, found: Collector
) -> tuple[list[dict], list[dict], list[_Room]]:
    extraction, scale = floor_input.extraction, floor_input.scale.metres_per_px
    raw_rooms = list(extraction.rooms or [])
    entries = [(room, _ring(room)) for room in raw_rooms]
    to_m = pixel_to_metres(extraction, scale)

    kept: list[tuple[object, list[tuple[float, float]]]] = []
    seen_ids: set[str] = set()
    for index, (room, ring) in enumerate(entries):
        label = str(getattr(room, "ref", None) or getattr(room, "name", None) or getattr(room, "id", index))
        if str(getattr(room, "id", index)) in seen_ids:
            found.add("room_duplicate_id", label)
            continue
        seen_ids.add(str(getattr(room, "id", index)))
        if ring is None:
            found.add("polygon_dropped", label)
            continue
        metres = [to_m(x, y) for x, y in ring]
        was_valid = Polygon(metres).is_valid
        polygon = _usable(metres)
        if polygon is None:
            found.add("polygon_dropped", label)
            continue
        if not was_valid:
            found.add("polygon_repaired", label)
            metres = list(polygon.exterior.coords)[:-1]
        kept.append((room, metres))

    snapped = _snap([ring for _, ring in kept])
    rooms: list[_Room] = []
    spaces: list[dict] = []
    id_map: dict[str, _Room] = {}
    for number, ((room, original), ring) in enumerate(zip(kept, snapped, strict=True), start=1):
        # keep the snapped outline only when it is still a clean polygon
        candidate = Polygon(ring) if len(ring) >= 3 else None
        if candidate is not None and candidate.is_valid and candidate.area >= MIN_ROOM_AREA_M2:
            polygon, corners = candidate, ring
        else:
            polygon, corners = Polygon(original), original
        coords = [[round(x, 3), round(y, 3)] for x, y in corners]
        space_id = f"{floor_id}-S{number:03d}"
        kind = room.type if room.type in ROOM_TYPES else "room"  # type: ignore[attr-defined]
        ref = str(room.ref).strip() if room.ref not in (None, "") else None  # type: ignore[attr-defined]
        given = str(room.name).strip() if room.name not in (None, "") else None  # type: ignore[attr-defined]
        name = given or (f"Room {ref}" if ref else f"Room {number}")
        given_type = (room.room_type or "").strip()  # type: ignore[attr-defined]
        if kind in ("stair", "lift"):
            room_type = TYPE_ROOM_TYPE[kind]
        elif given_type and given_type != "generic_room":
            room_type = given_type
        else:
            room_type = TYPE_ROOM_TYPE.get(kind, "generic_room")
        spaces.append(
            {
                "id": space_id,
                "floor_id": floor_id,
                "type": kind,
                "room_type": room_type,
                "name": name,
                "ref": ref,
                "polygon": coords,
                "synthetic": False,
            }
        )
        info = _Room(space_id, ref, name, kind, given or ref, polygon)
        rooms.append(info)
        id_map[str(room.id)] = info  # type: ignore[attr-defined]

    boundaries: dict[str, object] = {}

    def boundary(room: _Room):
        if room.space_id not in boundaries:
            boundaries[room.space_id] = room.polygon.boundary
        return boundaries[room.space_id]

    openings: list[dict] = []
    for door in extraction.doors or []:
        try:
            ids = [str(room_id) for room_id in door.rooms]
        except TypeError:
            ids = []
        spot = _point(door.position_px)
        if len(ids) != 2:
            found.add("door_unknown_room", "?")
            continue
        label = "/".join(id_map[i].ref or id_map[i].name if i in id_map else i for i in ids)
        outside = [i == OUTSIDE for i in ids]
        if ids[0] == ids[1]:
            found.add("door_same_room", label)
            continue
        if any(i != OUTSIDE and i not in id_map for i in ids):
            found.add("door_unknown_room", label)
            continue
        if spot is None:
            found.add("door_bad_position", label)
            continue
        point = Point(*to_m(*spot))
        ends = [id_map[i] for i in ids if i != OUTSIDE]
        if any(room.polygon.distance(point) > MAX_DOOR_SNAP_M for room in ends):
            found.add("door_not_on_wall", label)
            continue
        width = _door_width(door.width_px, scale)
        if len(ends) == 2:
            spot_m = point_on_wall(shared_wall(ends[0].polygon, ends[1].polygon), point, width)
            if spot_m is None:
                spot_m = nearest_points(boundary(ends[0]), point)[0]
            second = nearest_points(boundary(ends[1]), spot_m)[0]
            if spot_m.distance(second) > 2 * ADJACENT_DISTANCE_M:  # the midpoint is then within 0.6 m of both
                found.add("door_not_on_wall", label)
                continue
            position = [(spot_m.x + second.x) / 2, (spot_m.y + second.y) / 2]
        else:
            others = [room.polygon for room in rooms if room is not ends[0]]
            spot_m = point_on_wall(exterior_wall(ends[0].polygon, others), point, width)
            if spot_m is None:
                spot_m = nearest_points(boundary(ends[0]), point)[0]
            position = [spot_m.x, spot_m.y]
        if point.distance(Point(position)) > DOOR_MOVED_WARN_M:
            found.add("door_moved", label)
        kind = "entrance" if any(outside) else (door.kind if door.kind in DOOR_KINDS else "door")
        openings.append(
            {
                "id": f"{floor_id}-O{len(openings) + 1:04d}",
                "floor_id": floor_id,
                "space_ids": [OUTSIDE if flag else id_map[i].space_id for i, flag in zip(ids, outside, strict=True)],
                "kind": kind,
                "position": [round(position[0], 3), round(position[1], 3)],
                "width_m": width,
                "step_free": True,
                "synthetic": False,
            }
        )
    return spaces, openings, rooms


# ---------- stairs and lifts ----------


def _link_connectors(
    levels: list[int], floor_ids: dict[int, str], rooms: dict[int, list[_Room]], building_id: str
) -> tuple[list[dict], set[str]]:
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        while parent.setdefault(item, item) != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for low, high in itertools.pairwise(levels):
        pairs = []
        for first in (room for room in rooms[low] if room.type in CONNECTOR_KIND):
            for second in (room for room in rooms[high] if room.type == first.type):
                same_key = any(
                    a and b and a.lower() == b.lower()
                    for a, b in ((first.ref, second.ref), (first.given_name, second.given_name))
                )
                union = first.polygon.union(second.polygon).area
                overlap = first.polygon.intersection(second.polygon).area / union if union else 0.0
                if same_key or overlap >= MIN_STAIR_OVERLAP:
                    pairs.append((same_key, overlap, first.space_id, second.space_id))
        used: set[str] = set()
        for _, _, first_id, second_id in sorted(pairs, reverse=True):
            if first_id not in used and second_id not in used:
                used.update((first_id, second_id))
                parent[find(second_id)] = find(first_id)

    by_id = {room.space_id: (level, room) for level in levels for room in rooms[level]}
    groups: dict[str, list[str]] = defaultdict(list)
    for space_id in [space_id for space_id in parent if space_id in by_id]:
        groups[find(space_id)].append(space_id)
    connectors = []
    linked: set[str] = set()
    ordered = sorted(
        (sorted(group, key=lambda sid: by_id[sid][0]) for group in groups.values() if len(group) > 1),
        key=lambda g: (by_id[g[0]][0], g[0]),
    )
    for number, group in enumerate(ordered, start=1):
        first_room = by_id[group[0]][1]
        kind = CONNECTOR_KIND[first_room.type]
        connectors.append(
            {
                "id": f"{building_id}-V{number:02d}",
                "kind": kind,
                "name": first_room.name,
                "floor_ids": [floor_ids[by_id[sid][0]] for sid in group],
                "space_ids": group,
                "step_free": kind == "lift",
                "synthetic": False,
            }
        )
        linked.update(group)
    return connectors, linked


# ---------- entry points ----------


def _check_input(floors: list[FloorInput], building_id: str) -> None:
    if not isinstance(building_id, str) or not building_id.strip():
        raise ConvertError("The building needs an id.")
    if not floors:
        raise ConvertError("There is no floor to convert.")
    levels = [floor.level for floor in floors]
    if len(set(levels)) != len(levels):
        raise ConvertError("Two floor images have the same level.")
    for floor in floors:
        factor = _finite(floor.scale.metres_per_px)
        if factor is None or factor <= 0:
            raise ConvertError("The scale must be a positive number of metres per pixel.")


def convert_floors_with_findings(
    floors: list[FloorInput], building_name: str, building_id: str
) -> tuple[dict, Findings]:
    """Return the building.json dict and what was repaired or dropped on the way."""
    _check_input(floors, building_id)
    found = Collector()
    ordered = sorted(floors, key=lambda floor: floor.level)
    levels = [floor.level for floor in ordered]
    floor_ids = {level: f"{building_id}-F{level}" for level in levels}
    spaces: list[dict] = []
    openings: list[dict] = []
    rooms: dict[int, list[_Room]] = {}
    for floor in ordered:
        floor_spaces, floor_openings, floor_rooms = _convert_floor(floor, floor_ids[floor.level], found)
        spaces += floor_spaces
        openings += floor_openings
        rooms[floor.level] = floor_rooms
        if not floor_spaces:
            found.add("floor_empty", f"floor {floor.level}")
    if not spaces:
        raise ConvertError("No usable room was found in the plan.")

    connectors, linked = _link_connectors(levels, floor_ids, rooms, building_id)
    if len(levels) > 1:
        for level in levels:
            for room in rooms[level]:
                if room.type in CONNECTOR_KIND and room.space_id not in linked:
                    found.add(
                        "connector_single_floor", room_label({"id": room.space_id, "ref": room.ref, "name": room.name})
                    )

    floor_dicts = [
        {
            "id": floor_ids[level],
            "level": level,
            "name": "Ground floor" if level == 0 else (f"Floor {level}" if level > 0 else f"Basement {-level}"),
            "elevation_m": round(level * FLOOR_HEIGHT_M, 2),
            "height_m": FLOOR_HEIGHT_M,
        }
        for level in levels
    ]
    building = {
        "building": {
            "id": building_id,
            "name": building_name,
            "source": "plan_upload",
            "source_ref": {},
            "license": "",
            "attribution": "Built from uploaded floor plans",
            "split": "user",
            "units": "m",
        },
        "floors": floor_dicts,
        "spaces": spaces,
        "openings": openings,
        "vertical_connectors": connectors,
        "assets": [],
    }
    return building, Findings(found.findings())


def convert_floors(floors: list[FloorInput], building_name: str, building_id: str) -> dict:
    """The building.json dict only; use convert_floors_with_findings to also get what was dropped."""
    return convert_floors_with_findings(floors, building_name, building_id)[0]
