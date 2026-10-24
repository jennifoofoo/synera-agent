"""Level 4 validation: checks on a converted building.json dict, answered as plain-language Findings.

Never raises on odd data: a building that cannot even be loaded becomes a `building_invalid` finding."""

import math
from collections import defaultdict

import networkx as nx
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

from building_agent.level4.schema import Finding, Findings
from starter_agent.building_map import ADJACENT_DISTANCE_M, OUTSIDE, BuildingMap

MIN_AREA_M2 = 1.0
PLAUSIBLE_AREA_M2 = (2.0, 300.0)
PLAUSIBLE_DOOR_WIDTH_M = (0.7, 2.5)
PLAUSIBLE_FOOTPRINT_M = (4.0, 400.0)
OVERLAP_SHARE = 0.25
LARGE_ROOM_TYPES = {"hall", "outdoor", "corridor"}
OUTER_WALL_TOLERANCE_M = 0.6
OUTER_CLOSE_GAP_M = 0.3

# code -> (level, template). {s}, {have} and {is} adapt to the count {n}.
CODES: dict[str, tuple[str, str]] = {
    "building_invalid": ("error", "The building data is incomplete and could not be checked."),
    "polygon_invalid": ("error", "{n} room{s} {have} an unusable outline."),
    "polygon_repaired": ("warning", "{n} room outline{s} {have} crossed itself and {is} repaired."),
    "polygon_dropped": ("warning", "{n} room{s} without a usable outline {is} left out."),
    "polygon_tiny": ("error", "{n} room{s} {is} smaller than 1 m2."),
    "room_overlap": ("error", "{n} pair{s} of rooms {have} a strong overlap."),
    "room_duplicate_id": ("warning", "{n} room{s} {have} an id that was already used and {is} left out."),
    "door_unknown_room": ("error", "{n} door{s} {have} a room that does not exist."),
    "door_same_room": ("error", "{n} door{s} {have} the same room on both sides."),
    "door_not_on_wall": ("error", "{n} door{s} {is} not on a wall the two rooms share."),
    "door_bad_position": ("warning", "{n} door{s} without a usable position {is} left out."),
    "door_moved": ("warning", "{n} door{s} {is} more than 0.5 m from the wall in the plan and moved onto it."),
    "entrance_not_on_outer_wall": ("warning", "{n} entrance{s} {is} not on the outer wall of the floor."),
    "entrance_dropped": ("warning", "{n} entrance marker{s} in the plan {is} not on the outer wall and {is} left out."),
    "entrance_reattached": ("warning", "{n} entrance{s} {is} moved to the room that touches the outer wall there."),
    "no_entrance": ("error", "The building has no entrance to the outside."),
    "room_unreachable": ("error", "{n} room{s} {have} no way out, doors are probably missing."),
    "low_connectivity": ("warning", "{n} room{s} {have} no door in the plan, a door is probably missing."),
    "area_implausible": ("warning", "{n} room{s} {have} an unlikely size (not 2 to 300 m2)."),
    "door_width_implausible": ("warning", "{n} door{s} {have} an unlikely width (not 0.7 to 2.5 m)."),
    "connector_missing_stop": ("error", "{n} stair{s} or lift{s} {have} no stop room on every floor they pass."),
    "connector_single_floor": ("warning", "{n} stair{s} or lift{s} could not be matched to a room on another floor."),
    "scale_implausible": ("error", "The building would be an unlikely size, the scale is probably wrong."),
    "scale_unusual_known": ("warning", "The building is an unusual size for the length you gave, please check it."),
    "no_vertical_connectors": (
        "error",
        "I found more than one floor but no stairs or lifts between them. Which rooms are the stairs and lifts?",
    ),
    "connector_typed_by_hint": ("warning", "{n} room{s} {is} taken as stairs or lift because of the name or colour."),
    "connector_linked_by_order": (
        "warning",
        "{n} stair or lift pair{s} on neighbouring floors {is} linked because each floor has only one.",
    ),
    "connector_aligned_by_centre": (
        "warning",
        "{n} stair or lift pair{s} {is} matched after centring the floors on each other, please check.",
    ),
    "floor_empty": ("warning", "{n} floor{s} without any room."),
}

PLURAL_PHRASES = {"s": "s", "have": "have", "is": "are"}
SINGULAR_PHRASES = {"s": "", "have": "has", "is": "is"}


class Collector:
    """Gathers items per code and turns them into one Finding per code."""

    def __init__(self) -> None:
        self.items: dict[str, list[str]] = defaultdict(list)

    def add(self, code: str, item: str = "") -> None:
        self.items[code].append(item)

    def findings(self) -> list[Finding]:
        found = []
        for code, items in self.items.items():
            level, template = CODES[code]
            phrases = SINGULAR_PHRASES if len(items) == 1 else PLURAL_PHRASES
            message = template.format(n=len(items), **phrases)
            found.append(Finding(level, code, message, [item for item in items if item]))
        return found


def room_label(space: dict) -> str:
    return space.get("ref") or space.get("name") or space["id"]


def _polygon(space: dict) -> Polygon | None:
    try:
        coords = [(float(x), float(y)) for x, y in space["polygon"]]
    except (KeyError, TypeError, ValueError):
        return None
    if len(coords) < 3 or not all(math.isfinite(value) for point in coords for value in point):
        return None
    return Polygon(coords)


def _check_rooms(building: dict, found: Collector) -> dict[str, Polygon]:
    polygons: dict[str, Polygon] = {}
    for space in building["spaces"]:
        polygon = _polygon(space)
        if polygon is None or not polygon.is_valid:
            found.add("polygon_invalid", room_label(space))
            continue
        polygons[space["id"]] = polygon
        if polygon.area < MIN_AREA_M2:
            found.add("polygon_tiny", room_label(space))
        elif not PLAUSIBLE_AREA_M2[0] <= polygon.area <= PLAUSIBLE_AREA_M2[1]:
            too_big_allowed = space.get("type") in LARGE_ROOM_TYPES and polygon.area > PLAUSIBLE_AREA_M2[1]
            if not too_big_allowed:
                found.add("area_implausible", room_label(space))
    return polygons


def _check_overlaps(building: dict, polygons: dict[str, Polygon], found: Collector) -> None:
    by_floor: dict[str, list[str]] = defaultdict(list)
    for space in building["spaces"]:
        if space["id"] in polygons:
            by_floor[space["floor_id"]].append(space["id"])
    spaces = {space["id"]: space for space in building["spaces"]}
    for ids in by_floor.values():
        shapes = [polygons[space_id] for space_id in ids]
        tree = STRtree(shapes)
        for index, shape in enumerate(shapes):
            for other in tree.query(shape, predicate="intersects"):
                if other <= index:
                    continue
                smaller = min(shape.area, shapes[other].area)
                if smaller > 0 and shape.intersection(shapes[other]).area / smaller > OVERLAP_SHARE:
                    first, second = spaces[ids[index]], spaces[ids[other]]
                    found.add("room_overlap", f"{room_label(first)}/{room_label(second)}")


def outer_boundary(shapes: list[Polygon]):
    """Outline of the whole floor: union of the rooms with small gaps closed, courtyards count as outside."""
    if not shapes:
        return None
    union = unary_union([shape.buffer(OUTER_CLOSE_GAP_M / 2) for shape in shapes]).buffer(-OUTER_CLOSE_GAP_M / 2)
    return None if union.is_empty else union.boundary


def _check_entrances(building: dict, polygons: dict[str, Polygon], found: Collector) -> None:
    spaces = {space["id"]: space for space in building["spaces"]}
    outlines: dict[str, object] = {}
    for opening in building["openings"]:
        if OUTSIDE not in opening["space_ids"]:
            continue
        floor_id = opening.get("floor_id")
        if floor_id not in outlines:
            outlines[floor_id] = outer_boundary(
                [polygons[s["id"]] for s in building["spaces"] if s["floor_id"] == floor_id and s["id"] in polygons]
            )
        outline = outlines[floor_id]
        room_id = next((end for end in opening["space_ids"] if end != OUTSIDE), None)
        if outline is None or room_id not in polygons:
            continue
        point = Point(opening["position"])
        if (
            outline.distance(point) > OUTER_WALL_TOLERANCE_M
            or outline.distance(polygons[room_id]) > ADJACENT_DISTANCE_M
        ):
            found.add("entrance_not_on_outer_wall", room_label(spaces[room_id]))


def _check_doors(building: dict, polygons: dict[str, Polygon], found: Collector) -> None:
    spaces = {space["id"]: space for space in building["spaces"]}
    for opening in building["openings"]:
        ends = opening["space_ids"]
        label = "/".join(room_label(spaces[end]) if end in spaces else str(end) for end in ends)
        known = [end for end in ends if end == OUTSIDE or end in spaces]
        if len(known) != 2:
            found.add("door_unknown_room", label)
            continue
        if ends[0] == ends[1]:
            found.add("door_same_room", label)
            continue
        width = opening.get("width_m")
        if width is not None and not PLAUSIBLE_DOOR_WIDTH_M[0] <= width <= PLAUSIBLE_DOOR_WIDTH_M[1]:
            found.add("door_width_implausible", label)
        rooms = [polygons[end] for end in ends if end in polygons]
        if len(rooms) != len([end for end in ends if end != OUTSIDE]):
            continue  # an unusable room is reported on its own
        point = Point(opening["position"])
        if not all(room.distance(point) <= ADJACENT_DISTANCE_M for room in rooms):
            found.add("door_not_on_wall", label)


def _usable_part(building: dict) -> dict:
    """The building without rooms whose outline is unusable (and what points at them), so routing cannot crash."""
    spaces = [space for space in building["spaces"] if _polygon(space) is not None]
    ids = {space["id"] for space in spaces}
    return {
        **building,
        "spaces": spaces,
        "openings": [o for o in building["openings"] if all(end == OUTSIDE or end in ids for end in o["space_ids"])],
        "vertical_connectors": [c for c in building["vertical_connectors"] if all(s in ids for s in c["space_ids"])],
    }


def _check_reachability(building: dict, found: Collector) -> None:
    bm = BuildingMap(building)
    has_entrance = any(OUTSIDE in opening["space_ids"] for opening in building["openings"])
    if not has_entrance:
        found.add("no_entrance")
    if not building["spaces"]:
        return
    graph = bm.graph(step_free=False)
    if len(building["floors"]) > 1 and not building["vertical_connectors"]:
        _check_floors_alone(building, graph, found)
        return
    components = list(nx.connected_components(graph))
    if has_entrance and OUTSIDE in graph:
        reference = next(component for component in components if OUTSIDE in component)
    else:
        reference = max(components, key=len)
    for space in building["spaces"]:
        if space["id"] not in reference:
            found.add("room_unreachable", room_label(space))


def _check_connectivity(building: dict, found: Collector) -> None:
    """Rooms (type room) without any door or connector that room_unreachable did not already report.
    Only degree 0 counts: a room with a single door is normal, so it is never flagged."""
    degree: dict[str, int] = defaultdict(int)
    for opening in building["openings"]:
        for end in opening["space_ids"]:
            degree[end] += 1
    for connector in building["vertical_connectors"]:
        for end in connector["space_ids"]:
            degree[end] += 1
    reported = set(found.items.get("room_unreachable", []))
    for space in building["spaces"]:
        if space.get("type") == "room" and degree[space["id"]] == 0 and room_label(space) not in reported:
            found.add("low_connectivity", room_label(space))


def _check_floors_alone(building: dict, graph, found: Collector) -> None:
    """Without stairs or lifts every floor is checked on its own: rooms must reach an entrance (the outside), or, on a
    floor without one, the biggest group of rooms of that floor, so missing connectors are not reported as doors."""
    components = list(nx.connected_components(graph))
    group_of = {node: index for index, component in enumerate(components) for node in component}
    outside = group_of.get(OUTSIDE)
    for floor in building["floors"]:
        spaces = [space for space in building["spaces"] if space["floor_id"] == floor["id"]]
        has_exit = any(OUTSIDE in o["space_ids"] for o in building["openings"] if o.get("floor_id") == floor["id"])
        if has_exit and outside is not None:
            reference = outside
        else:
            sizes: dict[int, int] = defaultdict(int)
            for space in spaces:
                sizes[group_of[space["id"]]] += 1
            reference = max(sizes, key=sizes.__getitem__) if sizes else None
        for space in spaces:
            if group_of[space["id"]] != reference:
                found.add("room_unreachable", room_label(space))


def _check_connectors(building: dict, found: Collector) -> None:
    levels = {floor["id"]: floor["level"] for floor in building["floors"]}
    spaces = {space["id"]: space for space in building["spaces"]}
    for connector in building["vertical_connectors"]:
        floor_ids, space_ids = connector["floor_ids"], connector["space_ids"]
        stops_ok = len(floor_ids) == len(space_ids) and all(
            space_id in spaces and spaces[space_id]["floor_id"] == floor_id
            for floor_id, space_id in zip(floor_ids, space_ids, strict=False)
        )
        stop_levels = sorted(levels[floor_id] for floor_id in floor_ids if floor_id in levels)
        spanned = {level for level in levels.values() if stop_levels and stop_levels[0] <= level <= stop_levels[-1]}
        if not stops_ok or len(stop_levels) < 2 or spanned != set(stop_levels):
            found.add("connector_missing_stop", connector.get("name") or connector["id"])


def _check_scale(polygons: dict[str, Polygon], found: Collector, trusted: bool = False) -> None:
    if not polygons:
        return
    boxes = [polygon.bounds for polygon in polygons.values()]
    width = max(box[2] for box in boxes) - min(box[0] for box in boxes)
    height = max(box[3] for box in boxes) - min(box[1] for box in boxes)
    if not PLAUSIBLE_FOOTPRINT_M[0] <= max(width, height) <= PLAUSIBLE_FOOTPRINT_M[1]:
        found.add("scale_unusual_known" if trusted else "scale_implausible")


def validate(building: dict, trusted_scale: bool = False) -> Findings:
    """Check a building.json dict. Errors block saving, warnings are only shown.
    trusted_scale: the person gave a length for the scale, so an unusual building size is only a warning."""
    found = Collector()
    try:
        BuildingMap(building)  # fails early on missing keys
        polygons = _check_rooms(building, found)
        _check_overlaps(building, polygons, found)
        _check_doors(building, polygons, found)
        _check_entrances(building, polygons, found)
        _check_connectors(building, found)
        _check_scale(polygons, found, trusted_scale)
        usable = _usable_part(building)
        _check_reachability(usable, found)
        _check_connectivity(usable, found)
        items = found.findings()
        floors = len(building["floors"])
        if floors > 1 and not building["vertical_connectors"]:
            message = CODES["no_vertical_connectors"][1].replace("more than one floor", f"{floors} floors")
            items.append(Finding("error", "no_vertical_connectors", message))
    except (KeyError, TypeError, ValueError, IndexError):
        return Findings([Finding("error", "building_invalid", CODES["building_invalid"][1])])
    return Findings(items)


def describe(findings: Findings, max_items: int = 8) -> str:
    """Findings grouped by code with counts and room refs, e.g. '15 rooms have no way out: 0.06, 0.09, ...'."""
    if not findings.items:
        return "No problems found."
    grouped: dict[str, list[Finding]] = {}
    for finding in findings.items:
        grouped.setdefault(finding.code, []).append(finding)
    lines = []
    for code, group in grouped.items():
        items = [item for finding in group for item in finding.items]
        message = group[0].message
        if items and code in CODES:
            phrases = SINGULAR_PHRASES if len(items) == 1 else PLURAL_PHRASES
            message = CODES[code][1].format(n=len(items), **phrases)
        line = message.rstrip(".")
        if items:
            line += f": {', '.join(items[:max_items])}{', ...' if len(items) > max_items else ''}"
        lines.append(line + ".")
    return " ".join(lines)
