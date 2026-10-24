"""Edit operations beyond close/reopen/add_door: remove a door, widen a door, move an asset.

Each function mutates the map in place and keeps the two views in sync: `bm.openings` and `bm.data["openings"]`
(and `bm.assets` / `bm.data["assets"]`) hold the very same dict objects. Callers decide when to apply (the
confirmation guard lives in guide_tools); here everything raises MapError when it cannot be done.

Limitation: `BuildingMap.add_door` (starter code, protected) numbers new doors `len(openings) + 1`, which can
collide after a removal. `add_door_safe` avoids that for our own paths; direct calls to `bm.add_door` are not guarded.
Likewise `bm.resolve_space` knows only current asset names; use `resolve_asset` here for old names (aliases)."""

import math
import re

from shapely.affinity import rotate, translate
from shapely.geometry import Point, Polygon, box
from shapely.prepared import prep

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


def move_asset(bm: BuildingMap, asset_ref: str, to_space: str) -> dict:
    """Move one asset to another room. Id stays; name gets the new room ref and letter.

    Letter rule per (room, type): a lone asset has no letter. Arriving in a room with one lone asset turns that one
    into -A and the newcomer into -B. Otherwise the newcomer takes the letter after the highest one present.
    Leaving a room never re-letters siblings, except that a single remaining sibling loses its letter."""
    asset = resolve_asset(bm, asset_ref)
    target = bm.resolve_space(to_space)
    source = asset["space_id"]
    if target == source:
        raise MapError(f"{asset['name']} is already in {bm.spaces[source]['name']}.")
    x, y = free_point(bm, asset, target)
    old_name, renamed = asset["name"], []

    old_ref, new_ref = room_ref(bm, source), room_ref(bm, target)
    parsed = split_name(old_name, old_ref)
    label, tail = (parsed[0], parsed[2]) if parsed else (old_name, "")
    present = siblings(bm, target, asset["type"], asset)
    letters = [split_name(a["name"], new_ref) for a in present]
    new_letter = None
    if len(present) == 1 and letters[0] and letters[0][1] is None:
        sibling = present[0]
        rename(sibling, join_name(letters[0][0], new_ref, "A", letters[0][2]))
        renamed.append({"id": sibling["id"], "old": sibling["aliases"][-1], "new": sibling["name"]})
        new_letter = "B"
    elif present:
        highest = max((letter_index(p[1]) for p in letters if p and p[1]), default=0)
        new_letter = letter_name(highest + 1)
    taken = {a["name"] for a in bm.assets.values() if a is not asset}
    while join_name(label, new_ref, new_letter, tail) in taken:
        new_letter = letter_name(letter_index(new_letter or "A") + 1)
    new_name = join_name(label, new_ref, new_letter, tail)

    left = siblings(bm, source, asset["type"], asset)
    if len(left) == 1:
        remaining = split_name(left[0]["name"], old_ref)
        if remaining and remaining[1]:
            before = left[0]["name"]
            rename(left[0], join_name(remaining[0], old_ref, None, remaining[2]))
            renamed.append({"id": left[0]["id"], "old": before, "new": left[0]["name"]})

    rename(asset, new_name)
    asset["space_id"], asset["floor_id"] = target, bm.spaces[target]["floor_id"]
    asset["position"] = [x, y]
    bm.located_asset_ids = []
    moved = getattr(bm, "moved_assets", {})
    bm.moved_assets = {
        **moved,
        asset["id"]: {"space_id": target, "floor_id": asset["floor_id"], "position": [x, y], "name": new_name},
    }
    bm.last_edit = {
        "action": "move_asset",
        "id": asset["id"],
        "old_name": old_name,
        "new_name": new_name,
        "from_space": source,
        "to_space": target,
        "position": [x, y],
        "renamed_siblings": renamed,
    }
    return bm.last_edit
