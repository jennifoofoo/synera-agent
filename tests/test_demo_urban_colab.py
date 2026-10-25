"""The demo round on the Munich Urban Colab (demo/buildings/plan-89323a15): fire extinguishers on the ground floor
from the main entrance room, planned by POST /api/round, must be as long as POST /api/route over the same legs
(device to device).

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
    # One stop per device: the page walks leg by leg from device to device (start_point / destination_point), so
    # the legs routed like that add up to the planned total.
    walked, here = 0.0, (start, None)
    for stop in planned["info"]["stops"]:
        body = {"building": KEY, "start": here[0], "destination": stop["space_id"]}
        if here[1]:
            body["start_point"] = {"x": here[1][0], "y": here[1][1]}
        if stop["position"]:
            body["destination_point"] = {"x": stop["position"][0], "y": stop["position"][1]}
        _, routed = app.post("/api/route", body)
        assert routed["route"]["ok"], routed["route"]
        walked += routed["route"]["length_m"]
        here = (stop["space_id"], stop["position"])
    assert abs(walked - planned["total_m"]) <= 1.0


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


def test_whole_building_round_is_exact_and_no_longer_than_before(tmp_path):
    """15 extinguishers on both floors from the Project Room: Held-Karp (exact up to 16 stops), at most the 294 m
    the team measured with nearest neighbour + 2-opt."""
    building = json.loads((DEMO / "building.json").read_text(encoding="utf-8"))
    devices = [a for a in building["assets"] if a["type"] == "fire_extinguisher"]
    if len(devices) != 15:
        pytest.skip("the Urban Colab extinguishers changed")
    start = next(s["id"] for s in building["spaces"] if s["name"].startswith("Project Room"))
    _, reply = app_with(tmp_path, building).post(
        "/api/round", {"building": KEY, "type": "fire extinguisher", "area": "", "start": start}
    )
    planned = reply["round"]
    assert planned["ok"] and len(planned["stops"]) == 15
    assert planned["order"].startswith("exact")
    assert planned["total_m"] <= 294.5
    assert reply["state"]["route"]["length_m"] == pytest.approx(planned["total_m"], abs=0.1)
