"""The 3D view (web/static/view3d.js, scene3d.js): the data it needs from building_view, the vendored three.js
that keeps the page working offline, and the steering API documented in web/README.md. No API calls, no browser."""

import json
from pathlib import Path

import pytest

from web import api
from web.server import App

DATA = Path("data")
STATIC = Path("web/static")
VENDOR = STATIC / "vendor" / "three"
STEERING_API = [
    "show",
    "hide",
    "setFloorMode",
    "focusFloor",
    "focus",
    "highlight",
    "clearHighlights",
    "flyTo",
    "showRoute",
    "playRoute",
    "setThings",
    "resetView",
    "apply",
    "stats",
    "benchmark",
    "state",
]


def building_keys() -> list[str]:
    keys = sorted(path.parent.relative_to(DATA).as_posix() for path in (DATA / "dev").glob("*/building.json"))
    if not keys:
        pytest.skip("no kit data (scripts/get_data.sh)")
    return keys


def test_building_view_carries_floor_heights_and_asset_footprints():
    app = App(DATA)
    for key in building_keys()[:6]:
        view = api.building_view(app.session(key))
        raw = json.loads((DATA / key / "building.json").read_text(encoding="utf-8"))
        floors = {floor["id"]: floor for floor in raw["floors"]}
        for floor in view["floors"]:
            assert floor["elevation_m"] == pytest.approx(floors[floor["id"]]["elevation_m"], abs=0.01)
            assert floor["height_m"] == pytest.approx(floors[floor["id"]]["height_m"], abs=0.01)
        footprints = {asset["id"]: asset.get("footprint") for asset in raw["assets"]}
        for asset in view["assets"]:
            expected = footprints[asset["id"]]
            if expected:
                assert asset["footprint"]["width_m"] == pytest.approx(expected["width_m"], abs=0.01)
                assert asset["footprint"]["depth_m"] == pytest.approx(expected["depth_m"], abs=0.01)
                assert asset["footprint"]["rotation_deg"] == pytest.approx(expected.get("rotation_deg") or 0, abs=0.1)


def test_floor_without_heights_is_stacked_by_level():
    """Level 4 drafts may come without heights: the 3D view still gets a usable stack."""
    floor = api.floor_view({"id": "F2", "level": 2, "name": "Floor 2"})
    assert floor == {"id": "F2", "level": 2, "name": "Floor 2", "elevation_m": 6.0, "height_m": 3.0}
    basement = api.floor_view({"id": "B", "level": -1, "name": "Basement", "height_m": 4.0})
    assert basement["elevation_m"] == -4.0
    assert api.footprint_view(None) is None
    assert api.footprint_view({"width_m": 0, "depth_m": 1}) is None
