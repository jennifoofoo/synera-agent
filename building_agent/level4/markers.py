"""Deterministic door-marker detection for kit-style plan images (no model, no API).

The kit draws doors as brown dots, openings as grey dots and entrances as red triangles in fixed colours. Pixels of
those colours are found by thresholding, grouped into connected components and filtered by size and compactness.
`merge_markers` joins the detections with the vision model's doors. Coordinates are ORIGINAL image pixels."""

import itertools
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
from PIL import Image
from shapely.geometry import Point, Polygon

from building_agent.level4.schema import OUTSIDE, ExtractedDoor, ExtractedRoom, Extraction

# Exact kit colours (verified on proc, resplan, swiss and osm floors, see docs/eval-log.md "Marker detection")
DOOR_RGB = (139, 69, 19)
OPENING_RGB = (158, 158, 158)
ENTRANCE_RGB = (211, 47, 47)
# max per-channel distance of a marker pixel. Kit colours are exact; the slack absorbs noise and JPEG quality 95.
# Grey is tight because anti-aliased wall lines pass through grey.
CORE_TOLERANCE = {"door": 24, "opening": 10, "entrance": 24}
MIN_AREA_PX = {"door": 6, "opening": 6, "entrance": 12}  # pixels of a marker after a 3x3 opening removes thin lines
TYPICAL_AREA_PX = {"door": 20, "opening": 20, "entrance": 60}  # measured median marker areas at 100 dpi
MAX_PARTS = 4  # a blob of more touching markers than this is dropped
MIN_FILL = {"door": 0.55, "opening": 0.55, "entrance": 0.4}  # area / bounding box area (a triangle fills half)
MAX_ASPECT = 2.0

SAME_DOOR_PX = 6.0  # a marker this close to a model door is the same door
DEFAULT_TOLERANCE_PX = 8.0  # a marker must lie this close to the outline of each room it joins

KINDS = ("door", "opening", "entrance")
_RGB = {"door": DOOR_RGB, "opening": OPENING_RGB, "entrance": ENTRANCE_RGB}


@dataclass
class Marker:
    x: float
    y: float
    size_px: float  # equivalent diameter of the blob
    confidence: float  # 0..1 from fill ratio and number of pure pixels


@dataclass
class Markers:
    doors: list[Marker] = field(default_factory=list)
    openings: list[Marker] = field(default_factory=list)
    entrances: list[Marker] = field(default_factory=list)

    def of(self, kind: str) -> list[Marker]:
        return {"door": self.doors, "opening": self.openings, "entrance": self.entrances}[kind]

    def __len__(self) -> int:
        return len(self.doors) + len(self.openings) + len(self.entrances)


def _components(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """4-connected components of a boolean mask (BFS), as lists of (y, x)."""
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    groups = []
    for y, x in np.argwhere(mask):
        if seen[y, x]:
            continue
        seen[y, x] = True
        queue = [(int(y), int(x))]
        for cy, cx in queue:
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    queue.append((ny, nx))
        groups.append(queue)
    return groups


def _split(points: np.ndarray, parts: int) -> list[np.ndarray]:
    """Split a blob of touching markers into `parts` clusters (a few k-means steps, seeded along the long axis)."""
    data = points.astype(float)
    centred = data - data.mean(axis=0)
    axis = np.linalg.svd(centred, full_matrices=False)[2][0]
    order = np.argsort(centred @ axis)
    centres = data[order[np.linspace(0, len(data) - 1, parts).astype(int)]]
    labels = np.zeros(len(data), dtype=int)
    for _ in range(10):
        labels = np.argmin(((data[:, None, :] - centres[None]) ** 2).sum(-1), axis=1)
        centres = np.array([data[labels == k].mean(0) if (labels == k).any() else centres[k] for k in range(parts)])
    return [points[labels == k] for k in range(parts) if (labels == k).any()]


def _shifts(mask: np.ndarray) -> list[np.ndarray]:
    padded = np.pad(mask, 1)
    height, width = mask.shape
    return [padded[dy : dy + height, dx : dx + width] for dy in range(3) for dx in range(3)]


def _open(mask: np.ndarray) -> np.ndarray:
    """3x3 morphological opening: drops lines thinner than 3 px (walls, arcs), keeps dots and triangles."""
    eroded = np.logical_and.reduce(_shifts(mask))
    return np.logical_or.reduce(_shifts(eroded))


def _find(rgb: np.ndarray, kind: str) -> list[Marker]:
    distance = np.abs(rgb.astype(int) - np.array(_RGB[kind])).max(axis=2)
    core = distance <= CORE_TOLERANCE[kind]
    kept = _open(core)
    found = []
    for blob in _components(kept):
        grown = np.zeros_like(core)
        grown[tuple(np.array(blob).T)] = True
        points = np.argwhere(np.logical_or.reduce(_shifts(grown)) & core)  # blob plus its pure fringe
        area = len(points)
        height, width = np.ptp(points, axis=0) + 1
        fill = area / (height * width)
        parts = max(1, round(area / TYPICAL_AREA_PX[kind]))
        if not MIN_AREA_PX[kind] <= area or parts > MAX_PARTS or fill < MIN_FILL[kind] / parts**0.5:
            continue
        if max(height, width) / min(height, width) > MAX_ASPECT * parts:
            continue
        for part in _split(points, parts) if parts > 1 else [points]:
            if len(part) < MIN_AREA_PX[kind]:
                continue
            cy, cx = part.mean(axis=0)
            if kind == "entrance":  # the kit marker position is the centre of the triangle's bounding box
                cy, cx = (part.min(axis=0) + part.max(axis=0)) / 2
            confidence = round(min(1.0, fill / MIN_FILL[kind] / 1.5) * min(1.0, len(part) / TYPICAL_AREA_PX[kind]), 3)
            found.append(Marker(float(cx) + 0.5, float(cy) + 0.5, math.sqrt(4 * len(part) / math.pi), confidence))
    return found


def detect_markers(image_path: str | Path) -> Markers:
    """Door, opening and entrance markers of a kit-style plan image, in original pixel coordinates."""
    with Image.open(image_path) as image:
        rgb = np.array(image.convert("RGB"))
    return Markers(*(_find(rgb, kind) for kind in KINDS))


def _polygons(rooms: list[ExtractedRoom]) -> dict[str, Polygon]:
    shapes = {}
    for room in rooms:
        try:
            shape = Polygon([(float(x), float(y)) for x, y in room.polygon_px])
            if not shape.is_valid:
                shape = shape.buffer(0)
        except (TypeError, ValueError):
            continue
        if shape.geom_type == "Polygon" and shape.area > 0:
            shapes[room.id] = shape
    return shapes


def _room_pair(point: Point, shapes: dict[str, Polygon], tolerance_px: float) -> tuple[tuple[str, str] | None, int]:
    """The two rooms whose outlines are closest to the point (both within tolerance), and how many rooms are near."""
    near = sorted((shape.boundary.distance(point), room_id) for room_id, shape in shapes.items())
    near = [item for item in near if item[0] <= tolerance_px]
    if len(near) < 2:
        return None, len(near)
    if len(near) == 2:
        return (near[0][1], near[1][1]), 2
    # more than two rooms near: take the pair that touch each other closest, then the one nearest to the point
    best = min(
        itertools.combinations(near, 2),
        key=lambda pair: (round(shapes[pair[0][1]].distance(shapes[pair[1][1]]), 1), pair[0][0] + pair[1][0]),
    )
    return (best[0][1], best[1][1]), len(near)


def merge_markers(
    extraction: Extraction, markers: Markers, tolerance_px: float = DEFAULT_TOLERANCE_PX
) -> tuple[Extraction, list[str]]:
    """Add the detected markers to the model's doors. Markers are exact, so they win on position and kind.

    A door marker joins the two rooms whose outlines are nearest. A red marker next to exactly one room becomes an
    entrance. Anything else is dropped with a warning. Model doors without a marker stay unchanged."""
    shapes = _polygons(extraction.rooms)
    warnings: list[str] = []
    free = list(range(len(extraction.doors)))
    merged: list[ExtractedDoor] = []
    items = [(kind, marker) for kind in KINDS for marker in markers.of(kind)]
    for kind, marker in sorted(items, key=lambda item: (item[1].y, item[1].x)):
        point = Point(marker.x, marker.y)
        at = f"{kind} marker at ({marker.x:.0f}, {marker.y:.0f})"
        pair, count = _room_pair(point, shapes, tolerance_px)
        if kind == "entrance":
            near = sorted((shape.boundary.distance(point), room_id) for room_id, shape in shapes.items())
            near = [room_id for dist, room_id in near if dist <= tolerance_px]
            if len(near) == 1:
                pair = (near[0], OUTSIDE)
            else:
                pair = None
        twin = None
        if free:
            index = min(
                free,
                key=lambda i: math.dist(extraction.doors[i].position_px, (marker.x, marker.y)),
            )
            if math.dist(extraction.doors[index].position_px, (marker.x, marker.y)) <= SAME_DOOR_PX:
                twin = index
        if twin is not None:
            free.remove(twin)
            model = extraction.doors[twin]
            rooms = tuple(model.rooms)
            if pair is not None and set(pair) != set(rooms):
                warnings.append(
                    f"The model joined {rooms[0]} and {rooms[1]} at {at}, but the outlines say {pair[0]} and {pair[1]}; "
                    "kept the outline pair."
                )
                rooms = pair
            if model.kind != kind:
                warnings.append(f"The model called the door at {at} a {model.kind}; the marker colour says {kind}.")
            merged.append(
                ExtractedDoor(rooms=rooms, position_px=[marker.x, marker.y], kind=kind, width_px=model.width_px)
            )
        elif pair is not None:
            merged.append(ExtractedDoor(rooms=pair, position_px=[marker.x, marker.y], kind=kind, width_px=None))
            if count > 2 and kind != "entrance":
                warnings.append(f"{at} is near {count} rooms; joined {pair[0]} and {pair[1]}.")
        else:
            reason = "an entrance must touch exactly one room" if kind == "entrance" else "it does not join two rooms"
            warnings.append(f"Dropped {at}: {reason} ({count} rooms within {tolerance_px:.0f} px).")
    merged += [extraction.doors[i] for i in free]
    return replace(extraction, doors=merged), warnings
