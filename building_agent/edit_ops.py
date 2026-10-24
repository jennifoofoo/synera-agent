"""Edit operations beyond close/reopen/add_door: remove a door, widen a door, move or add an asset, undo snapshots.

Each function mutates the map in place and keeps the two views in sync: `bm.openings` and `bm.data["openings"]`
(and `bm.assets` / `bm.data["assets"]`) hold the very same dict objects. Callers decide when to apply (the
confirmation guard lives in guide_tools); here everything raises MapError when it cannot be done.

Limitation: `BuildingMap.add_door` (starter code, protected) numbers new doors `len(openings) + 1`, which can
collide after a removal. `add_door_safe` avoids that for our own paths; direct calls to `bm.add_door` are not guarded.
Likewise `bm.resolve_space` knows only current asset names; use `resolve_asset` here for old names (aliases)."""

import copy
import math
import re
from dataclasses import dataclass

from shapely.affinity import rotate, translate
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import nearest_points
from shapely.prepared import prep

from building_agent.asset_catalog import catalog_entry
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError

MIN_WIDTH_M = 0.6
MAX_WIDTH_M = 5.0
CLEARANCE_M = 0.05
GRID_STEP_M = 0.25
MAX_GRID_POINTS = 4000
NAME_TAIL = re.compile(r"^(?P<label>.+?) (?P<ref>{ref})(?:-(?P<letter>[A-Z]+))?(?P<tail>\s\(\d+\))?$")


# ---------- shared helpers ----------


def door_label(bm: BuildingMap, opening: dict) -> str:
    sides = " and ".join("outside" if sid == OUTSIDE else bm.spaces[sid]["name"] for sid in opening["space_ids"])
    return f"{opening['kind']} {opening['id']} between {sides}"


def is_entrance(opening: dict) -> bool:
    return OUTSIDE in opening["space_ids"]


def side_id(bm: BuildingMap, reference: str) -> str:
    return OUTSIDE if reference.strip().lower() == OUTSIDE else bm.resolve_space(reference)


def resolve_opening(bm: BuildingMap, element: str, other: str | None = None) -> dict:
    """An opening by id, or by the two rooms it joins (second side may be 'outside' for an entrance)."""
    if other is None:
        if element in bm.openings:
            return bm.openings[element]
        raise MapError(f"{element} is not a door id. Give a door id, or two rooms the door sits between.")
    pair = {side_id(bm, element), side_id(bm, other)}
    found = [opening for opening in bm.openings.values() if set(opening["space_ids"]) == pair]
    if not found:
        raise MapError("There is no door between those two places.")
    if len(found) > 1:
        raise MapError("Several doors join those places, name one by id: " + ", ".join(o["id"] for o in found))
    return found[0]


def next_door_id(bm: BuildingMap, floor_id: str) -> str:
    number = len(bm.openings) + 1
    while f"{floor_id}-O-new{number}" in bm.openings:
        number += 1
    return f"{floor_id}-O-new{number}"


def add_door_safe(bm: BuildingMap, first: str, second: str, step_free: bool = True) -> dict:
    """bm.add_door with an id that never collides. Uses the starter geometry on a scratch map when needed."""
    floor_id = bm.spaces[bm.resolve_space(first)]["floor_id"]
    if f"{floor_id}-O-new{len(bm.openings) + 1}" not in bm.openings:
        return bm.add_door(first, second, step_free)
    scratch = object.__new__(BuildingMap)
    scratch.__dict__.update(bm.__dict__)
    scratch.openings, scratch.data = {}, {**bm.data, "openings": []}
    opening = scratch.add_door(first, second, step_free)
    opening["id"] = next_door_id(bm, floor_id)
    bm.openings[opening["id"]] = opening
    bm.data["openings"].append(opening)
    return opening


# ---------- remove / widen door ----------


def remove_door(bm: BuildingMap, element: str, other: str | None = None) -> dict:
    opening = resolve_opening(bm, element, other)
    if is_entrance(opening):
        remaining = [o for o in bm.openings.values() if is_entrance(o) and o is not opening]
        if not remaining:
            raise MapError(f"{opening['id']} is the last entrance, the building would have no way in.")
    del bm.openings[opening["id"]]
    bm.data["openings"][:] = [item for item in bm.data["openings"] if item is not opening]
    bm.closed.discard(opening["id"])
    removed = getattr(bm, "removed_openings", [])
    bm.removed_openings = [*removed, opening["id"]]
    bm.last_edit = {"action": "remove_door", "id": opening["id"], "opening": opening}
    return bm.last_edit


def widen_door(bm: BuildingMap, element: str, other: str | None, width_m: float | None) -> dict:
    if width_m is None or isinstance(width_m, bool) or not isinstance(width_m, int | float) or math.isnan(width_m):
        raise MapError("widen_door needs width_m, the new width in metres.")
    if not MIN_WIDTH_M <= width_m <= MAX_WIDTH_M:
        raise MapError(f"A door width must be between {MIN_WIDTH_M} and {MAX_WIDTH_M} m, not {width_m}.")
    opening = resolve_opening(bm, element, other)
    old = opening.get("width_m")
    if old is not None and abs(old - width_m) < 1e-9:
        raise MapError(f"{opening['id']} is already {width_m} m wide.")
    opening["width_m"] = float(width_m)
    changes = getattr(bm, "widened_openings", {})
    bm.widened_openings = {**changes, opening["id"]: float(width_m)}
    bm.last_edit = {"action": "widen_door", "id": opening["id"], "old_width_m": old, "width_m": float(width_m)}
    return bm.last_edit


# ---------- move asset ----------


def resolve_asset(bm: BuildingMap, reference: str) -> dict:
    """An asset by id, exact name, or an earlier name (alias) kept after a rename."""
    if reference in bm.assets:
        return bm.assets[reference]
    lowered = reference.strip().lower()
    found = [
        asset
        for asset in bm.assets.values()
        if asset["name"].lower() == lowered or lowered in (alias.lower() for alias in asset.get("aliases", []))
    ]
    if len(found) == 1:
        return found[0]
    if not found:
        raise MapError(f"No asset is called '{reference}'. Try find_asset first.")
    raise MapError(
        f"'{reference}' fits several assets, name one by id: "
        + "; ".join(f"{a['id']} ({a['name']}, {bm.spaces[a['space_id']]['name']})" for a in found[:10])
    )


def asset_shape(asset: dict, x: float, y: float) -> Polygon:
    footprint = asset.get("footprint") or {}
    width, depth = footprint.get("width_m") or 0.5, footprint.get("depth_m") or 0.5
    shape = rotate(box(-width / 2, -depth / 2, width / 2, depth / 2), footprint.get("rotation_deg") or 0)
    return translate(shape, x, y)


def free_point(bm: BuildingMap, asset: dict, space_id: str) -> tuple[float, float]:
    """Representative point if free, else the nearest grid point where the footprint fits and clears the others."""
    room = Polygon(bm.spaces[space_id]["polygon"])
    inside = prep(room)
    others = [
        asset_shape(other, *other["position"])
        for other in bm.assets.values()
        if other["space_id"] == space_id and other is not asset
    ]

    def fits(x: float, y: float) -> bool:
        shape = asset_shape(asset, x, y)
        return inside.contains(shape) and all(shape.distance(other) >= CLEARANCE_M for other in others)

    middle = room.representative_point()
    if fits(middle.x, middle.y):
        return round(middle.x, 3), round(middle.y, 3)
    min_x, min_y, max_x, max_y = room.bounds
    step = max(GRID_STEP_M, max(max_x - min_x, max_y - min_y) / math.sqrt(MAX_GRID_POINTS))
    columns, rows = int((max_x - min_x) / step) + 1, int((max_y - min_y) / step) + 1
    grid = [(min_x + i * step, min_y + j * step) for i in range(columns) for j in range(rows)]
    grid.sort(key=lambda point: math.dist(point, (middle.x, middle.y)))
    fitted = False
    for x, y in grid:
        if inside.contains(Point(x, y)):
            fitted = fitted or inside.contains(asset_shape(asset, x, y))
            if fits(x, y):
                return round(x, 3), round(y, 3)
    if not fitted:
        raise MapError(f"{asset['name']} does not fit into {bm.spaces[space_id]['name']}: the room is too small.")
    raise MapError(f"There is no free spot for {asset['name']} in {bm.spaces[space_id]['name']}.")


def letter_name(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    text = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        text = chr(65 + rest) + text
    return text


def letter_index(letter: str) -> int:
    value = 0
    for char in letter:
        value = value * 26 + ord(char) - 64
    return value - 1


def split_name(name: str, ref: str) -> tuple[str, str | None, str] | None:
    match = re.match(NAME_TAIL.pattern.replace("{ref}", re.escape(ref)), name)
    return (match["label"], match["letter"], match["tail"] or "") if match else None


def join_name(label: str, ref: str, letter: str | None, tail: str) -> str:
    return f"{label} {ref}" + (f"-{letter}" if letter else "") + tail


def room_ref(bm: BuildingMap, space_id: str) -> str:
    space = bm.spaces[space_id]
    return space.get("ref") or space["name"]


def rename(asset: dict, new_name: str) -> None:
    if new_name != asset["name"]:
        aliases = asset.setdefault("aliases", [])
        if asset["name"] not in aliases:
            aliases.append(asset["name"])
        asset["name"] = new_name


def siblings(bm: BuildingMap, space_id: str, asset_type: str, skip: dict) -> list[dict]:
    found = [a for a in bm.assets.values() if a["space_id"] == space_id and a["type"] == asset_type and a is not skip]
    return sorted(found, key=lambda asset: asset["id"])


# ---------- placement with a hint ----------

WALL_GAP_M = 0.05
EXACT_TOLERANCE_M = 0.1
MIN_WALL_M = 0.5
MAX_WALL_TURN_DEG = 80.0
WALL_TIE_DEG = 10.0
MAX_HINT_POINTS = 10000
COMPASS = {"N": (0.0, 1.0), "S": (0.0, -1.0), "E": (1.0, 0.0), "W": (-1.0, 0.0)}
ANCHORS = {
    "NW": ("N", "W"),
    "NE": ("N", "E"),
    "SW": ("S", "W"),
    "SE": ("S", "E"),
    "N": ("N",),
    "S": ("S",),
    "E": ("E",),
    "W": ("W",),
    "CENTER": (),
}
ANCHOR_ALIASES = {"CENTRE": "CENTER", "MIDDLE": "CENTER", "C": "CENTER"} | {
    word: letters
    for letters, word in {
        "NW": "NORTHWEST",
        "NE": "NORTHEAST",
        "SW": "SOUTHWEST",
        "SE": "SOUTHEAST",
        "N": "NORTH",
        "S": "SOUTH",
        "E": "EAST",
        "W": "WEST",
    }.items()
}
ANCHOR_WORDS = {
    "NW": "north-west corner",
    "NE": "north-east corner",
    "SW": "south-west corner",
    "SE": "south-east corner",
    "N": "north wall",
    "S": "south wall",
    "E": "east wall",
    "W": "west wall",
    "CENTER": "centre of the room",
}
WALL_WORDS = {"N": "north", "S": "south", "E": "east", "W": "west"}
HINT_KEYS = {"anchor", "near", "point", "rotation_deg", "floor_id"}


def number(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise MapError(f"{what} must be a finite number.")
    return float(value)


def normal_angle(degrees: float) -> float:
    """Rotation in (-180, 180], one decimal."""
    turned = degrees % 360
    return round(turned - 360 if turned > 180 else turned, 1) or 0.0


def parse_hint(hint: dict) -> tuple[str, object, float | None]:
    """(mode, value, rotation_deg). Mode is anchor, near, point or rotate."""
    if not isinstance(hint, dict):
        raise MapError("hint must be an object such as {'anchor': 'NW'}, {'near': 'Room 1.02'} or {'point': [x, y]}.")
    unknown = set(hint) - HINT_KEYS
    if unknown:
        raise MapError(f"Unknown hint keys {sorted(unknown)}. Use anchor, near, point, rotation_deg.")
    modes = [key for key in ("anchor", "near", "point") if hint.get(key) is not None]
    if len(modes) > 1:
        raise MapError("A hint takes only one of anchor, near and point.")
    rotation = hint.get("rotation_deg")
    rotation = None if rotation is None else normal_angle(number(rotation, "rotation_deg"))
    if not modes:
        if rotation is None:
            raise MapError("The hint is empty. Give an anchor, a near target, a point or a rotation_deg.")
        return "rotate", None, rotation
    mode = modes[0]
    if mode == "anchor":
        key = str(hint["anchor"]).strip().upper().replace("-", "").replace(" ", "")
        key = ANCHOR_ALIASES.get(key, key)
        if key not in ANCHORS:
            raise MapError(f"Unknown anchor '{hint['anchor']}'. Use NW, NE, SW, SE, N, S, E, W or center.")
        return mode, key, rotation
    if mode == "near":
        if not isinstance(hint["near"], str) or not hint["near"].strip():
            raise MapError("near needs a room or asset name or id.")
        return mode, hint["near"].strip(), rotation
    point = hint["point"]
    if not isinstance(point, list | tuple) or len(point) != 2:
        raise MapError("point must be [x, y] in metres.")
    return mode, (number(point[0], "point x"), number(point[1], "point y")), rotation


def room_at(bm: BuildingMap, point, floor_id: str) -> str | None:
    """The smallest space on this floor whose polygon contains the point, or None."""
    x, y = number(point[0], "point x"), number(point[1], "point y")
    spot = Point(x, y)
    found = []
    for space in bm.spaces.values():
        if space["floor_id"] == floor_id:
            polygon = Polygon(space["polygon"])
            if polygon.contains(spot):
                found.append((polygon.area, space["id"]))
    return min(found)[1] if found else None


def wall_edges(room: Polygon) -> list[dict]:
    """Counter-clockwise edges with the outward unit normal (+y is north)."""
    ring = list(orient(room, 1.0).exterior.coords)[:-1]
    edges = []
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length > 1e-9:
            edges.append(
                {
                    "a": start,
                    "b": end,
                    "length": length,
                    "theta": math.degrees(math.atan2(dy, dx)),
                    "out": (dy / length, -dx / length),
                }
            )
    return edges


def pick_walls(edges: list[dict], letter: str) -> list[dict]:
    """Edges whose outward normal points closest to the compass direction, longest first."""
    direction = COMPASS[letter]

    def turn(edge: dict) -> float:
        dot = edge["out"][0] * direction[0] + edge["out"][1] * direction[1]
        return math.degrees(math.acos(max(-1.0, min(1.0, dot))))

    usable = [edge for edge in edges if edge["length"] >= MIN_WALL_M] or edges
    best = min(turn(edge) for edge in usable)
    if best > MAX_WALL_TURN_DEG:
        raise MapError(f"The room has no {WALL_WORDS[letter]} wall.")
    tied = [edge for edge in usable if turn(edge) <= best + WALL_TIE_DEG]
    return sorted(tied, key=lambda edge: -edge["length"])


def back_rotation(walls: list[dict]) -> float:
    """The asset's back goes against the longest wall (north/south first on a tie)."""
    return normal_angle(max(walls, key=lambda wall: round(wall["length"], 1))["theta"])


def choose_walls(room: Polygon, edges: list[dict], letters: tuple, width: float, depth: float, rotation) -> list[dict]:
    """One wall per letter. A corner takes the crossing that lies furthest into the compass direction."""
    options = [pick_walls(edges, letter) for letter in letters]
    if len(options) == 1:
        return [options[0][0]]
    best, best_score = [options[0][0], options[1][0]], None
    heading = (COMPASS[letters[0]][0] + COMPASS[letters[1]][0], COMPASS[letters[0]][1] + COMPASS[letters[1]][1])
    for first in options[0]:
        for second in options[1]:
            if first is second:
                continue
            turn = rotation if rotation is not None else back_rotation([first, second])
            (x, y), _ = anchor_point([first, second], width, depth, turn)
            score = (room.contains(Point(x, y)), x * heading[0] + y * heading[1])
            if best_score is None or score > best_score:
                best, best_score = [first, second], score
    return best


def dims(asset: dict) -> tuple[float, float]:
    footprint = asset.get("footprint") or {}
    return footprint.get("width_m") or 0.5, footprint.get("depth_m") or 0.5


def half_extent(width: float, depth: float, rotation: float, direction: tuple[float, float]) -> float:
    angle = math.radians(rotation)
    along = (math.cos(angle), math.sin(angle))
    across = (-math.sin(angle), math.cos(angle))
    return width / 2 * abs(along[0] * direction[0] + along[1] * direction[1]) + depth / 2 * abs(
        across[0] * direction[0] + across[1] * direction[1]
    )


def anchor_point(
    walls: list[dict], width: float, depth: float, rotation: float
) -> tuple[tuple[float, float], list[str]]:
    """Where the footprint centre goes so it sits GAP from the wall(s); a corner is two offset walls crossing."""
    notes: list[str] = []
    offsets = []
    for wall in walls:
        inward = (-wall["out"][0], -wall["out"][1])
        reach = half_extent(width, depth, rotation, inward) + WALL_GAP_M
        offsets.append((inward, wall["a"][0] * inward[0] + wall["a"][1] * inward[1] + reach, wall, reach))
    if len(offsets) == 2:
        (n1, c1, _, _), (n2, c2, _, _) = offsets
        det = n1[0] * n2[1] - n1[1] * n2[0]
        if abs(det) > 0.2:
            return ((c1 * n2[1] - c2 * n1[1]) / det, (n1[0] * c2 - n2[0] * c1) / det), notes
        notes.append("the two walls are not at an angle, so only the long one is used")
        offsets = offsets[:1]
    inward, _, wall, reach = offsets[0]
    mid = ((wall["a"][0] + wall["b"][0]) / 2, (wall["a"][1] + wall["b"][1]) / 2)
    return (mid[0] + inward[0] * reach, mid[1] + inward[1] * reach), notes


def nearest_fit(
    probe: dict, room: Polygon, others: list[Polygon], target: tuple[float, float], name: str, room_name: str
) -> tuple[float, float]:
    """The point nearest to `target` where the footprint lies inside the room and clears the others."""
    inside = prep(room)
    min_x, min_y, max_x, max_y = room.bounds
    step = max(0.1, math.sqrt(max((max_x - min_x) * (max_y - min_y), 1e-6) / MAX_HINT_POINTS))
    tx, ty = target
    left, right = math.ceil((tx - min_x) / step), math.ceil((max_x - tx) / step)
    down, up = math.ceil((ty - min_y) / step), math.ceil((max_y - ty) / step)
    grid = [(tx + i * step, ty + j * step) for i in range(-left, right + 1) for j in range(-down, up + 1)]
    grid.sort(key=lambda point: (point[0] - tx) ** 2 + (point[1] - ty) ** 2)
    fitted = False
    for x, y in grid:
        x, y = round(x, 3), round(y, 3)
        shape = asset_shape(probe, x, y)
        if inside.contains(shape):
            fitted = True
            if all(shape.distance(other) >= CLEARANCE_M for other in others):
                return x, y
    if not fitted:
        raise MapError(f"{name} does not fit into {room_name}: the room is too small.")
    raise MapError(f"There is no free spot for {name} in {room_name}.")


def resolve_near(bm: BuildingMap, reference: str) -> tuple[str, str]:
    """('asset', asset id) or ('space', space id) for a near target."""
    try:
        return "asset", resolve_asset(bm, reference)["id"]
    except MapError as error:
        if "several assets" in str(error):
            raise
    return "space", bm.resolve_space(reference)


def place(bm: BuildingMap, asset: dict, space_id: str, hint: dict) -> dict:
    """Choose position and rotation for `asset` in `space_id` from a hint. Changes nothing.

    Returns {mode, requested, position, rotation_deg, exact, distance_m, gaps, notes, ...}. When the exact spot is
    blocked or the room is not a rectangle, the nearest valid point is used and `exact` is False."""
    mode, value, rotation = parse_hint(hint)
    space = bm.spaces[space_id]
    room = Polygon(space["polygon"])
    others = [
        asset_shape(other, *other["position"])
        for other in bm.assets.values()
        if other["space_id"] == space_id and other is not asset
    ]
    width, depth = dims(asset)
    current = (asset.get("footprint") or {}).get("rotation_deg") or 0.0
    notes: list[str] = []
    near_shape = None
    near_name = None
    walls: list[dict] = []
    if mode == "anchor":
        edges = wall_edges(room)
        walls = choose_walls(room, edges, ANCHORS[value], width, depth, rotation) if ANCHORS[value] else []
        turns = [rotation] if rotation is not None else [back_rotation(walls) if walls else current]
    else:
        turns = [rotation if rotation is not None else current]
    if rotation is None:
        turns.append(normal_angle(turns[0] + 90))

    def candidate(turn: float) -> tuple[tuple[float, float], list[str]]:
        nonlocal near_shape, near_name
        if mode == "anchor":
            if not walls:
                middle = room.centroid if room.contains(room.centroid) else room.representative_point()
                return (middle.x, middle.y), []
            return anchor_point(walls, width, depth, turn)
        if mode == "point":
            if not room.contains(Point(value)):
                raise MapError(f"The point ({value[0]:g}, {value[1]:g}) is not inside {space['name']}.")
            return value, []
        if mode == "near":
            kind, ref = resolve_near(bm, value)
            if kind == "asset":
                other = bm.assets[ref]
                if other is asset:
                    raise MapError("An asset cannot be placed next to itself.")
                if other["space_id"] != space_id:
                    raise MapError(
                        f"{other['name']} is in {bm.spaces[other['space_id']]['name']}, not in {space['name']}."
                    )
                near_shape, near_name = asset_shape(other, *other["position"]), other["name"]
                return tuple(other["position"]), []
            neighbour = Polygon(bm.spaces[ref]["polygon"])
            near_name = bm.spaces[ref]["name"]
            if ref == space_id or neighbour.is_empty:
                return (room.representative_point().x, room.representative_point().y), []
            edge, _ = nearest_points(room, neighbour)
            heart = room.representative_point()
            pull = max(width, depth) / 2 + WALL_GAP_M
            gap = math.dist((edge.x, edge.y), (heart.x, heart.y)) or 1.0
            ratio = min(1.0, pull / gap)
            return (edge.x + (heart.x - edge.x) * ratio, edge.y + (heart.y - edge.y) * ratio), []
        if asset.get("space_id") == space_id and asset.get("position"):
            return tuple(asset["position"]), []
        middle = room.representative_point()
        return (middle.x, middle.y), []

    failure = None
    for turn in turns:
        wanted, extra = candidate(turn)
        probe = {**asset, "footprint": {**(asset.get("footprint") or {}), "rotation_deg": turn}}
        try:
            x, y = nearest_fit(probe, room, others, wanted, asset["name"], space["name"])
        except MapError as error:
            failure = failure or error
            continue
        shape = asset_shape(probe, x, y)
        notes = extra + (["turned 90 degrees to fit"] if turn != turns[0] else [])
        gaps = {
            letter: round(shape.distance(LineString([wall["a"], wall["b"]])), 2)
            for letter, wall in zip(ANCHORS.get(value, ()), walls, strict=False)
        }
        distance = math.dist((x, y), wanted)
        exact = distance <= EXACT_TOLERANCE_M or mode in ("near", "rotate")
        if mode == "anchor" and not exact and not room_is_rectangle(room):
            notes.append("the room is not a simple rectangle")
        result = {
            "mode": mode,
            "requested": value if mode in ("anchor", "near") else None,
            "position": [x, y],
            "rotation_deg": turn,
            "exact": exact,
            "distance_m": round(distance, 2),
            "gaps": gaps,
            "notes": notes,
        }
        if mode == "anchor":
            result["anchor"] = value
        if mode == "point":
            result["point"] = [round(value[0], 3), round(value[1], 3)]
        if mode == "near":
            result["near"] = near_name
            result["gap_m"] = round(shape.distance(near_shape), 2) if near_shape is not None else None
        return result
    raise failure


def room_is_rectangle(room: Polygon) -> bool:
    return abs(room.area - room.minimum_rotated_rectangle.area) < 0.01 * room.area


# ---------- naming ----------


def arrive(bm: BuildingMap, asset: dict, target: str, label: str, tail: str) -> tuple[str, list[dict]]:
    """Name for an asset arriving in `target` (letters per room and type) and the siblings that were renamed.

    A lone asset has no letter. Arriving next to one turns that one into -A and the newcomer into -B. Otherwise the
    newcomer takes the letter after the highest one present."""
    renamed: list[dict] = []
    new_ref = room_ref(bm, target)
    present = siblings(bm, target, asset["type"], asset)
    letters = [split_name(a["name"], new_ref) for a in present]
    new_letter = None
    if len(present) == 1 and letters[0] and letters[0][1] is None:
        sibling = present[0]
        before = sibling["name"]
        rename(sibling, join_name(letters[0][0], new_ref, "A", letters[0][2]))
        renamed.append({"id": sibling["id"], "old": before, "new": sibling["name"]})
        new_letter = "B"
    elif present:
        highest = max((letter_index(p[1]) for p in letters if p and p[1]), default=0)
        new_letter = letter_name(highest + 1)
    taken = {a["name"] for a in bm.assets.values() if a is not asset}
    while join_name(label, new_ref, new_letter, tail) in taken:
        new_letter = letter_name(letter_index(new_letter or "A") + 1)
    return join_name(label, new_ref, new_letter, tail), renamed


def depart(bm: BuildingMap, asset: dict, source: str) -> list[dict]:
    """A single remaining sibling in the room that is left loses its letter."""
    renamed = []
    old_ref = room_ref(bm, source)
    left = siblings(bm, source, asset["type"], asset)
    if len(left) == 1:
        remaining = split_name(left[0]["name"], old_ref)
        if remaining and remaining[1]:
            before = left[0]["name"]
            rename(left[0], join_name(remaining[0], old_ref, None, remaining[2]))
            renamed.append({"id": left[0]["id"], "old": before, "new": left[0]["name"]})
    return renamed


def view(asset: dict) -> dict:
    footprint = asset.get("footprint") or {}
    return {
        "space_id": asset["space_id"],
        "floor_id": asset["floor_id"],
        "position": list(asset["position"]),
        "name": asset["name"],
        "rotation_deg": footprint.get("rotation_deg"),
    }


# ---------- move asset ----------


def move_target(bm: BuildingMap, asset: dict, to_space: str | None, hint: dict | None) -> str:
    if to_space is not None:
        return bm.resolve_space(to_space)
    if not hint:
        raise MapError("move_asset needs a target room or a hint.")
    mode, value, _ = parse_hint(hint)
    if mode == "point":
        floor = hint.get("floor_id") or asset["floor_id"]
        found = room_at(bm, value, floor)
        if found is None:
            raise MapError(f"No room on that floor contains the point ({value[0]:g}, {value[1]:g}).")
        return found
    if mode == "near":
        kind, ref = resolve_near(bm, value)
        if kind == "asset":
            return bm.assets[ref]["space_id"]
    return asset["space_id"]


def move_asset(bm: BuildingMap, asset_ref: str, to_space: str | None = None, hint: dict | None = None) -> dict:
    """Move one asset to another room, or to a chosen spot (`hint`) in the same or another room.

    Id stays; the name gets the new room ref and letter only when the room changes.
    Letter rule per (room, type): a lone asset has no letter. Arriving in a room with one lone asset turns that one
    into -A and the newcomer into -B. Otherwise the newcomer takes the letter after the highest one present.
    Leaving a room never re-letters siblings, except that a single remaining sibling loses its letter."""
    asset = resolve_asset(bm, asset_ref)
    target = move_target(bm, asset, to_space, hint)
    source = asset["space_id"]
    if target == source and not hint:
        raise MapError(f"{asset['name']} is already in {bm.spaces[source]['name']}.")
    old_position, old_rotation = list(asset["position"]), (asset.get("footprint") or {}).get("rotation_deg")
    if hint:
        placement = place(bm, asset, target, hint)
        x, y = placement["position"]
    else:
        placement = None
        x, y = free_point(bm, asset, target)
    old_name, renamed = asset["name"], []

    if target != source:
        parsed = split_name(old_name, room_ref(bm, source))
        label, tail = (parsed[0], parsed[2]) if parsed else (old_name, "")
        new_name, renamed = arrive(bm, asset, target, label, tail)
        renamed += depart(bm, asset, source)
        rename(asset, new_name)
    else:
        new_name = old_name
    asset["space_id"], asset["floor_id"] = target, bm.spaces[target]["floor_id"]
    asset["position"] = [x, y]
    if placement is not None and placement["rotation_deg"] != old_rotation:
        asset.setdefault("footprint", {})["rotation_deg"] = placement["rotation_deg"]
    bm.located_asset_ids = []
    moved = getattr(bm, "moved_assets", {})
    bm.moved_assets = {**moved, asset["id"]: view(asset)}
    bm.last_edit = {
        "action": "move_asset",
        "id": asset["id"],
        "old_name": old_name,
        "new_name": new_name,
        "from_space": source,
        "to_space": target,
        "position": [x, y],
        "old_position": old_position,
        "old_rotation_deg": old_rotation,
        "rotation_deg": (asset.get("footprint") or {}).get("rotation_deg"),
        "renamed_siblings": renamed,
        "placement": placement,
    }
    return bm.last_edit


# ---------- add asset ----------

ASSET_ID = re.compile(r"^(?P<prefix>.+)-A(?P<number>\d+)$")


def next_asset_id(bm: BuildingMap) -> str:
    """Building prefix + '-A%05d' with the highest number plus one."""
    parsed = [m for m in (ASSET_ID.match(asset_id) for asset_id in bm.assets) if m]
    if parsed:
        prefixes = [m["prefix"] for m in parsed]
        prefix = max(set(prefixes), key=prefixes.count)
        number_ = max(int(m["number"]) for m in parsed if m["prefix"] == prefix)
    else:
        first = next(iter(bm.spaces))
        prefix, number_ = first.split("-F")[0] if "-F" in first else first, 0
    new_id = f"{prefix}-A{number_ + 1:05d}"
    while new_id in bm.assets:
        number_ += 1
        new_id = f"{prefix}-A{number_ + 1:05d}"
    return new_id


def add_asset(
    bm: BuildingMap, asset_type: str, to_space: str, hint: dict | None = None, name: str | None = None
) -> dict:
    """Add a new asset of a catalogue type to a room, optionally at a hinted spot. Id and name follow the data scheme."""
    key, entry = catalog_entry(asset_type)
    target = bm.resolve_space(to_space)
    space = bm.spaces[target]
    asset = {
        "id": next_asset_id(bm),
        "name": entry["label"],
        "category": entry["category"],
        "type": key,
        "space_id": target,
        "floor_id": space["floor_id"],
        "position": [0.0, 0.0],
        "footprint": {"width_m": entry["width_m"], "depth_m": entry["depth_m"], "rotation_deg": 0},
        "source": "generated",
    }
    if hint:
        placement = place(bm, asset, target, hint)
        x, y = placement["position"]
        asset["footprint"]["rotation_deg"] = placement["rotation_deg"]
    else:
        placement = None
        x, y = free_point(bm, asset, target)
    asset["position"] = [x, y]
    renamed: list[dict] = []
    if name:
        if any(other["name"].lower() == name.strip().lower() for other in bm.assets.values()):
            raise MapError(f"An asset called '{name}' exists already.")
        asset["name"] = name.strip()
    else:
        asset["name"], renamed = arrive(bm, asset, target, entry["label"], "")
    bm.assets[asset["id"]] = asset
    bm.data["assets"].append(asset)
    bm.located_asset_ids = []
    added = getattr(bm, "added_assets", {})
    bm.added_assets = {**added, asset["id"]: {**view(asset), "type": key, "category": entry["category"]}}
    bm.removed_assets = [item for item in getattr(bm, "removed_assets", []) if item != asset["id"]]
    bm.last_edit = {
        "action": "add_asset",
        "id": asset["id"],
        "name": asset["name"],
        "type": key,
        "to_space": target,
        "position": [x, y],
        "rotation_deg": asset["footprint"]["rotation_deg"],
        "width_m": entry["width_m"],
        "depth_m": entry["depth_m"],
        "renamed_siblings": renamed,
        "placement": placement,
    }
    return bm.last_edit


# ---------- undo snapshots ----------


@dataclass
class Snapshot:
    """What an edit can change, copied before it is applied."""

    label: str
    assets: list
    openings: list
    closed: set
    moved_assets: dict
    added_assets: dict
    removed_assets: list
    removed_openings: list
    widened_openings: dict
    after_signature: tuple | None = None  # building_signature right after the edit this snapshot undoes


def take_snapshot(bm: BuildingMap, label: str = "") -> Snapshot:
    return Snapshot(
        label,
        copy.deepcopy(bm.data["assets"]),
        copy.deepcopy(bm.data["openings"]),
        set(bm.closed),
        copy.deepcopy(getattr(bm, "moved_assets", {})),
        copy.deepcopy(getattr(bm, "added_assets", {})),
        list(getattr(bm, "removed_assets", [])),
        list(getattr(bm, "removed_openings", [])),
        dict(getattr(bm, "widened_openings", {})),
    )


def _reuse_dicts(current: dict, restored: list) -> list:
    """Refill the existing dict objects in place, so anything that holds one of them (routing indexes) stays valid."""
    out = []
    for item in restored:
        live = current.get(item["id"])
        if live is None:
            out.append(item)
        else:
            live.clear()
            live.update(item)
            out.append(live)
    return out


def restore_snapshot(bm: BuildingMap, snapshot: Snapshot) -> None:
    """Put the assets, doors and closures back in place; bm.* and bm.data keep sharing the same dict objects.

    Assets whose room, spot, rotation or name differ from before are listed in moved_assets with their restored values,
    and assets that no longer exist in removed_assets, so a page can redraw them."""
    before = {asset["id"]: view(asset) for asset in bm.data["assets"]}
    assets, openings = copy.deepcopy(snapshot.assets), copy.deepcopy(snapshot.openings)
    assets = _reuse_dicts(bm.assets, assets)
    openings = _reuse_dicts(bm.openings, openings)
    bm.data["assets"][:] = assets
    bm.assets.clear()
    bm.assets.update({asset["id"]: asset for asset in assets})
    bm.data["openings"][:] = openings
    bm.openings.clear()
    bm.openings.update({opening["id"]: opening for opening in openings})
    bm.closed.clear()
    bm.closed.update(snapshot.closed)
    moved = copy.deepcopy(snapshot.moved_assets)
    for asset in assets:
        if asset["id"] in before and view(asset) != before[asset["id"]]:
            moved[asset["id"]] = view(asset)
    bm.moved_assets = moved
    bm.added_assets = copy.deepcopy(snapshot.added_assets)
    gone = set(before) - set(bm.assets)
    bm.removed_assets = sorted((set(snapshot.removed_assets) | gone) - set(bm.assets))
    bm.removed_openings = list(snapshot.removed_openings)
    bm.widened_openings = dict(snapshot.widened_openings)
    bm.located_asset_ids = []
    bm.last_route = None
    bm.last_edit = {"action": "undo"}
