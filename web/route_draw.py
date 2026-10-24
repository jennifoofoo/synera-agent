"""Drawing-only geometry for the page's route line: keep its ends off furniture.

Nothing here changes a route (length, rooms, steps, Answer: lines). The routing model ignores assets on purpose
(Synera's rules); this module only moves the drawn points so the line does not start or end on a machine.

- `free_area`: the walkable part of a room (15 cm off the walls) minus every asset footprint grown by
  ASSET_MARGIN_M. Cached per room; the cache is keyed on a signature of all assets, so moving, adding or
  removing an asset in the chat invalidates it.
- `drawn_anchor`: the room anchor if it is free, else the nearest free point (the anchor if nothing is free).
- `ends_at_door`: big halls and production/warehouse zones: the line stops at the door it enters by."""

import weakref
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import Point
from shapely.ops import nearest_points, unary_union

from starter_agent.building_map import WALL_CLEARANCE_M, BuildingMap, outline

ASSET_MARGIN_M = 0.3  # how far the drawn line keeps off an asset footprint
BIG_ROOM_M2 = 150.0  # rooms at least this large: the line ends at their door, the room itself is the target
BIG_ROOM_TYPES = ("_zone",)  # room_type suffixes (production_zone, warehouse_zone, ...) treated as big
DEFAULT_SIZE_M = 0.5  # edit_ops.asset_shape's size for an asset without a footprint
INSIDE_NUDGE_M = 0.05  # a stepped-out point moves this far into the free area, off its edge


@dataclass
class DrawIndex:
    """Grown asset footprints per floor in an STRtree, plus per-room results."""

    signature: int
    trees: dict[str, tuple[shapely.STRtree, np.ndarray]] = field(default_factory=dict)
    rooms: dict[tuple, tuple] = field(default_factory=dict)  # (space id, polygon) -> (free area, drawn anchor)


_INDEXES: "weakref.WeakKeyDictionary[BuildingMap, DrawIndex]" = weakref.WeakKeyDictionary()


def asset_signature(bm: BuildingMap) -> int:
    """Changes whenever an asset is added, removed, moved, turned or resized."""
    return hash(
        tuple(
            (
                key,
                asset.get("floor_id"),
                tuple(asset["position"][:2]) if asset.get("position") else None,
                tuple(sorted((asset.get("footprint") or {}).items())),
            )
            for key, asset in bm.assets.items()
        )
    )


def draw_index(bm: BuildingMap) -> DrawIndex:
    """The asset index for the current assets; rebuilt only when the asset signature changed. Callers that need
    several rooms fetch it once and pass it on (the signature walks every asset)."""
    signature = asset_signature(bm)
    index = _INDEXES.get(bm)
    if index is None or index.signature != signature:
        index = DrawIndex(signature, grown_footprints(bm))
        _INDEXES[bm] = index
    return index


def grown_footprints(bm: BuildingMap) -> dict[str, tuple[shapely.STRtree, np.ndarray]]:
    """Per floor: every asset footprint grown by ASSET_MARGIN_M (same box as edit_ops.asset_shape), built in one
    vectorised call, with an STRtree over them."""
    rows: dict[str, list] = {}
    for asset in bm.assets.values():
        if asset.get("position") and asset.get("floor_id"):
            footprint = asset.get("footprint") or {}
            rows.setdefault(asset["floor_id"], []).append(
                (
                    asset["position"][0],
                    asset["position"][1],
                    footprint.get("width_m") or DEFAULT_SIZE_M,
                    footprint.get("depth_m") or DEFAULT_SIZE_M,
                    footprint.get("rotation_deg") or 0.0,
                )
            )
    trees = {}
    for floor_id, items in rows.items():
        x, y, width, depth, rotation = np.asarray(items, dtype=float).T
        half_w, half_d = width / 2 + ASSET_MARGIN_M, depth / 2 + ASSET_MARGIN_M
        cos, sin = np.cos(np.radians(rotation)), np.sin(np.radians(rotation))
        corners = np.stack([(-1, -1), (1, -1), (1, 1), (-1, 1)]).astype(float)
        local_x = corners[None, :, 0] * half_w[:, None]
        local_y = corners[None, :, 1] * half_d[:, None]
        ring = np.stack(
            [
                x[:, None] + local_x * cos[:, None] - local_y * sin[:, None],
                y[:, None] + local_x * sin[:, None] + local_y * cos[:, None],
            ],
            axis=2,
        )
        shapes = shapely.polygons(ring)
        trees[floor_id] = (shapely.STRtree(shapes), shapes)
    return trees


def room_entry(bm: BuildingMap, space_id: str, index: DrawIndex | None = None) -> tuple:
    """(free area, drawn anchor) of a room, cached until an asset or the room outline changes."""
    space = bm.spaces[space_id]
    index = index or draw_index(bm)
    key = (space_id, tuple(tuple(point) for point in space["polygon"]))
    if key not in index.rooms:
        polygon = outline(space["polygon"])
        walkable = polygon.buffer(-WALL_CLEARANCE_M)
        if walkable.is_empty:
            walkable = polygon
        blocked = []
        if space["floor_id"] in index.trees:
            tree, shapes = index.trees[space["floor_id"]]
            blocked = list(shapes[tree.query(walkable, predicate="intersects")])
        free = walkable.difference(unary_union(blocked)) if blocked else walkable
        index.rooms[key] = (free, step_out(free, bm.anchor(space_id)))
    return index.rooms[key]


def free_area(bm: BuildingMap, space_id: str, index: DrawIndex | None = None):
    return room_entry(bm, space_id, index)[0]


def drawn_anchor(bm: BuildingMap, space_id: str, index: DrawIndex | None = None) -> tuple[float, float]:
    """The room anchor, or the nearest point to it that is off every (grown) asset footprint."""
    return room_entry(bm, space_id, index)[1]


def step_out(free, point: tuple[float, float]) -> tuple[float, float]:
    """`point` if it lies in `free`, else the nearest point of `free` (nudged a little inside); unchanged if
    nothing is free."""
    if free.is_empty or free.covers(Point(point)):
        return (point[0], point[1])
    edge = nearest_points(free, Point(point))[0]
    inner = free.buffer(-INSIDE_NUDGE_M)
    if not inner.is_empty:
        nudged = nearest_points(inner, edge)[0]
        if nudged.distance(edge) <= 2 * INSIDE_NUDGE_M:
            edge = nudged
    return (edge.x, edge.y)


def ends_at_door(bm: BuildingMap, space_id: str) -> bool:
    """Big halls and zones: the route ends (or starts) at the door, the highlighted room is the target."""
    space = bm.spaces.get(space_id)
    if space is None:
        return False
    if str(space.get("room_type") or "").endswith(BIG_ROOM_TYPES):
        return True
    return outline(space["polygon"]).area >= BIG_ROOM_M2
