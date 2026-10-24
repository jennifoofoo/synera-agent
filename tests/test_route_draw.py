"""The drawn route line keeps its ends off furniture and stops at the door of big halls. Drawing only: the route
itself (length, rooms, steps) stays exactly what the people model says."""

import time
from pathlib import Path

import pytest
from shapely.geometry import Point

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
    session = session_for(str(LARGEST))
    bm = session.map
    rooms = [s for s in bm.spaces if bm.spaces[s]["type"] == "room"]
    start, end = rooms[0], rooms[-1]
    page = api.route_view(session, start, end)  # cold: builds the asset index
    assert page["ok"]
    began = time.perf_counter()
    api.route_view(session, rooms[1], rooms[-2])
    assert time.perf_counter() - began < 1.0
    began = time.perf_counter()
    route_draw.draw_index(bm)
    assert time.perf_counter() - began < 0.05, "asset signature check must stay cheap"


def test_building_dirs_exist():
    assert Path(LARGEST).exists() and Path(FACTORY).exists()
