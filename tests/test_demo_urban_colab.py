"""The demo round on the Munich Urban Colab (demo/buildings/plan-89323a15): fire extinguishers on the ground floor
from the main entrance room, planned by POST /api/round, must be as long as POST /api/route over the same stops.

The demo link (docs/submission/VIDEO_2MIN.md):
    http://localhost:8798/?building=user/plan-89323a15#round=fire_extinguisher&area=Ground%20floor
"""

import json
import shutil
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from web.server import App

DEMO = Path("demo/buildings/plan-89323a15")
KEY = "user/plan-89323a15"


def main_entrance_room(building: dict) -> str:
    """The page's default start (twin/src/round/choices.ts entranceRoom): the room behind the first entrance, by id."""
    return min(o["space_ids"][0] for o in building["openings"] if o["kind"] == "entrance" and o["space_ids"])


def ground_floor_extinguishers(building: dict) -> list[dict]:
    ground = {floor["id"] for floor in building["floors"] if floor["level"] == 0}
    return [a for a in building["assets"] if a["type"] == "fire_extinguisher" and a["floor_id"] in ground]


def app_with(tmp_path: Path, building: dict) -> App:
    buildings = tmp_path / "buildings"
    shutil.copytree(DEMO, buildings / DEMO.name)
    (buildings / DEMO.name / "building.json").write_text(json.dumps(building), encoding="utf-8")
    return App(Path("data"), tmp_path / "uploads", buildings, knowledge_root=tmp_path / "knowledge")


def assert_round_matches_route(app: App, building: dict) -> None:
    start = main_entrance_room(building)
    _, reply = app.post(
        "/api/round", {"building": KEY, "type": "fire extinguisher", "area": "Ground floor", "start": start}
    )
    planned = reply["round"]
    assert planned["ok"], planned
    stops = [stop["space_id"] for stop in planned["info"]["stops"]]
    assert len(stops) > 0
    assert planned["devices"] == len(ground_floor_extinguishers(building))
    _, routed = app.post("/api/route", {"building": KEY, "start": start, "destination": stops[-1], "via": stops[:-1]})
    assert routed["route"]["ok"], routed["route"]
    assert abs(routed["route"]["length_m"] - planned["total_m"]) <= 1.0


def test_demo_round_on_the_urban_colab(tmp_path):
    building = json.loads((DEMO / "building.json").read_text(encoding="utf-8"))
    if not ground_floor_extinguishers(building):
        pytest.skip("Urban Colab has no fire extinguishers on the ground floor yet (to be added from the plan photos)")
    assert_round_matches_route(app_with(tmp_path, building), building)


def test_round_on_the_urban_colab_with_extinguishers_in_some_rooms(tmp_path):
    """Until the real extinguishers are in: the same check with one test extinguisher in a few ground-floor rooms,
    so the round and the route agree on this building's doors and corridors now."""
    building = json.loads((DEMO / "building.json").read_text(encoding="utf-8"))
    ground = next(floor["id"] for floor in building["floors"] if floor["level"] == 0)
    rooms = [s for s in building["spaces"] if s["floor_id"] == ground and s["type"] in ("room", "hall", "corridor")]
    for number, space in enumerate(rooms[::4], start=1):
        point = Polygon(space["polygon"]).representative_point()
        building["assets"].append(
            {
                "id": f"test-fe-{number}",
                "name": f"Fire extinguisher T{number}",
                "category": "equipment",
                "type": "fire_extinguisher",
                "space_id": space["id"],
                "floor_id": ground,
                "position": [round(point.x, 2), round(point.y, 2)],
                "footprint": {"width_m": 0.3, "depth_m": 0.3, "rotation_deg": 0.0},
            }
        )
    assert_round_matches_route(app_with(tmp_path, building), building)
