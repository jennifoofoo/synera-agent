"""The 3D view (web/static/view3d.js, scene3d.js): the data it needs from building_view, the vendored three.js
that keeps the page working offline, and the steering API documented in web/README.md. No API calls, no browser."""

import json
import re
import threading
import urllib.request
from pathlib import Path

import pytest

from web import api
from web.server import App, make_handler

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


def test_three_is_vendored_pinned_and_loaded_without_a_cdn():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    import_map = json.loads(re.search(r'<script type="importmap">(.*?)</script>', html, re.DOTALL).group(1))["imports"]
    assert import_map["three"] == "./vendor/three/three.module.min.js"
    assert (STATIC / import_map["three"]).is_file()
    assert (STATIC / import_map["three/addons/"] / "OrbitControls.js").is_file()
    assert "MIT License" in (VENDOR / "LICENSE").read_text(encoding="utf-8")
    assert 'const t="170"' in (VENDOR / "three.module.min.js").read_text(encoding="utf-8")[:400]
    # Offline demo: nothing on the page is fetched from the internet.
    for path in [STATIC / "index.html", *STATIC.glob("*.js")]:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"""(src|href|from|import)\s*[=(]?\s*["']https?://""", text), path


def test_steering_api_is_implemented_and_documented():
    source = (STATIC / "view3d.js").read_text(encoding="utf-8")
    readme = Path("web/README.md").read_text(encoding="utf-8")
    assert "window.view3d = api" in source
    for name in STEERING_API:
        assert re.search(rf"^\s+{name}\(", source, re.MULTILINE), f"view3d.{name} missing in view3d.js"
        assert f"view3d.{name}(" in readme, f"view3d.{name} missing in web/README.md"
    # A chat reply can carry {"view": {...}} for the 3D view.
    assert "window.view3d?.apply(result.view)" in (STATIC / "app.js").read_text(encoding="utf-8")


def test_server_serves_the_3d_modules():
    from http.server import ThreadingHTTPServer

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App(DATA)))
    except PermissionError:
        pytest.skip("local port binding is not allowed here")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        for path in (
            "/view3d.js",
            "/scene3d.js",
            "/vendor/three/three.module.min.js",
            "/vendor/three/OrbitControls.js",
        ):
            with urllib.request.urlopen(base + path) as response:
                assert response.status == 200
                assert "javascript" in response.headers["Content-Type"]
    finally:
        server.shutdown()
