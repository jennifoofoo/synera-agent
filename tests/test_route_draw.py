"""The drawn route line keeps its ends off furniture and stops at the door of big halls. Drawing only: the route
itself (length, rooms, steps) stays exactly what the people model says."""

import itertools
import json
import math
import time
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import LineString, Point

from building_agent import routing
from building_agent.edit_ops import asset_shape
from starter_agent.building_map import outline
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
    assert Path(LARGEST).exists() and Path(FACTORY).exists() and Path(CAMPUS).exists()


# ---------- the line threads every door along its wall normal ----------

CAMPUS = DATA / "dev" / "proc-campus-dev-013"  # Jennifer's 3D screenshot: Kitchen 1.09 -> Toilet 1.20
MAX_DOOR_ANGLE_DEG = 15.0
MIN_THREADED_SHARE = 0.9  # door sides in a wall that are threaded (a door with an asset in front keeps the turn)


def nearest_wall_direction(polygon, point) -> np.ndarray:
    """Unit direction of the room outline edge nearest `point` (independent of route_draw's normal)."""
    coords = np.asarray(polygon.exterior.coords)[:, :2]
    edges = [LineString([a, b]) for a, b in itertools.pairwise(coords) if math.dist(a, b) > 1e-9]
    edge = min(edges, key=lambda line: line.distance(Point(point)))
    (ax, ay), (bx, by) = edge.coords
    return np.array([bx - ax, by - ay]) / edge.length


def door_side_ok(bm, opening: dict, door, neighbour) -> bool | None:
    """The drawn segment door -> neighbour is within MAX_DOOR_ANGLE_DEG of the normal of the wall the door sits in
    (of the room on that side) and touches neither room's wall beside the doorway (outline minus the door gap).
    None if the door is not in a wall of that room (a synthetic hand-over inside a stairwell or lift)."""
    segment = LineString([door, neighbour])
    heading = np.subtract(neighbour, door) / segment.length
    gap = Point(door).buffer(opening["width_m"] / 2)
    rooms = [outline(bm.spaces[space_id]["polygon"]) for space_id in opening["space_ids"]]
    side = min(rooms, key=lambda polygon: polygon.distance(Point(neighbour)))
    if side.exterior.distance(Point(door)) > route_draw.SHARED_WALL_M:
        return None
    if abs(float(np.dot(heading, nearest_wall_direction(side, door)))) > math.sin(math.radians(MAX_DOOR_ANGLE_DEG)):
        return False
    return not any(segment.intersects(polygon.exterior.difference(gap)) for polygon in rooms)


def door_sides(bm, stops: list[str], legs: list) -> list[tuple]:
    """(opening, door point, neighbour point) for both sides of every narrow door crossed between rooms, from the
    drawn line (doors at the very start or end of the line have one side)."""
    geometry = api.route_geometry(bm, stops, legs)
    crossed = {
        node[1]
        for leg in legs
        for node in leg
        if node[0] == "o" and all(s in bm.spaces for s in bm.openings[node[1]]["space_ids"])
    }
    sides = []
    for segment in geometry["segments"]:
        points = [tuple(point) for point in segment["points"]]
        for opening_id in crossed:
            opening = bm.openings[opening_id]
            if opening["floor_id"] != segment["floor_id"] or opening["width_m"] >= route_draw.WIDE_OPENING_M:
                continue
            door = tuple(api.rounded(opening["position"]))
            for at in [i for i, point in enumerate(points) if point == door]:
                sides += [(opening, door, points[i]) for i in (at - 1, at + 1) if 0 <= i < len(points)]
    return sides


@pytest.mark.parametrize("building", DEV_BUILDINGS)
def test_drawn_line_crosses_doors_along_the_wall_normal(building):
    """Every door side that got an approach point is crossed within 15 degrees of the wall normal without touching
    the walls beside the doorway, and at least MIN_THREADED_SHARE of all narrow door sides are threaded."""
    building_dir = DATA / "dev" / building
    bm = api.RecordingMap.load(building_dir)
    good = total = 0
    for start, end, step_free, via in route_requests(building_dir):
        stops = [bm.resolve_space(stop) for stop in [start, *via, end]]
        legs = api.route_legs(bm, stops, step_free, [])
        if legs is None:
            continue
        for opening, door, neighbour in door_sides(bm, stops, legs):
            ok = door_side_ok(bm, opening, door, neighbour)
            if ok is None:
                continue  # the door is not in a wall of this room
            approaches = {
                tuple(api.rounded(route_draw.door_approach(bm, opening["id"], space_id)))
                for space_id in opening["space_ids"]
                if route_draw.door_approach(bm, opening["id"], space_id) is not None
            }
            assert ok or neighbour not in approaches, (building, opening["id"], door, neighbour)
            if opening.get("synthetic") and not ok:
                continue  # a synthetic hand-over at a stair landing's corner: no door, no jambs, keeps its turn
            good, total = good + ok, total + 1
    assert not total or good / total >= MIN_THREADED_SHARE, (building, good, total)


def test_kitchen_to_toilet_threads_both_doors():
    """Jennifer's screenshot: the line used to turn on the door centres and cut diagonally across the corridor,
    through the jambs. Now each door is met head-on, 0.5 m out on both sides; route and length unchanged."""
    session = session_for(str(CAMPUS))
    bm = session.map
    start, end = space_by_name(bm, "Kitchen 1.09"), space_by_name(bm, "Toilet 1.20")
    page = api.route_view(session, start, end)
    agent = routing.route(bm, start, end)
    assert (page["length_m"], page["space_path"]) == (agent.length_m, agent.space_path)
    points = [tuple(point) for segment in page["segments"] for point in segment["points"]]
    legs = api.route_legs(bm, [start, end], False, [])
    doors = [bm.openings[node[1]] for node in legs[0][::2] if node[0] == "o"]
    assert len(doors) == 2
    for opening in doors:
        door = tuple(api.rounded(opening["position"]))
        at = points.index(door)
        for neighbour in (points[at - 1], points[at + 1]):
            assert door_side_ok(bm, opening, door, neighbour), (door, neighbour)
            assert math.dist(door, neighbour) == pytest.approx(0.5, abs=0.02)
