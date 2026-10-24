"""Files that travel with a plan image: the vector plan (floor_<n>.svg) and a building.json with the scale.

Both are looked up NEXT TO the plan image that was already validated to be inside the fixed upload folder, never from a
path that came from the browser or from message text. A file that is a symlink out of the folder, too big or not what
it claims to be is ignored with a plain note, and the vision pipeline carries on as before.

`svg_extraction` reads the svg (exact rooms, doors, entrances, room numbers); `adopt_vision` copies what the svg lacks
(names, room types, stair and lift types) from a vision extraction of the same plan, matched by room position."""

import re
from dataclasses import replace
from pathlib import Path

from PIL import Image
from shapely.geometry import Polygon

from building_agent.level4.schema import ROOM_TYPES, Extraction
from building_agent.level4.svg_read import infer_missing_refs, read_svg_with_note

SIZE_TOLERANCE = 0.02  # the svg and the png are the same drawing; sizes may differ by rounding only
MIN_OVERLAP = 0.3  # share of the smaller room that a vision room must cover to lend its name and type
ADOPTED_TYPES = {"stair", "lift", "hall", "corridor", "outdoor"}
_PLAIN = re.compile(r"_plain$", re.IGNORECASE)


def _inside(candidate: Path, uploads_root: Path) -> Path | None:
    """The resolved file when it is a regular file inside `uploads_root` (symlinks are followed, then checked)."""
    try:
        resolved = candidate.resolve()
        if resolved.is_file() and resolved.is_relative_to(Path(uploads_root).resolve()):
            return resolved
    except (OSError, RuntimeError):
        pass
    return None


def find_sibling(image: Path, uploads_root: Path, suffix: str) -> Path | None:
    """`<stem><suffix>` next to the image (also without a trailing `_plain`), inside the upload folder."""
    stem = image.stem
    for name in dict.fromkeys((stem, _PLAIN.sub("", stem))):
        found = _inside(image.with_name(name + suffix), uploads_root)
        if found is not None:
            return found
    return None


def find_building_json(image: Path, uploads_root: Path) -> Path | None:
    """`<stem>.building.json` next to the image (one file per plan, never a shared one)."""
    return find_sibling(image, uploads_root, ".building.json")


def _image_size(image: Path) -> tuple[int, int] | None:
    try:
        with Image.open(image) as picture:
            return picture.size
    except Exception:  # noqa: BLE001 - Pillow raises many kinds; "cannot tell" is all we need
        return None


def svg_extraction(image: Path, uploads_root: Path) -> tuple[Extraction | None, str, int]:
    """(extraction, note, inferred numbers) of the svg next to `image`; extraction is None when there is no svg or it
    cannot be used (the note says why, empty when there is simply no svg)."""
    svg = find_sibling(image, uploads_root, ".svg")
    if svg is None:
        return None, "", 0
    extraction, refused = read_svg_with_note(svg)
    if extraction is None:
        return None, refused, 0
    size = _image_size(image)
    if size is not None and any(
        abs(have - want) > SIZE_TOLERANCE * max(want, 1) + 2
        for have, want in zip((extraction.width_px, extraction.height_px), size, strict=True)
    ):
        return None, "The vector file does not match the size of the plan image, so it was ignored.", 0
    inferred = infer_missing_refs(extraction.rooms)
    return extraction, "", inferred


def _shape(room) -> Polygon | None:
    try:
        shape = Polygon(room.polygon_px)
        return shape if shape.is_valid and shape.area > 0 else shape.buffer(0)
    except (TypeError, ValueError):
        return None


def adopt_vision(svg: Extraction, vision: Extraction | None) -> tuple[Extraction, int]:
    """The svg extraction with names, room types and stair, lift and hall types taken from the vision rooms that
    cover the same place (best overlap first, each vision room once). Returns it and how many rooms got something."""
    if vision is None:
        return svg, 0
    seen = [(room, _shape(room)) for room in vision.rooms]
    pairs = []
    for index, room in enumerate(svg.rooms):
        mine = _shape(room)
        if mine is None:
            continue
        for number, (_, other) in enumerate(seen):
            if other is None or not mine.intersects(other):
                continue
            share = mine.intersection(other).area / min(mine.area, other.area)
            if share >= MIN_OVERLAP:
                pairs.append((share, index, number))
    rooms = list(svg.rooms)
    used_svg, used_vision, adopted = set(), set(), 0
    for _, index, number in sorted(pairs, reverse=True):
        if index in used_svg or number in used_vision:
            continue
        used_svg.add(index)
        used_vision.add(number)
        lent = seen[number][0]
        mine = rooms[index]
        kind = lent.type if lent.type in ADOPTED_TYPES and lent.type in ROOM_TYPES else mine.type
        wanted = (lent.room_type or "").strip()
        room_type = wanted if wanted and wanted != "generic_room" else mine.room_type
        if kind == "outdoor" and mine.type != "outdoor":
            kind = mine.type  # the drawing's green fill is the authority for balconies, not a guess
        rooms[index] = replace(
            mine, name=lent.name or mine.name, type=kind, room_type=room_type, ref=mine.ref or lent.ref
        )
        adopted += 1
    return replace(
        svg,
        rooms=rooms,
        scale_bar_px=vision.scale_bar_px,
        scale_bar_m=vision.scale_bar_m,
    ), adopted


def label_for(room_type: str) -> str:
    return room_type.replace("_", " ").strip().capitalize()


def compose_names(extraction: Extraction) -> Extraction:
    """Name rooms the way the kit does ('Kitchen 1.30'): the room type word plus the printed number. A room whose
    type is unknown (generic) keeps its own name, or none (then 'Room <number>' is used later)."""
    rooms = []
    for room in extraction.rooms:
        name = room.name
        if room.ref:
            if name and room.ref not in name:
                name = f"{name} {room.ref}"
            elif not name and room.room_type and room.room_type != "generic_room":
                name = f"{label_for(room.room_type)} {room.ref}"
        rooms.append(replace(room, name=name))
    return replace(extraction, rooms=rooms)
