"""Deterministic room segmentation of the kit plan images (no model, numpy + PIL + shapely only).

The kit draws every room as a flat filled colour region (colour by room type), outlined by thin dark wall lines,
with printed room numbers and small door markers. A connected-colour-region analysis therefore gives every room
with exact corners. `segment_rooms` does that, `match_to_extraction` uses the result to repair what the vision
model lost, merged or drew too small.

Palette learned from the kit images (RGB, flat fills):
  background   white (255,255,255); anything with all channels >= 248 counts as white
  walls        dark grey lines (about 70..85 grey), 1 px wide plus anti-aliasing; never a fill
  markers      doors brown (139,69,19), outer entrances red triangles (211,47,47), openings grey dots (158);
               plain ink, they sit on walls or outside the building
  text         dark glyphs of room numbers and the title; plain ink
  room fills   beige (243,239,230) generic room / office / toilet ...; light grey (220) corridor, also stair
               and lift cases and door swing arcs; orange (244,177,131); purple (180,167,214);
               yellow (255,242,179) hall; green (207,232,196) outdoor
Rooms of different types may share the beige fill, so only wall lines separate them; the colour is a hint, never
the identity of a room. A colour that is not in the palette but covers a real area is learned as an extra fill.
"""

import time
from dataclasses import dataclass, field, replace

import numpy as np
from PIL import Image
from shapely.geometry import Polygon

from building_agent.level4.schema import ExtractedRoom, Extraction

PALETTE: dict[str, tuple[tuple[int, int, int], str, str]] = {
    # name: (rgb, schema type, room_type)
    "beige": ((243, 239, 230), "room", "generic_room"),
    "grey": ((220, 220, 220), "corridor", "corridor"),
    "orange": ((244, 177, 131), "room", "generic_room"),
    "purple": ((180, 167, 214), "room", "generic_room"),
    "yellow": ((255, 242, 179), "room", "generic_room"),
    "green": ((207, 232, 196), "outdoor", "outdoor"),
}
MARKER_COLOURS = [(139, 69, 19), (211, 47, 47), (158, 158, 158)]
WHITE_MIN = 248
COLOUR_TOLERANCE = 8
EXTRA_FILL_MIN_SHARE = 0.0008  # of all pixels, to learn a colour that is not in the palette
MIN_REGION_AREA_PX = 20
MIN_THICKNESS_PX = 3.0  # 2 * area / perimeter: thinner regions are gaps between double wall lines, not rooms
SMALL_INK_MAX_PX = (24, 60)  # clip range for the longest side of text and dot components, scaled by image size
DOT_REACH_PX = 3
WALL_GROW_PX = 1  # walls are about 2 px of ink: each room takes the half next to it
SIMPLIFY_PX = 1.2
COUNTER_MAX_PX = 40  # fill islands this small (insides of 0, 6, 8, 9) belong to the glyph around them
COUNTER_MAX_SPAN_PX = 10
MIN_FILL_SHARE = 0.5  # of non-white pixels that must be flat fills, else this is not a kit-style plan
OFF_PALETTE_MAX_SHARE = (
    0.10  # of the image in colours outside the kit palette (kit plans: under 1%), else a scan or photo
)
PALETTE_MAX_SHARE = 0.75  # of the image in ONE palette colour (kit plans: up to 61%), else this is not a floor plan
MIN_IMPLAUSIBLE_REGIONS = 12
IMPLAUSIBLE_REGION_FACTOR = 3  # more regions than this many times the model's rooms means noise, not rooms
SCAN_NOTE = (
    "This image looks like a scan or a photo, so I did not use its colours to redraw the rooms. "
    "The rooms come from my own reading of the image only and may be less exact."
)
NOISE_NOTE = (
    "The colour analysis found far more areas than I can see rooms, so I did not use it. "
    "The rooms come from my own reading of the image only and may be less exact."
)


@dataclass
class Region:
    polygon: list[list[float]]  # outline corners in original pixel coordinates, not closed
    colour: tuple[int, int, int]
    colour_name: str
    area_px: float
    touches_border: bool
    holes: list[list[list[float]]] = field(default_factory=list)

    @property
    def shape(self) -> Polygon:
        return Polygon(self.polygon, self.holes)


@dataclass
class SegmentResult:
    width_px: int
    height_px: int
    regions: list[Region]
    fill_share: float = 1.0  # flat fills / non-white pixels
    seconds: float = 0.0
    reject_note: str = ""  # plain words, set when the colour analysis must not be trusted on this image

    @property
    def usable(self) -> bool:
        return bool(self.regions) and self.fill_share >= MIN_FILL_SHARE and not self.reject_note


def _label_runs(values: np.ndarray, connectivity: int) -> np.ndarray:
    """Connected components of equal non-negative values (negative = background). 0 = none, 1.. = components.
    Run based union-find with numpy only."""
    height, width = values.shape
    padded = np.pad(values, ((0, 0), (1, 1)), constant_values=-1)
    centre = padded[:, 1:-1]
    starts = np.argwhere((centre >= 0) & (centre != padded[:, :-2]))
    ends = np.argwhere((centre >= 0) & (centre != padded[:, 2:]))
    if not len(starts):
        return np.zeros((height, width), dtype=np.int32)
    stride = width + 3
    s = starts[:, 0] * stride + starts[:, 1]
    e = ends[:, 0] * stride + ends[:, 1] + 1  # exclusive
    run_value = centre[starts[:, 0], starts[:, 1]]
    sa, ea = s + stride, e + stride  # runs of the row above, moved into the row below
    if connectivity == 4:
        lo = np.searchsorted(ea, s, side="right")
        hi = np.searchsorted(sa, e, side="left")
    else:
        lo = np.searchsorted(ea, s, side="left")
        hi = np.searchsorted(sa, e, side="right")
    count = np.clip(hi - lo, 0, None)
    below = np.repeat(np.arange(len(s)), count)
    first = np.repeat(lo, count)
    above = first + (np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count))
    same = run_value[above] == run_value[below]
    above, below = above[same], below[same]
    parent = np.arange(len(s))
    while True:
        pa, pb = parent[above], parent[below]
        differ = pa != pb
        if not differ.any():
            break
        np.minimum.at(parent, np.maximum(pa, pb)[differ], np.minimum(pa, pb)[differ])
        while True:
            hop = parent[parent]
            if (hop == parent).all():
                break
            parent = hop
    _, run_label = np.unique(parent, return_inverse=True)
    lengths = e - s
    flat_start = starts[:, 0] * width + starts[:, 1]
    offsets = np.arange(lengths.sum()) - np.repeat(np.cumsum(lengths) - lengths, lengths)
    out = np.zeros(height * width, dtype=np.int32)
    out[np.repeat(flat_start, lengths) + offsets] = np.repeat(run_label + 1, lengths)
    return out.reshape(height, width)


def _close(a, b, tolerance: int) -> bool:
    return max(abs(x - y) for x, y in zip(a, b)) <= tolerance


def _classify(rgb: np.ndarray) -> tuple[np.ndarray, list[tuple[str, tuple[int, int, int]]]]:
    """Per pixel: -2 white, -1 ink (walls, text, markers, anti-aliasing), >= 0 index into the returned fills."""
    height, width, _ = rgb.shape
    packed = (rgb[..., 0].astype(np.int32) << 16) | (rgb[..., 1].astype(np.int32) << 8) | rgb[..., 2]
    unique, inverse, counts = np.unique(packed, return_inverse=True, return_counts=True)
    colours = np.stack([(unique >> 16) & 255, (unique >> 8) & 255, unique & 255], axis=1).astype(np.int16)
    fills = [(name, spec[0]) for name, spec in PALETTE.items()]
    kind = np.full(len(unique), -1, dtype=np.int32)
    kind[(colours >= WHITE_MIN).all(axis=1)] = -2
    luma = colours @ np.array([0.299, 0.587, 0.114])
    for index in np.argsort(-counts):  # learn extra fills, biggest first
        if kind[index] != -1 or counts[index] < EXTRA_FILL_MIN_SHARE * height * width or luma[index] < 170:
            continue
        colour = tuple(int(c) for c in colours[index])
        if any(_close(colour, rgb_, COLOUR_TOLERANCE) for _, rgb_ in fills) or any(
            _close(colour, marker, 30) for marker in MARKER_COLOURS
        ):
            continue
        fills.append((f"fill_{colour[0]:02x}{colour[1]:02x}{colour[2]:02x}", colour))
    palette = np.array([rgb_ for _, rgb_ in fills], dtype=np.int16)
    distance = np.abs(colours[:, None, :] - palette[None, :, :]).max(axis=2)
    best = distance.argmin(axis=1)
    match = (distance[np.arange(len(unique)), best] <= COLOUR_TOLERANCE) & (kind != -2)
    kind[match] = best[match]
    return kind[inverse].reshape(height, width), fills


def _shift(image: np.ndarray, dy: int, dx: int, fill: int) -> np.ndarray:
    out = np.full_like(image, fill)
    h, w = image.shape
    out[max(dy, 0) : h + min(dy, 0), max(dx, 0) : w + min(dx, 0)] = image[
        max(-dy, 0) : h + min(-dy, 0), max(-dx, 0) : w + min(-dx, 0)
    ]
    return out


def _counters(comp: np.ndarray) -> np.ndarray:
    """Pixels of tiny compact fill islands, the insides of printed 0, 6, 8, 9."""
    sizes = np.bincount(comp.ravel())
    ys, xs = np.nonzero((comp > 0) & (sizes[comp] <= COUNTER_MAX_PX))
    ids = comp[ys, xs]
    spans = np.zeros(len(sizes), dtype=int)
    for axis in (ys, xs):
        low = np.full(len(sizes), np.iinfo(np.int32).max)
        high = np.full(len(sizes), -1)
        np.minimum.at(low, ids, axis)
        np.maximum.at(high, ids, axis)
        spans = np.maximum(spans, high - low + 1)
    compact = (spans <= COUNTER_MAX_SPAN_PX) & (sizes <= COUNTER_MAX_PX)
    compact[0] = False
    return compact[comp]


def _absorb_small_ink(lab: np.ndarray, comp: np.ndarray) -> np.ndarray:
    """Text and dots inside exactly one room (and not touching white or a wall) become part of that room."""
    height, width = lab.shape
    ink = lab == -1
    ink_id = _label_runs(np.where(ink, 0, -1), 8)
    n = int(ink_id.max())
    if not n:
        return comp
    ys, xs = np.nonzero(ink)
    ids = ink_id[ys, xs]
    top = np.full(n + 1, height)
    left = np.full(n + 1, width)
    bottom = np.zeros(n + 1, dtype=int)
    right = np.zeros(n + 1, dtype=int)
    np.minimum.at(top, ids, ys)
    np.minimum.at(left, ids, xs)
    np.maximum.at(bottom, ids, ys)
    np.maximum.at(right, ids, xs)
    limit = int(np.clip(0.05 * max(height, width), *SMALL_INK_MAX_PX))
    small = (np.maximum(bottom - top, right - left) + 1 <= limit) & (np.arange(n + 1) > 0)
    low = np.full(n + 1, np.iinfo(np.int32).max)
    high = np.full(n + 1, -1)
    touches_white = np.zeros(n + 1, dtype=bool)
    sel = small[ids]
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        neighbour_comp = _shift(comp, dy, dx, 0)[ys[sel], xs[sel]]
        neighbour_white = _shift((lab == -2).astype(np.int32), dy, dx, 0)[ys[sel], xs[sel]] > 0
        has = neighbour_comp > 0
        np.minimum.at(low, ids[sel][has], neighbour_comp[has])
        np.maximum.at(high, ids[sel][has], neighbour_comp[has])
        touches_white[ids[sel][neighbour_white]] = True
    take = small & (low == high) & ~touches_white
    target = np.where(take, low, 0)
    out = comp.copy()
    filled = ink & take[ink_id]
    out[filled] = target[ink_id[filled]]
    return out


def _door_dots(rgb: np.ndarray) -> np.ndarray:
    """Pixels around door (brown) and opening (grey) dots; a room may reach through them to the wall middle."""
    signed = rgb.astype(np.int16)
    brown = np.abs(signed - np.array(MARKER_COLOURS[0])).max(axis=2) <= 12
    grey = (np.abs(signed - np.array(MARKER_COLOURS[2])).max(axis=2) <= 6) & (np.ptp(signed, axis=2) == 0)
    dots = brown | grey
    for _ in range(DOT_REACH_PX):
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            dots = dots | _shift(dots, dy, dx, False)
    return dots


def _grow_into_walls(comp: np.ndarray, lab: np.ndarray, steps: int, dots: np.ndarray) -> np.ndarray:
    out = comp.copy()
    free = (lab != -2) & (comp == 0)
    for step in range(steps + DOT_REACH_PX):
        allowed = free if step < steps else free & dots
        best = np.zeros_like(out)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            best = np.maximum(best, _shift(out, dy, dx, 0))
        take = allowed & (out == 0) & (best > 0)
        out[take] = best[take]
    return out


def _outline(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """Closed pixel-edge rings of a boolean mask (clockwise on screen), as lists of (x, y) corner points."""
    padded = np.pad(mask, 1)
    inside = padded[1:-1, 1:-1]
    edges: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for (dy, dx), step in (
        ((-1, 0), lambda y, x: ((x, y), (x + 1, y))),
        ((0, 1), lambda y, x: ((x + 1, y), (x + 1, y + 1))),
        ((1, 0), lambda y, x: ((x + 1, y + 1), (x, y + 1))),
        ((0, -1), lambda y, x: ((x, y + 1), (x, y))),
    ):
        outside = inside & ~_shift_pad(padded, dy, dx)
        for y, x in np.argwhere(outside).tolist():
            a, b = step(y, x)
            edges.setdefault(a, []).append(b)
    rings = []
    while edges:
        start = next(iter(edges))
        ring = [start]
        previous, current = start, edges[start].pop()
        if not edges[start]:
            del edges[start]
        while current != start:
            ring.append(current)
            options = edges[current]
            if len(options) == 1:
                nxt = options.pop()
            else:  # pinch point: turn right on screen so a diagonal touch does not join two lobes
                heading = (current[0] - previous[0], current[1] - previous[1])
                right = (-heading[1], heading[0])
                nxt = next((o for o in options if (o[0] - current[0], o[1] - current[1]) == right), options[-1])
                options.remove(nxt)
            if not options:
                del edges[current]
            previous, current = current, nxt
        rings.append(ring)
    return rings


def _shift_pad(padded: np.ndarray, dy: int, dx: int) -> np.ndarray:
    h, w = padded.shape
    return padded[1 + dy : h - 1 + dy, 1 + dx : w - 1 + dx]


def _ring_polygon(ring: list[tuple[int, int]], offset: tuple[int, int], tolerance: float) -> list[list[float]]:
    pts = [(x + offset[0], y + offset[1]) for x, y in ring]
    shape = Polygon(pts)
    if tolerance > 0:
        shape = shape.simplify(tolerance, preserve_topology=True)
    if shape.is_empty or shape.geom_type != "Polygon":
        return [[float(x), float(y)] for x, y in pts]
    return [[float(x), float(y)] for x, y in list(shape.exterior.coords)[:-1]]


def _looks_like_scan(lab: np.ndarray, palette_size: int) -> bool:
    """Kit plans use the palette colours only. A scan, photo or tilted sheet has its paper tone (and noise) learned as
    extra fill colours that cover a large part of the image, or one palette colour that covers almost all of it."""
    counts = np.bincount(lab[lab >= 0], minlength=palette_size)
    total = lab.size
    off_palette = counts[palette_size:].sum() / total
    return bool(off_palette > OFF_PALETTE_MAX_SHARE or counts.max(initial=0) / total > PALETTE_MAX_SHARE)


def check_region_count(segment: SegmentResult, model_rooms: int) -> SegmentResult:
    """Reject a segmentation with far more regions than the model has rooms (noise, not rooms)."""
    if segment.reject_note or not model_rooms:
        return segment
    if len(segment.regions) > max(MIN_IMPLAUSIBLE_REGIONS, IMPLAUSIBLE_REGION_FACTOR * model_rooms):
        return replace(segment, reject_note=NOISE_NOTE)
    return segment


MAX_PIXELS = 6_000_000  # about 1.8 GB of working memory per 4 Mpx measured; larger images keep the model polygons


def segment_rooms(image_path, simplify_px: float = SIMPLIFY_PX, wall_grow_px: int = WALL_GROW_PX) -> SegmentResult:
    begin = time.perf_counter()
    with Image.open(image_path) as image:
        if image.width * image.height > MAX_PIXELS:
            raise ValueError("The image is too large to segment.")
        rgb = np.asarray(image.convert("RGB"))
    height, width, _ = rgb.shape
    lab, fills = _classify(rgb)
    if _looks_like_scan(lab, len(PALETTE)):  # paper tone read as one flat fill: skip the work and the false regions
        return SegmentResult(width, height, [], 0.0, time.perf_counter() - begin, SCAN_NOTE)
    comp = _label_runs(lab, 4)
    counters = _counters(comp)
    lab = np.where(counters, -1, lab)
    comp = np.where(counters, 0, comp)
    comp = _absorb_small_ink(lab, comp)
    comp = _grow_into_walls(comp, lab, wall_grow_px, _door_dots(rgb))
    non_white = int((lab != -2).sum())
    fill_share = float((lab >= 0).sum() / non_white) if non_white else 0.0
    n = int(comp.max())
    regions: list[Region] = []
    if n:
        flat = comp.ravel()
        order = np.argsort(flat, kind="stable")
        bounds = np.searchsorted(flat[order], np.arange(1, n + 2))
        fill_of = np.zeros(n + 1, dtype=int)
        pos = np.nonzero(lab >= 0)
        fill_of[comp[pos]] = lab[pos]
        for k in range(1, n + 1):
            idx = order[bounds[k - 1] : bounds[k]]
            if len(idx) < MIN_REGION_AREA_PX:
                continue
            ys, xs = np.divmod(idx, width)
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            mask = np.zeros((y1 - y0, x1 - x0), dtype=bool)
            mask[ys - y0, xs - x0] = True
            polys = [(_ring_polygon(r, (int(x0), int(y0)), simplify_px), r) for r in _outline(mask)]
            polys = [(p, r) for p, r in polys if len(p) >= 3]
            if not polys:
                continue
            areas = [abs(Polygon(p).area) for p, _ in polys]
            outer = int(np.argmax(areas))
            if 2 * len(idx) / max(Polygon(polys[outer][0]).length, 1.0) < MIN_THICKNESS_PX:
                continue
            holes = [p for i, (p, _) in enumerate(polys) if i != outer and areas[i] >= MIN_REGION_AREA_PX]
            name, colour = fills[fill_of[k]]
            regions.append(
                Region(
                    polys[outer][0],
                    colour,
                    name,
                    float(len(idx)),
                    bool(y0 == 0 or x0 == 0 or y1 == height or x1 == width),
                    holes,
                )
            )
    regions.sort(key=lambda region: (min(y for _, y in region.polygon), min(x for x, _ in region.polygon)))
    return SegmentResult(width, height, regions, fill_share, time.perf_counter() - begin)


def _type_of(colour_name: str) -> tuple[str, str]:
    spec = PALETTE.get(colour_name)
    return (spec[1], spec[2]) if spec else ("room", "generic_room")


CLAIM_MIN_SHARE = 0.3  # of a model room that must lie in a region to claim it


def match_to_extraction(extraction: Extraction, segment: SegmentResult) -> tuple[Extraction, list[str]]:
    """Replace the model's rough room polygons by the segmented regions and add rooms the model lost.
    Doors are untouched (they reference room ids, which stay)."""
    segment = check_region_count(segment, len(extraction.rooms))
    if segment.reject_note:
        return extraction, [segment.reject_note]
    if not segment.usable:
        why = "no regions" if not segment.regions else f"only {segment.fill_share:.0%} of the ink is flat fill"
        return extraction, [f"segmentation_skipped: {why}"]
    shapes = [region.shape.buffer(0) for region in segment.regions]
    warnings: list[str] = []
    claims: dict[int, list[tuple[float, int]]] = {}  # region index -> (overlap area, room index)
    for room_index, room in enumerate(extraction.rooms):
        model = Polygon(room.polygon_px).buffer(0)
        if model.is_empty or model.area <= 0:
            continue
        best = (0.0, -1)
        for region_index, shape in enumerate(shapes):
            if shape.bounds[0] > model.bounds[2] or shape.bounds[2] < model.bounds[0]:
                continue
            if shape.bounds[1] > model.bounds[3] or shape.bounds[3] < model.bounds[1]:
                continue
            overlap = shape.intersection(model).area
            if overlap > best[0]:
                best = (overlap, region_index)
        inside = best[1] >= 0 and (
            best[0] / model.area >= CLAIM_MIN_SHARE or shapes[best[1]].contains(model.representative_point())
        )
        if inside:
            claims.setdefault(best[1], []).append((best[0], room_index))
    new_polygons: dict[int, list[list[float]]] = {}
    claimed_regions: set[int] = set()
    for region_index, items in claims.items():
        items.sort(reverse=True)
        claimed_regions.add(region_index)
        winner = items[0][1]
        new_polygons[winner] = segment.regions[region_index].polygon
        for _, loser in items[1:]:
            warnings.append(
                f"room_region_shared: {extraction.rooms[loser].id} keeps its polygon, region went to {extraction.rooms[winner].id}"
            )
    rooms = []
    for room_index, room in enumerate(extraction.rooms):
        if room_index in new_polygons:
            rooms.append(replace(room, polygon_px=[list(p) for p in new_polygons[room_index]]))
            continue
        rooms.append(room)
        if not any(room_index == r for items in claims.values() for _, r in items):
            warnings.append(f"room_without_region: {room.id} keeps the model polygon")
    used = {room.id for room in rooms}
    counter = 0
    for region_index, region in enumerate(segment.regions):
        if region_index in claimed_regions:
            continue
        counter += 1
        while f"seg{counter}" in used:
            counter += 1
        room_id = f"seg{counter}"
        used.add(room_id)
        kind, room_type = _type_of(region.colour_name)
        rooms.append(
            ExtractedRoom(id=room_id, polygon_px=[list(p) for p in region.polygon], type=kind, room_type=room_type)
        )
        warnings.append(f"room_added_from_image: {room_id} ({region.colour_name}, {region.area_px:.0f} px)")
    return replace(extraction, rooms=rooms), warnings
