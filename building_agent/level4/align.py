"""Put the floors of a built building into one shared XY frame.

Every plan image is cropped to its own floor, so each converted floor starts in its own frame. Stairs and lifts sit at
the same XY on every floor they serve, so an upper floor is moved (translation only, no rotation) until its connector
rooms lie on those of a floor below. The translation that gives the largest overlap wins, and it is only used when the
match is solid: at least two connectors overlap well and they cover most of the smaller connector set. Otherwise the
floor stays where it is (offset 0) and the card says so. The first floor (lowest level) is the origin.

The offsets are stored in the building (`source_ref.floor_offsets_m`) so that later fixes given in image pixels can be
moved the same way."""

from shapely.affinity import translate
from shapely.geometry import Polygon

CONNECTOR_TYPES = ("stair", "lift")
MIN_MATCHED = 2  # connectors of the upper floor that must lie on one of the lower floor
MIN_ROOM_MATCH = 0.5  # share of the smaller connector that must overlap to count as matched
MIN_COVERAGE = 0.6  # overlapping area as a share of the smaller total connector area


def _connectors(building: dict, floor_id: str) -> list[tuple[str, Polygon]]:
    found = []
    for space in building["spaces"]:
        if space["floor_id"] != floor_id or space.get("type") not in CONNECTOR_TYPES:
            continue
        polygon = Polygon(space["polygon"])
        if polygon.is_valid and polygon.area > 0:
            found.append((space["type"], polygon))
    return found


def _overlap(moved: list[tuple[str, Polygon]], fixed: list[tuple[str, Polygon]]) -> tuple[float, int]:
    """(total overlap area, connectors of `moved` that lie on a connector of `fixed` of the same kind)."""
    total, matched = 0.0, 0
    for kind, polygon in moved:
        best, best_share = 0.0, 0.0
        for other_kind, other in fixed:
            if other_kind != kind or not polygon.intersects(other):
                continue
            area = polygon.intersection(other).area
            best = max(best, area)
            best_share = max(best_share, area / min(polygon.area, other.area))
        total += best
        matched += best_share >= MIN_ROOM_MATCH
    return total, matched


def best_translation(
    fixed: list[tuple[str, Polygon]], moving: list[tuple[str, Polygon]]
) -> tuple[tuple[float, float], str]:
    """((dx, dy), reason). The shift of `moving` onto `fixed`; (0, 0) with a reason when the match is not solid."""
    if not fixed or not moving:
        return (0.0, 0.0), "no stairs or lifts on one of the floors"
    candidates = {(0.0, 0.0)}
    for kind, polygon in moving:
        for other_kind, other in fixed:
            if kind == other_kind:
                candidates.add(
                    (round(other.centroid.x - polygon.centroid.x, 3), round(other.centroid.y - polygon.centroid.y, 3))
                )
    scored = []
    for dx, dy in candidates:
        area, matched = _overlap([(k, translate(p, dx, dy)) for k, p in moving], fixed)
        scored.append((area, matched, -(dx * dx + dy * dy), (dx, dy)))
    area, matched, _, shift = max(scored)
    smaller = min(sum(p.area for _, p in fixed), sum(p.area for _, p in moving))
    if matched < MIN_MATCHED:
        return (0.0, 0.0), f"only {matched} connector(s) match"
    if area / smaller < MIN_COVERAGE:
        return (0.0, 0.0), f"the connectors overlap by only {area / smaller:.0%}"
    return shift, ""


def align_floors(building: dict) -> tuple[dict[int, tuple[float, float]], dict[int, str]]:
    """Move the spaces and openings of every upper floor in place. Returns (offset per level, why not per level);
    a level is in the second dict when it could not be matched to any floor below (it then has offset (0, 0))."""
    levels = {floor["id"]: floor["level"] for floor in building["floors"]}
    ordered = sorted(levels.values())
    floor_id = {level: fid for fid, level in levels.items()}
    offsets = {level: (0.0, 0.0) for level in ordered}
    skipped: dict[int, str] = {}
    placed: list[int] = ordered[:1]
    for level in ordered[1:]:
        moving = _connectors(building, floor_id[level])
        reason = "no floor below to match"
        for below in reversed(placed):
            fixed = [
                (kind, translate(polygon, *offsets[below])) for kind, polygon in _connectors(building, floor_id[below])
            ]
            shift, reason = best_translation(fixed, moving)
            if not reason:
                offsets[level] = shift
                break
        else:
            skipped[level] = reason
        placed.append(level)
    for level, (dx, dy) in offsets.items():
        if dx == 0.0 and dy == 0.0:
            continue
        for space in building["spaces"]:
            if space["floor_id"] == floor_id[level]:
                space["polygon"] = [[round(x + dx, 3), round(y + dy, 3)] for x, y in space["polygon"]]
        for opening in building["openings"]:
            if opening["floor_id"] == floor_id[level]:
                x, y = opening["position"]
                opening["position"] = [round(x + dx, 3), round(y + dy, 3)]
    return offsets, skipped
