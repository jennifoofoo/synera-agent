"""What the person clicked on the page, checked against the building before the agent may see it.

The page sends {space_id, asset_id, point [x, y] in model metres (+y north), floor_id}. Nothing here trusts the
client: ids must exist, numbers must be finite and sane, the floor must match the room. Any bad field drops the
whole selection (the reason says which). Only a point outside its room is dropped on its own, with a note."""

import math
from dataclasses import dataclass

from shapely.geometry import Point, Polygon

from starter_agent.building_map import BuildingMap

MAX_COORDINATE_M = 1_000_000.0
MAX_ID_LENGTH = 200


@dataclass(frozen=True)
class Selection:
    space_id: str | None = None
    asset_id: str | None = None
    point: tuple[float, float] | None = None
    floor_id: str | None = None
    note: str = ""


@dataclass(frozen=True)
class SelectionCheck:
    selection: Selection | None
    reason: str = ""


def text_id(raw: dict, name: str) -> str | None:
    value = raw.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > MAX_ID_LENGTH:
        raise ValueError(f"{name} must be a short text")
    return value


def read_point(value) -> tuple[float, float]:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise ValueError("point must be [x, y]")
    for number in value:
        if isinstance(number, bool) or not isinstance(number, int | float) or not math.isfinite(number):
            raise ValueError("point must be two finite numbers")
        if abs(number) > MAX_COORDINATE_M:
            raise ValueError("point is out of range")
    return float(value[0]), float(value[1])


def check_selection(raw, bm: BuildingMap) -> SelectionCheck:
    """Validate a client selection. Never raises."""
    if raw is None:
        return SelectionCheck(None)
    if not isinstance(raw, dict):
        return SelectionCheck(None, "context must be an object")
    try:
        space_id, asset_id, floor_id = (text_id(raw, name) for name in ("space_id", "asset_id", "floor_id"))
        point = read_point(raw["point"]) if raw.get("point") is not None else None
    except ValueError as error:
        return SelectionCheck(None, str(error))
    if space_id is not None and space_id not in bm.spaces:
        return SelectionCheck(None, "unknown space")
    if asset_id is not None:
        if asset_id not in bm.assets:
            return SelectionCheck(None, "unknown asset")
        asset_space = bm.assets[asset_id]["space_id"]
        if space_id is not None and asset_space != space_id:
            return SelectionCheck(None, "asset is not in that space")
        space_id = space_id or asset_space
    if floor_id is not None and floor_id not in bm.floors:
        return SelectionCheck(None, "unknown floor")
    if space_id is not None:
        space_floor = bm.spaces[space_id]["floor_id"]
        if floor_id is not None and floor_id != space_floor:
            return SelectionCheck(None, "floor does not match the space")
        floor_id = space_floor
    note = ""
    if point is not None:
        if space_id is not None:
            if not Polygon(bm.spaces[space_id]["polygon"]).buffer(1e-6).contains(Point(point)):
                point, note = None, "The clicked point is outside the selected room and was dropped."
        elif floor_id is None:
            return SelectionCheck(None, "point needs a floor or a space")
    if space_id is None and asset_id is None and point is None:
        return SelectionCheck(None, "nothing selected")
    return SelectionCheck(Selection(space_id, asset_id, point, floor_id, note))


def validate_selection(raw, bm: BuildingMap) -> Selection | None:
    return check_selection(raw, bm).selection


@dataclass(frozen=True)
class HereCheck:
    """The page's "I'm here" click, checked: a room is required, the point is optional, {"clear": true} forgets."""

    space_id: str | None = None
    floor_id: str | None = None
    point: tuple[float, float] | None = None
    clear: bool = False
    reason: str = ""
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.clear or self.space_id is not None


def check_here(raw, bm: BuildingMap) -> HereCheck:
    """Validate context['here'] = {space_id, point?, floor_id?}. Never raises; an unknown id drops the whole thing.

    Same rules as the selection: the room must exist, numbers must be finite, the floor must match the room. A
    point outside the room is dropped on its own, with a note. Never read from message text."""
    if raw is None:
        return HereCheck()
    if not isinstance(raw, dict):
        return HereCheck(reason="here must be an object")
    if raw.get("clear") is True:
        return HereCheck(clear=True)
    try:
        space_id, floor_id = text_id(raw, "space_id"), text_id(raw, "floor_id")
        point = read_point(raw["point"]) if raw.get("point") is not None else None
    except ValueError as error:
        return HereCheck(reason=str(error))
    if space_id is None:
        return HereCheck(reason="here needs a space_id")
    if space_id not in bm.spaces:
        return HereCheck(reason="unknown space")
    if floor_id is not None and floor_id != bm.spaces[space_id]["floor_id"]:
        return HereCheck(reason="floor does not match the space")
    note = ""
    if point is not None and not Polygon(bm.spaces[space_id]["polygon"]).buffer(1e-6).contains(Point(point)):
        point, note = None, "The point is outside the room and was dropped."
    return HereCheck(space_id, bm.spaces[space_id]["floor_id"], point, note=note)
