"""Reader for the vector plan the kit writes next to the png (floor_<n>.svg); used by build_from_plan when one exists.

Rooms are the outlined patches, doors are the marker points. Marker pairs come from the two nearest outlines, so the
result is exact where a plan carries such an svg and useless where it does not (a scan, a photo, a plain png).
Room numbers are the comments `<!-- 1.01 -->` of the text blocks (glyph paths, no text elements); a number belongs to
the room that holds the middle of its glyphs. Names and room types are NOT in the svg (fills only tell room, balcony
and corridor or stairwell), so the caller fills those in. The file is never run: it is read as text with regular
expressions, and files that are too big or carry scripts, entities or external references are refused."""

import itertools
import re
from pathlib import Path

from shapely.geometry import Point, Polygon

from building_agent.level4.schema import OUTSIDE, ExtractedDoor, ExtractedRoom, Extraction

PNG_PER_PT = 100 / 72
MAX_MARKER_DISTANCE_PX = 25.0
ROOM_STROKE = "#333333"
# fill -> (type, room_type, palette name of segment.py, which connector detection reads: orange stair, purple lift)
ROOM_FILLS = {
    "#f3efe6": ("room", "generic_room", "beige"),
    "#cfe8c4": ("outdoor", "balcony", "green"),
    "#dcdcdc": ("corridor", "corridor", "grey"),
    "#f4b183": ("room", "generic_room", "orange"),
    "#b4a7d6": ("room", "generic_room", "purple"),
    "#fff2b3": ("room", "generic_room", "yellow"),
}
MARKER_KINDS = {"#8b4513": "door", "#9e9e9e": "opening", "#d32f2f": "entrance"}

_PATCH = re.compile(r'<g id="patch_\d+">\s*<path d="([^"]+)"[^>]*style="([^"]*)"')
_MARKER = re.compile(r'<g id="line2d_\d+">\s*<path d="M ([-\d.]+) ([-\d.]+)\s*"[^>]*style="[^"]*stroke: (#[0-9a-f]{6})')
_SIZE = re.compile(r'<svg[^>]*width="([\d.]+)pt" height="([\d.]+)pt"')
_NUMBER = re.compile(r"-?\d+\.?\d*")
_TEXT = re.compile(r'<g id="text_\d+">\s*<!-- ([^>]{1,40}?) -->\s*<g [^>]*transform="translate\(([-\d.]+) ([-\d.]+)\)')
_GLYPH_SHIFT = re.compile(r'<use xlink:href="#[^"]+" transform="translate\(([-\d.]+) 0\)"')
_GLYPH_SCALE = 0.06  # pt per glyph unit in the kit's text blocks (font size about 6 pt)
_GLYPH_ADVANCE = 63.6  # width of the last glyph in those units (digits; close enough for a middle point)
_CAP_HEIGHT = 0.73  # of the em (100 glyph units)
MAX_SVG_BYTES = 20 * 1024 * 1024
UNSAFE = re.compile(r"<script|<!ENTITY|<foreignObject|href=\"(?:https?:|file:|data:|javascript:)", re.IGNORECASE)


def read_svg(path: Path) -> Extraction | None:
    """The floor as an Extraction in the pixel frame of the matching png, or None if the file is not such a plan."""
    try:
        file = Path(path)
        if not file.is_file() or file.stat().st_size > MAX_SVG_BYTES:
            return None
        text = file.read_text(encoding="utf-8")
        if UNSAFE.search(text):
            return None
        size = _SIZE.search(text)
        rooms = _rooms(text)
        if size is None or not rooms:
            return None
        _number_rooms(text, rooms)
        outlines = [(room.id, Polygon(room.polygon_px)) for room in rooms]
        doors = [door for door in (_door(m, outlines) for m in _MARKER.findall(text)) if door is not None]
        return Extraction(
            round(float(size.group(1)) * PNG_PER_PT), round(float(size.group(2)) * PNG_PER_PT), rooms, doors
        )
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _rooms(text: str) -> list[ExtractedRoom]:
    rooms = []
    for data, style in _PATCH.findall(text):
        fill = re.search(r"fill: (#[0-9a-f]{6})", style)
        if fill is None or fill.group(1) not in ROOM_FILLS or f"stroke: {ROOM_STROKE}" not in style:
            continue
        numbers = [float(v) for v in _NUMBER.findall(data)]
        if len(numbers) % 2 or len(numbers) < 6:
            continue
        points = [[x * PNG_PER_PT, y * PNG_PER_PT] for x, y in zip(numbers[::2], numbers[1::2])]
        if Polygon(points).is_valid and Polygon(points).area > 0:
            kind, room_type, palette = ROOM_FILLS[fill.group(1)]
            rooms.append(ExtractedRoom(f"r{len(rooms)}", points, type=kind, room_type=room_type, fill=palette))
    return rooms


def _number_rooms(text: str, rooms: list[ExtractedRoom]) -> None:
    """Set `ref` of every room that holds the middle of a printed number (smallest room wins, one number per room)."""
    shapes = [(room, Polygon(room.polygon_px)) for room in rooms]
    blocks = list(_TEXT.finditer(text))
    for index, block in enumerate(blocks):
        end = blocks[index + 1].start() if index + 1 < len(blocks) else len(text)
        shifts = [float(v) for v in _GLYPH_SHIFT.findall(text, block.end(), end)]
        width = (max(shifts, default=0.0) + _GLYPH_ADVANCE) * _GLYPH_SCALE
        x = (float(block.group(2)) + width / 2) * PNG_PER_PT
        y = (float(block.group(3)) - _CAP_HEIGHT * 100 * _GLYPH_SCALE / 2) * PNG_PER_PT
        point = Point(x, y)
        holders = sorted(
            ((shape.area, index, room) for index, (room, shape) in enumerate(shapes) if shape.contains(point))
        )
        if holders and holders[0][2].ref is None:
            holders[0][2].ref = block.group(1).strip()


def _door(marker: tuple[str, str, str], outlines: list[tuple[str, Polygon]]) -> ExtractedDoor | None:
    x, y, colour = float(marker[0]) * PNG_PER_PT, float(marker[1]) * PNG_PER_PT, marker[2]
    kind = MARKER_KINDS.get(colour)
    if kind is None:
        return None
    point = Point(x, y)
    near = sorted(((shape.distance(point), room_id) for room_id, shape in outlines))
    wanted = 1 if kind == "entrance" else 2
    near = [item for item in near[:wanted] if item[0] <= MAX_MARKER_DISTANCE_PX]
    if len(near) < wanted:
        return None
    ends = (near[0][1], OUTSIDE) if kind == "entrance" else (near[0][1], near[1][1])
    return ExtractedDoor(ends, [x, y], kind)


_NUMBERED = re.compile(r"^(-?\d+)\.(\d+)$")


def infer_missing_refs(rooms: list[ExtractedRoom]) -> int:
    """Give a number to rooms whose number the plan did not print (small rooms), and return how many got one.

    The kit numbers the rooms of a floor in drawing order (0.01, 0.02, ...), so a run of unnumbered rooms between
    two numbered ones gets the numbers in between, but only when they fit exactly: the numbered rooms of the floor
    are all of the form <floor>.<nn> and rise in drawing order, and the gap holds as many rooms as missing numbers."""
    numbered = [(index, _NUMBERED.match(room.ref)) for index, room in enumerate(rooms) if room.ref]
    if any(match is None for _, match in numbered) or not numbered:
        return 0
    values = [(index, match.group(1), int(match.group(2)), len(match.group(2))) for index, match in numbered]
    if len({floor for _, floor, _, _ in values}) != 1 or any(b[2] <= a[2] for a, b in itertools.pairwise(values)):
        return 0
    filled = 0
    for (first, floor, low, width), (second, _, high, _) in itertools.pairwise(values):
        gap = second - first - 1
        if gap > 0 and high - low - 1 == gap:
            for step, index in enumerate(range(first + 1, second), start=1):
                rooms[index].ref = f"{floor}.{low + step:0{width}d}"
                filled += 1
    return filled
