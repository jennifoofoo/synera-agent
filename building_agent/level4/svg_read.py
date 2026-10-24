"""Optional reader for the vector plan the kit writes next to the png (floor_<n>.svg). Not part of the default flow.

Rooms are the outlined patches, doors are the marker points. Marker pairs come from the two nearest outlines, so the
result is exact where a plan carries such an svg and useless where it does not (a scan, a photo, a plain png)."""

import re
from pathlib import Path

from shapely.geometry import Point, Polygon

from building_agent.level4.schema import OUTSIDE, ExtractedDoor, ExtractedRoom, Extraction

PNG_PER_PT = 100 / 72
MAX_MARKER_DISTANCE_PX = 25.0
ROOM_STROKE = "#333333"
ROOM_FILLS = {
    "#f3efe6": ("room", "generic_room"),
    "#cfe8c4": ("outdoor", "balcony"),
    "#dcdcdc": ("corridor", "corridor"),
}
MARKER_KINDS = {"#8b4513": "door", "#9e9e9e": "opening", "#d32f2f": "entrance"}

_PATCH = re.compile(r'<g id="patch_\d+">\s*<path d="([^"]+)"[^>]*style="([^"]*)"')
_MARKER = re.compile(r'<g id="line2d_\d+">\s*<path d="M ([-\d.]+) ([-\d.]+)\s*"[^>]*style="[^"]*stroke: (#[0-9a-f]{6})')
_SIZE = re.compile(r'<svg[^>]*width="([\d.]+)pt" height="([\d.]+)pt"')
_NUMBER = re.compile(r"-?\d+\.?\d*")


def read_svg(path: Path) -> Extraction | None:
    """The floor as an Extraction in the pixel frame of the matching png, or None if the file is not such a plan."""
    try:
        text = Path(path).read_text(encoding="utf-8")
        size = _SIZE.search(text)
        rooms = _rooms(text)
        if size is None or not rooms:
            return None
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
            kind, room_type = ROOM_FILLS[fill.group(1)]
            rooms.append(ExtractedRoom(f"r{len(rooms)}", points, type=kind, room_type=room_type))
    return rooms


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
