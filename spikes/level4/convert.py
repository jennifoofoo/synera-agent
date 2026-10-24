"""Deterministic converter: extraction JSON (pixels) -> building.json fragment for one floor (metres).

Scale modes:
- "true_width": metres per pixel from a known building width (experiment reference, or the user's answer)
- "door": assume a typical door is 0.9 m wide, use the median door width in px
- "bar": a printed scale bar (bar_m / bar_px)
Frame: x right, y up, bounding box of all rooms starts at (0, 0)."""

import statistics

TYPE_ROOM_TYPE = {"stair": "stairwell", "lift": "lift", "corridor": "corridor", "hall": "lobby"}
DEFAULT_DOOR_WIDTH_M = 0.9


def bbox(points: list[list[float]]) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def metres_per_pixel(extraction: dict, mode: str, true_width_m: float | None = None) -> float | None:
    rooms = extraction.get("rooms", [])
    if mode == "true_width" and true_width_m:
        x0, _, x1, _ = bbox([p for room in rooms for p in room["polygon_px"]])
        return true_width_m / (x1 - x0)
    if mode == "door":
        widths = [d["width_px"] for d in extraction.get("doors", []) if d.get("kind") == "door" and d.get("width_px")]
        return DEFAULT_DOOR_WIDTH_M / statistics.median(widths) if widths else None
    if mode == "bar":
        scale = extraction.get("scale") or {}
        if scale.get("bar_px") and scale.get("bar_m"):
            return scale["bar_m"] / scale["bar_px"]
    return None


def convert(extraction: dict, building_id: str, level: int, scale: float) -> dict:
    """Return {floors, spaces, openings, vertical_connectors, assets, warnings} for one floor."""
    rooms = [r for r in extraction.get("rooms", []) if len(r.get("polygon_px") or []) >= 3]
    x0, _, _, y1 = bbox([p for room in rooms for p in room["polygon_px"]])
    floor_id = f"{building_id}-F{level}"

    def to_m(point: list[float]) -> list[float]:
        return [round((point[0] - x0) * scale, 3), round((y1 - point[1]) * scale, 3)]

    warnings: list[str] = []
    id_map: dict[str, str] = {}
    spaces = []
    for index, room in enumerate(rooms):
        space_id = f"{floor_id}-S{index:03d}"
        id_map[room["id"]] = space_id
        kind = room.get("type") or "room"
        room_type = room.get("room_type") or TYPE_ROOM_TYPE.get(kind, "generic_room")
        spaces.append(
            {
                "id": space_id,
                "floor_id": floor_id,
                "type": kind,
                "room_type": TYPE_ROOM_TYPE.get(kind, room_type),
                "name": room.get("name") or room.get("ref") or room["id"],
                "ref": room.get("ref"),
                "polygon": [to_m(p) for p in room["polygon_px"]],
                "synthetic": False,
            }
        )
    openings = []
    for index, door in enumerate(extraction.get("doors", [])):
        ends = [id_map.get(r, "outside" if r == "outside" else None) for r in door.get("rooms", [])]
        if len(ends) != 2 or None in ends or ends[0] == ends[1]:
            warnings.append(f"door {index} joins unknown or identical rooms: {door.get('rooms')}")
            continue
        width_m = round(door["width_px"] * scale, 2) if door.get("width_px") else DEFAULT_DOOR_WIDTH_M
        openings.append(
            {
                "id": f"{floor_id}-O{index:04d}",
                "floor_id": floor_id,
                "space_ids": ends,
                "kind": door.get("kind") or "door",
                "position": to_m(door["position_px"]),
                "width_m": width_m,
                "step_free": True,
                "synthetic": False,
            }
        )
    floor = {
        "id": floor_id,
        "level": level,
        "name": f"Floor {level}",
        "elevation_m": 0.0,
        "height_m": 3.0,
    }
    return {
        "floors": [floor],
        "spaces": spaces,
        "openings": openings,
        "vertical_connectors": [],
        "assets": [],
        "warnings": warnings,
    }
