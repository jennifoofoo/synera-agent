"""The drawn route line keeps its ends off furniture and stops at the door of big halls. Drawing only: the route
itself (length, rooms, steps) stays exactly what the people model says."""

import itertools
import json
import time
from pathlib import Path

import pytest
from shapely.geometry import LineString, Point

from building_agent import routing
from building_agent.edit_ops import asset_shape
from tests.conftest import DATA
from tests.test_web_routing import case_request, sample, session_for
from web import api, route_draw

LARGEST = DATA / "dev" / "osm-way27917482"  # about 5000 assets
FACTORY = DATA / "dev" / "proc-factory-dev-012"  # Jennifer's screenshot: Warehouse zone H-B3 -> Production zone H-A2
TOUCH_MARGIN_M = 0.1


def footprints(bm, floor_id: str) -> list:
    return [
        asset_shape(a, a["position"][0], a["position"][1]).buffer(TOUCH_MARGIN_M)
        for a in bm.assets.values()
        if a.get("position") and a.get("floor_id") == floor_id
    ]


def door_points(bm) -> set:
    return {tuple(api.rounded(o["position"])) for o in bm.openings.values()}


def space_by_name(bm, name: str) -> str:
    return next(space_id for space_id, space in bm.spaces.items() if space["name"] == name)


@pytest.mark.parametrize("index", range(len(sample())))
def test_line_ends_are_off_furniture_and_the_route_is_unchanged(index):
    building_dir, kind, answer = sample()[index]
    start, end, step_free, via = case_request(kind, answer)
    session = session_for(building_dir)
    bm = session.map
    if answer.get("closed_element_id"):
        bm.set_closed(answer["closed_element_id"], True)
    page = api.route_view(session, start, end, step_free, via)
    agent = routing.route(bm, start, end, step_free, via)
    assert (page["length_m"], page["space_path"]) == (agent.length_m, agent.space_path)
    assert page["steps"] == api.compact_steps(agent.steps)
    doors = door_points(bm)
    for segment, at in ((page["segments"][0], 0), (page["segments"][-1], -1)):
        point = tuple(segment["points"][at])
        if point in doors:
            continue
        space_id = page["space_path"][0 if at == 0 else -1]
        if route_draw.free_area(bm, space_id).is_empty:
            continue  # nothing is free in this room: the anchor stays
        hit = [f for f in footprints(bm, segment["floor_id"]) if f.contains(Point(point))]
        assert not hit, (space_id, point)


def test_big_hall_route_ends_at_the_door():
    session = session_for(str(FACTORY))
    bm = session.map
    start, end = space_by_name(bm, "Warehouse zone H-B3"), space_by_name(bm, "Production zone H-A2")
    page = api.route_view(session, start, end)
    assert page["length_m"] == routing.route(bm, start, end).length_m
    points = [tuple(point) for segment in page["segments"] for point in segment["points"]]
    end_doors = {tuple(api.rounded(o["position"])) for o in bm.openings.values() if end in o["space_ids"]}
    assert points[-1] in end_doors
    assert len(set(points)) >= 2


def test_moving_an_asset_onto_the_anchor_moves_the_drawn_end():
    session = session_for(str(FACTORY))
    bm = session.map
    room = next(s for s in bm.spaces.values() if not route_draw.ends_at_door(bm, s["id"]) and s["type"] == "room")
    before = route_draw.drawn_anchor(bm, room["id"])
    asset = next(a for a in bm.assets.values() if a.get("position"))
    anchor = bm.anchor(room["id"])
    asset.update(space_id=room["id"], floor_id=room["floor_id"], position=[anchor[0], anchor[1]])
    after = route_draw.drawn_anchor(bm, room["id"])
    assert after != before
    assert not asset_shape(asset, *anchor).buffer(TOUCH_MARGIN_M).contains(Point(after))


def test_drawing_is_fast_on_the_largest_building():
    """Drawing budget (route_geometry only, routing excluded): ~150 ms per route on the largest building, cold
    caches included. The assert leaves headroom for a loaded machine."""
    bm = api.RecordingMap.load(LARGEST)
    slowest = 0.0
    for start, end, step_free, via in route_requests(LARGEST):
        stops = [bm.resolve_space(stop) for stop in [start, *via, end]]
        legs = api.route_legs(bm, stops, step_free, [])
        if legs is None:
            continue
        began = time.perf_counter()
        api.route_geometry(bm, stops, legs)
        slowest = max(slowest, time.perf_counter() - began)
    assert slowest < 0.4, slowest
    began = time.perf_counter()
    route_draw.draw_index(bm)
    assert time.perf_counter() - began < 0.05, "asset signature check must stay cheap"


def route_requests(building: Path) -> list[tuple[str, str, bool, list[str]]]:
    requests = []
    for line in (building / "questions_basic.jsonl").read_text(encoding="utf-8").splitlines():
        question = json.loads(line)
        if question["kind"] in ("route", "route_step_free", "tour"):
            requests.append(case_request(question["kind"], question["answer"]))
    return requests


DEV_BUILDINGS = sorted(path.parent.name for path in (DATA / "dev").glob("*/questions_basic.jsonl"))


@pytest.mark.parametrize("building", DEV_BUILDINGS)
def test_drawn_line_walks_round_assets(building, monkeypatch):
    """Every drawn walk keeps off the asset footprints (plus 10 cm) of the rooms on the route, except where
    route_draw found no free walk inside a room and kept the straight line."""
    building_dir = DATA / "dev" / building
    bm = api.RecordingMap.load(building_dir)
    kept_straight: set[tuple] = set()
    real_detour = route_draw.detour

    def recording_detour(bm, space_id, start, end, index):
        found = real_detour(bm, space_id, start, end, index)
        if found is None:
            kept_straight.add((tuple(start), tuple(end)))
        return found

    monkeypatch.setattr(route_draw, "detour", recording_detour)
    shapes = [
        (a["floor_id"], a["space_id"], asset_shape(a, a["position"][0], a["position"][1]).buffer(TOUCH_MARGIN_M))
        for a in bm.assets.values()
        if a.get("position")
    ]
    for start, end, step_free, via in route_requests(building_dir):
        stops = [bm.resolve_space(stop) for stop in [start, *via, end]]
        legs = api.route_legs(bm, stops, step_free, [])
        if legs is None:
            continue
        rooms = set(stops) | {room for leg in legs for _, _, room in leg}
        for segment in api.route_geometry(bm, stops, legs)["segments"]:
            if segment["kind"] != "walk":
                continue
            for first, second in itertools.pairwise(map(tuple, segment["points"])):
                line = LineString([first, second])
                touched = [
                    room
                    for floor_id, room, shape in shapes
                    if floor_id == segment["floor_id"] and room in rooms and shape.intersects(line)
                ]
                assert not touched or (first, second) in kept_straight, (building, start, end, first, second)


def test_building_dirs_exist():
    assert Path(LARGEST).exists() and Path(FACTORY).exists()
