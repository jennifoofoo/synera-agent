"""Drawing-only geometry for the page's route line: keep it off furniture.

Nothing here changes a route (length, rooms, steps, Answer: lines). The routing model ignores assets on purpose
(Synera's rules); this module only moves and adds drawn points so the line does not start, end or run on a
machine. Doors stay the hand-over points between rooms.

- `free_area`: the walkable part of a room (15 cm off the walls) minus every asset footprint grown by
  ASSET_MARGIN_M. Cached per room; the cache is keyed on a signature of all assets, so moving, adding or
  removing an asset in the chat invalidates it.
- `drawn_anchor`: the room anchor if it is free, else the nearest free point (the anchor if nothing is free).
- `ends_at_door`: big halls and production/warehouse zones: the line stops at the door it enters by.
- `detour`: inside one room, the shortest line from point to point that keeps off the grown footprints (A* over
  the reflex corners of the free area, visibility checked lazily and cached per room). None if there is none:
  the caller then keeps the straight line."""

import heapq
import math
import weakref
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point, box
from shapely.geometry.polygon import orient
from shapely.ops import nearest_points, unary_union

from starter_agent.building_map import COVER_TOLERANCE_M, WALL_CLEARANCE_M, BuildingMap, outline

ASSET_MARGIN_M = 0.3  # how far the drawn line keeps off an asset footprint
BIG_ROOM_M2 = 150.0  # rooms at least this large: the line ends at their door, the room itself is the target
BIG_ROOM_TYPES = ("_zone",)  # room_type suffixes (production_zone, warehouse_zone, ...) treated as big
DEFAULT_SIZE_M = 0.5  # edit_ops.asset_shape's size for an asset without a footprint
INSIDE_NUDGE_M = 0.05  # a stepped-out point moves this far into the free area, off its edge
TIGHT_MARGIN_M = 0.12  # fallback margin round assets when the normal one closes every gap
TIGHT_WALL_M = 0.05  # fallback wall clearance
MAX_STEP_M = 1.0  # a line end never jumps further than this to reach the free area
WINDOW_PADS_M = (3.0, 8.0)  # search windows round a blocked line, before the whole room
MAX_ROOM_CORNERS = 250  # above this, a whole-room search is too slow for the page
SMOOTH_M = 0.1  # simplify tolerance for a detour, kept only if the simpler line still stays free


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


def step_out(free, point, inner=None) -> tuple[float, float]:
    """`point` if it lies in `free`, else the nearest point of `free` (nudged a little inside); unchanged if
    nothing is free. `inner`: free shrunk by INSIDE_NUDGE_M, if the caller has it."""
    if free.is_empty or free.covers(Point(point)):
        return (float(point[0]), float(point[1]))
    edge = nearest_points(free, Point(point))[0]
    inner = free.buffer(-INSIDE_NUDGE_M) if inner is None else inner
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


# ---------- walk round the assets inside a room ----------


@dataclass
class RoomPaths:
    """What a room needs to draw a walk round its assets: the obstacles, the free parts with the corners a
    shortest walk can bend at, and the visibility rows found so far (one per expanded corner, filled lazily)."""

    blocked: object  # union of grown footprints touching the room (prepared), or None
    parts: list  # per free part: (allowed polygon (prepared), corners array)
    free: object  # the free area
    inner: object  # free area shrunk by INSIDE_NUDGE_M, for stepping points out
    rows: dict = field(default_factory=dict)  # part -> corner -> bool row: which corners it sees


def room_paths(bm: BuildingMap, space_id: str, index: DrawIndex, tight: bool = False) -> RoomPaths:
    """Per room, cached with the index. tight: the fallback when the normal margins leave no free walk (a gap
    between two machines narrower than both margins): assets grown by TIGHT_MARGIN_M only, walls TIGHT_WALL_M."""
    space = bm.spaces[space_id]
    key = ("paths", tight, space_id, tuple(tuple(point) for point in space["polygon"]))
    if key not in index.rooms:
        polygon = outline(space["polygon"])
        hits = np.empty(0, dtype=object)
        if space["floor_id"] in index.trees:
            tree, shapes = index.trees[space["floor_id"]]
            hits = shapes[tree.query(polygon, predicate="intersects")]
        blocked = None
        if len(hits):
            if tight:
                hits = shapely.buffer(hits, TIGHT_MARGIN_M - ASSET_MARGIN_M, join_style="mitre")
            blocked = unary_union(list(hits))
            shapely.prepare(blocked)
        if tight:
            walkable = polygon.buffer(-TIGHT_WALL_M)
            free = walkable.difference(blocked) if blocked is not None else walkable
        else:
            free = room_entry(bm, space_id, index)[0]
        parts = []
        for part in parts_of(free):
            allowed = part.buffer(COVER_TOLERANCE_M)
            shapely.prepare(allowed)
            parts.append((allowed, bend_corners(part)))
        index.rooms[key] = RoomPaths(blocked, parts, free, free.buffer(-INSIDE_NUDGE_M))
    return index.rooms[key]


def bend_corners(part) -> np.ndarray:
    """Corners where a shortest walk can bend: the reflex corners of the free area. After orient() the free area
    lies left of every ring, so a right turn is a reflex corner."""
    oriented = orient(part)
    found = []
    for ring in [oriented.exterior, *oriented.interiors]:
        coords = np.asarray(ring.coords)[:-1, :2]
        if len(coords) < 3:
            continue
        incoming = coords - np.roll(coords, 1, axis=0)
        outgoing = np.roll(coords, -1, axis=0) - coords
        cross = incoming[:, 0] * outgoing[:, 1] - incoming[:, 1] * outgoing[:, 0]
        found.append(coords[cross < -1e-9])
    return np.concatenate(found) if found else np.empty((0, 2))


def sees(allowed, origin: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """Which targets a straight line from origin reaches without leaving `allowed`."""
    if not len(targets):
        return np.zeros(0, dtype=bool)
    lines = shapely.linestrings(np.stack([np.broadcast_to(origin, targets.shape), targets], axis=1))
    return shapely.covers(allowed, lines)


def detour(bm: BuildingMap, space_id: str, start, end, index: DrawIndex) -> list[tuple[float, float]] | None:
    """Points to draw between `start` and `end` (both excluded) so the line inside the room keeps off its assets.
    [] if the straight line is already clear, None if no free walk exists (the caller keeps the straight line).
    A start or end on a footprint (or a door in the wall) first steps to the nearest free point. Tries the normal
    margins first, then the tight ones."""
    paths = room_paths(bm, space_id, index)
    if paths.blocked is None or tuple(start) == tuple(end):
        return []
    if not paths.blocked.intersects(LineString([start, end])):
        return []
    for tight in (False, True):
        paths = room_paths(bm, space_id, index, tight)
        walk = free_walk(paths, start, end)
        if walk is not None:
            return [point for point in walk if point not in (tuple(start), tuple(end))]
    return None


def free_walk(paths: RoomPaths, start, end) -> list | None:
    """The walk first -> bends -> last inside the free area, or None. Looks in a window round the two points
    first (big corridors have hundreds of corners), then in the whole room unless that is too big to be fast."""
    first, last = step_out(paths.free, start, paths.inner), step_out(paths.free, end, paths.inner)
    if max(math.dist(first, start), math.dist(last, end)) > MAX_STEP_M:
        return None  # the free area is far from this point (a narrow nook): no sensible line in this tier
    low = np.minimum(first, last)
    high = np.maximum(first, last)
    for pad in WINDOW_PADS_M:
        window = box(*(low - pad), *(high + pad))
        if window.covers(paths.free):
            break
        for part in parts_of(paths.free.intersection(window)):
            allowed = part.buffer(COVER_TOLERANCE_M)
            shapely.prepare(allowed)
            if allowed.covers(Point(first)) and allowed.covers(Point(last)):
                bends = shortest_walk({}, allowed, bend_corners(part), np.asarray(first), np.asarray(last))
                if bends is not None:
                    return smoothed([first, *bends, last], allowed)
    for number, (allowed, corners) in enumerate(paths.parts):
        if allowed.covers(Point(first)) and allowed.covers(Point(last)):
            if len(corners) > MAX_ROOM_CORNERS:
                return None  # too many corners to search the whole room quickly: keep the straight line
            rows = paths.rows.setdefault(number, {})
            bends = shortest_walk(rows, allowed, corners, np.asarray(first), np.asarray(last))
            return None if bends is None else smoothed([first, *bends, last], allowed)
    return None


def parts_of(geometry) -> list:
    return [
        part for part in getattr(geometry, "geoms", [geometry]) if part.geom_type == "Polygon" and not part.is_empty
    ]


def shortest_walk(rows: dict, allowed, corners: np.ndarray, first, last) -> list | None:
    """A* from first to last over the bend corners; a corner's visibility is computed when it is expanded and
    kept for later routes. Returns the corners bent at, or None if last cannot be reached."""
    if bool(sees(allowed, first, last[None, :])[0]):
        return []
    goal, start = len(corners), len(corners) + 1
    best, came, done = {start: 0.0}, {}, set()
    to_goal = np.hypot(*(corners - last).T)
    goal_seen = sees(allowed, last, corners)
    queue = [(float(np.hypot(*(last - first))), start)]
    while queue:
        _, node = heapq.heappop(queue)
        if node == goal:
            bends = []
            while came.get(node, start) != start:
                node = came[node]
                bends.append((float(corners[node][0]), float(corners[node][1])))
            return bends[::-1]
        if node in done:
            continue
        done.add(node)
        origin = first if node == start else corners[node]
        if node == start:
            visible = sees(allowed, first, corners)
        else:
            visible = rows.get(node)
            if visible is None:
                visible = rows[node] = sees(allowed, origin, corners)
        distances = np.hypot(*(corners - origin).T)
        steps = [(int(i), float(distances[i])) for i in np.flatnonzero(visible) if i != node and i not in done]
        if node != start and goal_seen[node]:
            steps.append((goal, float(np.hypot(*(last - origin)))))
        for target, step in steps:
            cost = best[node] + step
            if cost < best.get(target, math.inf) - 1e-9:
                best[target], came[target] = cost, node
                heapq.heappush(queue, (cost + (0.0 if target == goal else float(to_goal[target])), target))
    return None


def smoothed(points: list, allowed) -> list[tuple[float, float]]:
    """The walk simplified with SMOOTH_M (no zigzag from near-collinear corners), if that still stays free."""
    line = LineString(points)
    simple = line.simplify(SMOOTH_M, preserve_topology=False)
    chosen = simple if len(simple.coords) >= 2 and allowed.covers(simple) else line
    return [(float(x), float(y)) for x, y in chosen.coords]


# ---------- thread the line straight through a door ----------

APPROACH_M = 0.5  # the line meets a door along its wall normal from this far inside each room
APPROACH_MIN_M = 0.2  # never closer than this (shallow rooms, assets near the door)
APPROACH_STEP_M = 0.05  # how the approach shortens when its point or segment is not free
WIDE_OPENING_M = 3.0  # openings at least this wide (hall passages) have no jambs to cut: no approach
SHARED_WALL_M = 0.3  # how far apart two rooms' outlines may lie and still count as one wall at a door


def door_approach(
    bm: BuildingMap, opening_id: str, space_id: str, index: DrawIndex | None = None
) -> tuple[float, float] | None:
    """The point inside `space_id` the line passes before (after) the door, so it crosses the doorway along the
    wall normal instead of cutting the jambs: min(APPROACH_M, half the room depth behind the door, at least
    APPROACH_MIN_M) along the normal, shortened until the point is free and the short segment to the door keeps
    off the assets. None for wide openings, outside, or when no such point exists (the door is then the turn)."""
    opening = bm.openings.get(opening_id)
    space = bm.spaces.get(space_id)
    if opening is None or space is None or (opening.get("width_m") or 0.0) >= WIDE_OPENING_M:
        return None
    index = index or draw_index(bm)
    key = ("approach", opening_id, space_id, tuple(opening["position"][:2]), tuple(map(tuple, space["polygon"])))
    if key not in index.rooms:
        index.rooms[key] = find_approach(bm, opening, space_id, index)
    return index.rooms[key]


def find_approach(bm: BuildingMap, opening: dict, space_id: str, index: DrawIndex) -> tuple[float, float] | None:
    polygon = outline(bm.spaces[space_id]["polygon"])
    door = np.asarray(opening["position"][:2], dtype=float)
    if polygon.exterior.distance(Point(door)) > SHARED_WALL_M:
        return None  # not in this room's wall (a synthetic hand-over inside a stairwell or lift): keep the turn
    other = bm.other_side(opening, space_id)
    other_polygon = outline(bm.spaces[other]["polygon"]) if other in bm.spaces else None
    normal = wall_normal(polygon, other_polygon, door, opening.get("width_m") or 1.0)
    span = span_along(polygon, door, normal)
    if span is None:
        return None
    enter, leave = span
    for tight in (False, True):  # an asset close in front of the door: try the tight margins before giving up
        paths = room_paths(bm, space_id, index, tight)
        distance = enter + min(APPROACH_M, (leave - enter) / 2)
        while distance >= enter + APPROACH_MIN_M - 1e-9:
            point = door + normal * distance
            free = paths.free.is_empty or paths.free.covers(Point(point))
            clear = paths.blocked is None or not paths.blocked.intersects(LineString([door, point]))
            if free and clear:
                return (float(point[0]), float(point[1]))
            distance -= APPROACH_STEP_M
    return None


def wall_normal(polygon, other_polygon, door: np.ndarray, width: float) -> np.ndarray:
    """Unit normal of the wall the door sits in, pointing into `polygon`: the room's outline edge nearest the door
    (a door in a thick wall sits a little off it); at a corner, of the edges about as near, the one the room on
    the other side lies along (its outline within SHARED_WALL_M)."""
    ring = np.asarray(orient(polygon).exterior.coords)[:, :2]  # counter-clockwise: the room is left of every edge
    starts, edges = ring[:-1], np.diff(ring, axis=0)
    lengths = np.hypot(*edges.T)
    keep = lengths > 1e-9
    starts, edges, lengths = starts[keep], edges[keep], lengths[keep]
    along = np.clip(np.einsum("ij,ij->i", door - starts, edges) / lengths**2, 0.0, 1.0)
    distances = np.hypot(*(starts + edges * along[:, None] - door).T)
    near = distances <= distances.min() + 0.05
    chosen = int(np.argmin(distances))
    if other_polygon is not None and near.sum() > 1:
        around = Point(door).buffer(max(width / 2, APPROACH_M))
        shared = other_polygon.buffer(SHARED_WALL_M).intersection(around)
        overlap = [
            LineString([starts[i], starts[i] + edges[i]]).intersection(shared).length if near[i] else -1.0
            for i in range(len(edges))
        ]
        chosen = int(np.argmax(overlap))
    direction = edges[chosen] / lengths[chosen]
    return np.array([-direction[1], direction[0]])


def span_along(polygon, door: np.ndarray, normal: np.ndarray) -> tuple[float, float] | None:
    """(enter, leave): how far from the door the ray along `normal` enters the room and leaves it again. None if
    it enters further than SHARED_WALL_M away (the door is not in this wall) or the room is too shallow there."""
    reach = math.hypot(*np.subtract(polygon.bounds[2:], polygon.bounds[:2])) + 1.0
    inside = LineString([door, door + normal * reach]).intersection(polygon)
    spans = [
        sorted(math.dist(door, coord[:2]) for coord in part.coords)
        for part in getattr(inside, "geoms", [inside])
        if part.geom_type == "LineString" and not part.is_empty
    ]
    if not spans:
        return None
    enter, leave = min(spans)[0], min(spans)[-1]
    if enter > SHARED_WALL_M or leave - enter < 2 * APPROACH_MIN_M:
        return None
    return enter, leave
