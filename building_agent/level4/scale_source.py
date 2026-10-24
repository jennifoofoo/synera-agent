"""Where the scale of a plan can come from besides a printed bar or a length the person gives: a building.json that
travels with the plan. Synera said the scale is "provided in the plan/building.json" but not under which field, so the
lookup is tolerant: many spellings, nested under building / floors / plan(s), per floor or global, numbers or numeric
strings (also "0.02 m/px" or "50 px/m"). Everything is checked against a sane range and the key that was used is
reported, so the card can say where the scale came from. Pure functions, no I/O except `load_building_json`."""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

MIN_VALUE, MAX_VALUE = 0.001, 1000.0
MAX_JSON_BYTES = 5 * 1024 * 1024
MAX_DEPTH = 5
M_PER_PX_KEYS = {
    "m_per_px",
    "m_per_pixel",
    "metres_per_pixel",
    "meters_per_pixel",
    "metre_per_pixel",
    "meter_per_pixel",
    "metres_per_px",
    "meters_per_px",
    "mpp",
}
PX_PER_M_KEYS = {
    "px_per_m",
    "px_per_metre",
    "px_per_meter",
    "pixels_per_m",
    "pixels_per_metre",
    "pixels_per_meter",
    "pixel_per_m",
    "pixel_per_metre",
    "pixel_per_meter",
    "ppm",
}
# plain names: a value of 1 or more is read as pixels per metre, below 1 as metres per pixel (a plan is never
# drawn at less than one pixel per metre of a real building, nor at more than a metre per pixel)
AMBIGUOUS_KEYS = {"scale", "resolution", "plan_scale", "image_scale", "drawing_scale"}
WIDTH_KEYS = {
    "width_m",
    "width_metres",
    "width_meters",
    "building_width_m",
    "building_width",
    "extent_x_m",
    "size_x_m",
    "length_x_m",
}
SIZE_KEYS = {"size_m", "extent_m", "dimensions_m", "bbox_size_m"}
LEVEL_KEYS = ("level", "floor_level", "floor")
_FLOOR_NAME = re.compile(r"^(?:(?:floor|level|f|og|eg)[ _-]?)?(-?\d+)$", re.IGNORECASE)
_UNIT_M_PER_PX = re.compile(r"m(?:etres?|eters?)?\s*(?:/|per)\s*p(?:x|ixels?)\b", re.IGNORECASE)
_UNIT_PX_PER_M = re.compile(r"p(?:x|ixels?)\s*(?:/|per)\s*m(?:etres?|eters?)?\b", re.IGNORECASE)
_NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?(?:e[-+]?\d+)?", re.IGNORECASE)


@dataclass
class ScaleHit:
    metres_per_px: float
    key: str  # where it was found, e.g. "floors[0].px_per_m"
    reading: str  # "m_per_px", "px_per_m" or "guessed from size" (plain names)


@dataclass
class WidthHit:
    metres: float
    key: str


def load_building_json(path: Path) -> dict | list | None:
    """The parsed file, or None when it is missing, too big or not JSON (never raises)."""
    try:
        file = Path(path)
        if not file.is_file() or file.stat().st_size > MAX_JSON_BYTES:
            return None
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict | list) else None


def _normal(key: object) -> str:
    return re.sub(r"[\s\-/]+", "_", str(key).strip().lower())


def _number(value: object) -> tuple[float, str | None] | None:
    """(number, unit hint 'm_per_px' | 'px_per_m' | None) of an int, float or numeric string; None if not finite."""
    if isinstance(value, bool):
        return None
    hint = None
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str) and len(value) <= 60:
        match = _NUMBER.search(value)
        if match is None:
            return None
        try:
            number = float(match.group(0).replace(",", "."))
        except ValueError:
            return None
        hint = "m_per_px" if _UNIT_M_PER_PX.search(value) else "px_per_m" if _UNIT_PX_PER_M.search(value) else None
    else:
        return None
    return (number, hint) if math.isfinite(number) else None


def _floor_of(key: object, node: object) -> int | None:
    """The floor level a dict entry stands for (its own level field, or a floor-like dict key), else None."""
    if isinstance(node, dict):
        for name in LEVEL_KEYS:
            value = node.get(name)
            if isinstance(value, int | float) and not isinstance(value, bool) and float(value) == int(value):
                return int(value)
    match = _FLOOR_NAME.match(key.strip()) if isinstance(key, str) else None
    return int(match.group(1)) if match else None


def _walk(node: object, path: str, floor: int | None, depth: int):
    """Yield (path, key, value, floor) for every entry; `floor` is the level of the closest floor-like parent."""
    if depth > MAX_DEPTH:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            yield here, key, value, floor
            child_floor = _floor_of(key, value) if isinstance(value, dict) else None
            yield from _walk(value, here, child_floor if child_floor is not None else floor, depth + 1)
    elif isinstance(node, list):
        for index, value in enumerate(node[:200]):
            here = f"{path}[{index}]"
            child_floor = _floor_of(None, value) if isinstance(value, dict) else None
            yield from _walk(value, here, child_floor if child_floor is not None else floor, depth + 1)


def _candidate(key: object, value: object) -> tuple[float, str, int] | None:
    """(metres per pixel, reading, explicitness rank) when `key` names a scale and the value is sane."""
    name = _normal(key)
    parsed = _number(value)
    if parsed is None:
        return None
    number, hint = parsed
    if name in M_PER_PX_KEYS:
        reading, rank = "m_per_px", 0
    elif name in PX_PER_M_KEYS:
        reading, rank = "px_per_m", 0
    elif name in AMBIGUOUS_KEYS:
        reading, rank = hint or ("px_per_m" if number >= 1 else "m_per_px"), 1
        if hint is None:
            reading += " (guessed from size)"
    else:
        return None
    if not MIN_VALUE <= number <= MAX_VALUE:
        return None
    metres = number if reading.startswith("m_per_px") else 1.0 / number
    return (metres, reading, rank) if math.isfinite(metres) and metres > 0 else None


def find_scale(data: object, level: int | None = None) -> ScaleHit | None:
    """The scale (metres per pixel) a building.json gives for floor `level` (any floor when None), or None.

    Precedence: a value under the wanted floor beats a global one, an explicit unit name (m_per_px, px_per_m, ...)
    beats a plain name (scale, resolution), then the shallower key, then the first one in the file. A value that is
    not a finite number in 0.001..1000 is skipped, so a bad floor value falls back to the global one."""
    best: tuple[tuple, ScaleHit] | None = None
    for order, (path, key, value, floor) in enumerate(_walk(data, "", None, 0)):
        if level is not None and floor is not None and floor != level:
            continue
        found = _candidate(key, value)
        if found is None:
            continue
        metres, reading, rank = found
        specific = 0 if (floor is not None and floor == level) else 1
        rating = (specific, rank, path.count(".") + path.count("["), order)
        if best is None or rating < best[0]:
            best = (rating, ScaleHit(metres, path, reading))
    return best[1] if best else None


def _x_extent(polygons: list) -> float | None:
    xs = [
        float(point[0])
        for polygon in polygons
        if isinstance(polygon, list)
        for point in polygon
        if isinstance(point, list) and len(point) >= 2 and all(isinstance(v, int | float) for v in point[:2])
    ]
    return max(xs) - min(xs) if len(xs) >= 3 else None


def find_building_width(data: object, level: int | None = None) -> WidthHit | None:
    """The width (x extent) of the building in metres from a building.json: a width field (per floor first, then
    global), a size pair [width, height], or the x extent of the room polygons of that floor when the file holds them.
    Used with an svg: the width of the drawn rooms in pixels then gives the scale."""
    best: tuple[tuple, WidthHit] | None = None
    for order, (path, key, value, floor) in enumerate(_walk(data, "", None, 0)):
        if level is not None and floor is not None and floor != level:
            continue
        name = _normal(key)
        number = None
        if name in WIDTH_KEYS:
            parsed = _number(value)
            number = parsed[0] if parsed else None
        elif name in SIZE_KEYS and isinstance(value, list) and len(value) == 2:
            parsed = _number(value[0])
            number = parsed[0] if parsed else None
        if number is None or not MIN_VALUE <= number <= 100000.0:
            continue
        rating = (0 if (floor is not None and floor == level) else 1, path.count(".") + path.count("["), order)
        if best is None or rating < best[0]:
            best = (rating, WidthHit(number, path))
    if best:
        return best[1]
    if isinstance(data, dict) and isinstance(data.get("spaces"), list):
        floors = {
            str(f.get("id")): f.get("level") for f in data.get("floors") or [] if isinstance(f, dict) and "id" in f
        }
        polygons = [
            s.get("polygon")
            for s in data["spaces"]
            if isinstance(s, dict) and (level is None or floors.get(str(s.get("floor_id"))) == level)
        ]
        width = _x_extent([p for p in polygons if p])
        if width and MIN_VALUE <= width <= 100000.0:
            return WidthHit(width, "spaces[].polygon (x extent)")
    return None
