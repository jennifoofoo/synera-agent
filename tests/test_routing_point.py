"""Routes from the exact position inside a room (routing.route start_point / destination_point), offline.

Unit cases run on a small synthetic building (an L-shaped room, rotated copies, a closed door, a step); the sweep
runs on every train/dev/test building; the web and tool wiring has its own tests at the bottom."""

import copy
import csv
import math
import random
from pathlib import Path

import networkx as nx
import pytest
from shapely.geometry import Point

from building_agent import routing
from building_agent.guide_tools import GuideState
from building_agent.position import make_position
from building_agent.tools import make_tools
from starter_agent.building_map import DOOR_PREFIX, OUTSIDE, BuildingMap, MapError, outline, walking_lengths
from tests.conftest import load_map
from tests.test_web import multi_floor_building_with_lift
from web import api
from web.server import App

DATA = Path("data")
BUILDINGS = sorted(str(path.parent) for path in DATA.glob("*/*/building.json"))
L_ROOM = [[0, 0], [10, 0], [10, 4], [4, 4], [4, 10], [0, 10]]


def synthetic(angle_deg: float = 0.0, step_free_door: bool = True) -> BuildingMap:
    """A: L-shaped room, B: rectangle east of A (door at (10, 2)), C: rectangle north of B (door at (13, 4))."""
    turn = math.radians(angle_deg)

    def rotate(x, y):
        return [x * math.cos(turn) - y * math.sin(turn), x * math.sin(turn) + y * math.cos(turn)]

    def space(space_id, polygon):
        return {
            "id": space_id,
            "floor_id": "F0",
            "type": "room",
            "room_type": "generic_room",
            "name": space_id,
            "ref": space_id,
            "polygon": [rotate(*corner) for corner in polygon],
        }

    def door(opening_id, position, ids, step_free=True):
        return {
            "id": opening_id,
            "floor_id": "F0",
            "space_ids": ids,
            "kind": "door",
            "position": rotate(*position),
            "width_m": 0.9,
            "step_free": step_free,
        }

    return BuildingMap(
        {
            "building": {"id": "synthetic"},
            "floors": [{"id": "F0", "level": 0, "name": "Ground", "elevation_m": 0.0, "height_m": 3.0}],
            "spaces": [
                space("A", L_ROOM),
                space("B", [[10, 0], [16, 0], [16, 4], [10, 4]]),
                space("C", [[10, 4], [16, 4], [16, 10], [10, 10]]),
            ],
            "openings": [door("AB", (10, 2), ["A", "B"]), door("BC", (13, 4), ["B", "C"], step_free_door)],
            "vertical_connectors": [],
            "assets": [],
        }
    )


def rotate_point(x: float, y: float, angle_deg: float) -> tuple[float, float]:
    turn = math.radians(angle_deg)
    return x * math.cos(turn) - y * math.sin(turn), x * math.sin(turn) + y * math.cos(turn)


def rest_of_route(bm: BuildingMap, door_id: str, destination: str) -> float:
    """Anchor-model length from a door to the destination's anchor (the part a start point does not change)."""
    return nx.dijkstra_path_length(routing.routing_graph(bm, False).graph, DOOR_PREFIX + door_id, destination)


def anchor_walk(bm: BuildingMap, space_id: str, point) -> float:
    return walking_lengths(outline(bm.spaces[space_id]["polygon"]), [point, bm.anchor(space_id)])[(0, 1)]


# ---------- unit cases ----------


def test_point_in_the_middle_of_a_room():
    bm = synthetic()
    # A, from the middle of the long arm: straight east to the door landing (30 cm inside), plus the 30 cm to the door
    result = routing.route(bm, "A", "B", start_point=(2.0, 2.0))
    points = list(bm.last_route_points)
    expected = math.dist((2.0, 2.0), (9.7, 2.0)) + 0.3 + rest_of_route(bm, "AB", "B")
    assert result.length_m == pytest.approx(expected, abs=0.02)
    assert points[0] == ("F0", (2.0, 2.0))
    assert result.steps[0] == "Start in A [A] on Ground."
    assert result.steps[1].startswith("Walk about 8 m through the door into B")
    assert result.space_path == routing.route(bm, "A", "B").space_path == ["A", "B"]


def test_point_near_a_wall_steps_in_to_the_walkable_area():
    bm = synthetic()
    near_wall = (0.02, 2.0)  # 2 cm from the wall, inside the 15 cm clearance
    result = routing.route(bm, "A", "B", start_point=near_wall)
    inside = routing.route(bm, "A", "B", start_point=(0.15, 2.0))
    assert result.length_m == pytest.approx(inside.length_m + 0.13, abs=0.02)
    assert math.isfinite(result.length_m)


def test_point_in_the_non_convex_room_walks_round_the_corner():
    bm = synthetic()
    point = (1.0, 9.0)  # top of the L's vertical arm
    result = routing.route(bm, "A", "B", start_point=point)
    corner = (3.894, 3.894)  # the walkable area rounds the reflex corner (4, 4) with a 15 cm arc
    room_part = math.dist(point, corner) + math.dist(corner, (9.7, 2.0)) + 0.3
    assert result.length_m == pytest.approx(room_part + rest_of_route(bm, "AB", "B"), abs=0.05)
    assert result.length_m > math.dist(point, (10, 2)) + rest_of_route(bm, "AB", "B")  # not the straight line


@pytest.mark.parametrize("angle", [0, 33, 90, 180, 257])
def test_rotated_building_gives_the_same_lengths(angle):
    plain, turned = synthetic(), synthetic(angle)
    for point in [(1.0, 9.0), (2.0, 2.0), (0.05, 0.05)]:
        expected = routing.route(plain, "A", "C", start_point=point, destination_point=(15.0, 9.0))
        got = routing.route(
            turned, "A", "C", start_point=rotate_point(*point, angle), destination_point=rotate_point(15.0, 9.0, angle)
        )
        assert got.length_m == pytest.approx(expected.length_m, abs=0.02)
        assert got.space_path == expected.space_path == ["A", "B", "C"]


def test_point_outside_the_room_is_moved_in_or_rejected_with_a_message():
    bm = synthetic()
    near = routing.route(bm, "A", "B", start_point=(-0.2, 2.0))  # 20 cm outside: moved to the wall
    assert bm.last_route_points[0] == ("F0", (0.0, 2.0))
    assert near.length_m == pytest.approx(routing.route(bm, "A", "B", start_point=(0.0, 2.0)).length_m)
    with pytest.raises(MapError, match=r"outside A"):
        routing.route(bm, "A", "B", start_point=(30.0, 30.0))
    with pytest.raises(MapError, match="finite"):
        routing.route(bm, "A", "B", start_point=(float("nan"), 1.0))
    with pytest.raises(MapError, match="another floor"):
        routing.route(bm, "A", "B", start_point=(1.0, 1.0), start_floor="F9")
    inside_the_notch = (7.0, 7.0)  # the empty corner of the L: 3 m from the room
    with pytest.raises(MapError, match="outside"):
        routing.route(bm, "A", "B", start_point=inside_the_notch)


def test_same_room_uses_the_direct_visibility_length_between_the_points():
    bm = synthetic()
    first, second = (1.0, 9.0), (9.0, 1.0)  # across the L's corner
    result = routing.route(bm, "A", "A", start_point=first, destination_point=second)
    corner = (3.894, 3.894)  # the 15 cm arc round the reflex corner
    assert result.length_m == pytest.approx(math.dist(first, corner) + math.dist(corner, second), abs=0.05)
    assert result.space_path == ["A"]
    assert bm.last_route_points == [("F0", first), ("F0", second)]
    assert result.steps[-1].startswith("Walk about 12 m. You have arrived at A")
    straight = routing.route(bm, "B", "B", start_point=(11.0, 1.0), destination_point=(15.0, 3.0))
    assert straight.length_m == pytest.approx(math.dist((11.0, 1.0), (15.0, 3.0)), abs=0.01)
    assert routing.route(bm, "A", "A").length_m == 0.0


def test_start_point_and_via_and_destination_point():
    bm = synthetic()
    plain = routing.route(bm, "A", "C", via=["B"])
    with_points = routing.route(bm, "A", "C", via=["B"], start_point=(1.0, 9.0), destination_point=(15.0, 9.0))
    assert with_points.space_path == plain.space_path
    assert bm.last_route_points[0] == ("F0", (1.0, 9.0)) and bm.last_route_points[-1] == ("F0", (15.0, 9.0))


def test_step_free_and_closed_doors_still_apply():
    bm = synthetic(step_free_door=False)
    assert routing.route(bm, "A", "C", start_point=(1.0, 9.0)).space_path == ["A", "B", "C"]
    with pytest.raises(MapError, match="step-free"):
        routing.route(bm, "A", "C", step_free=True, start_point=(1.0, 9.0))
    assert bm.last_route is None
    open_bm = synthetic()
    assert routing.route(open_bm, "A", "C", step_free=True, start_point=(1.0, 9.0)).step_free
    open_bm.closed.add("AB")
    with pytest.raises(MapError, match="No route"):
        routing.route(open_bm, "A", "B", start_point=(1.0, 9.0))
    assert open_bm.last_route is None and open_bm.last_route_points == []
    open_bm.closed.clear()
    open_bm.closed.add("B")
    with pytest.raises(MapError, match="No route"):
        routing.route(open_bm, "A", "C", start_point=(1.0, 9.0))


def test_the_cached_graph_is_never_changed():
    bm = synthetic()
    graph = routing.routing_graph(bm, False).graph
    before = sorted(graph.edges(keys=True, data="weight"))
    routing.route(bm, "A", "C", start_point=(1.0, 9.0), destination_point=(15.0, 9.0))
    routing.route(bm, "A", "A", start_point=(1.0, 9.0), destination_point=(9.0, 1.0))
    assert routing.routing_graph(bm, False).graph is graph
    assert sorted(graph.edges(keys=True, data="weight")) == before
    assert routing.route(bm, "A", "C").length_m == routing.route(synthetic(), "A", "C").length_m


def test_a_start_at_the_anchor_gives_the_anchor_route():
    bm = synthetic()
    for room in ("A", "B"):
        anchor = bm.anchor(room)
        assert routing.route(bm, room, "C", start_point=anchor).length_m == pytest.approx(
            routing.route(bm, room, "C").length_m, abs=0.01
        )


def test_example_corner_against_the_anchor():
    """Documented example: a corner of the L room against its anchor start."""
    bm = synthetic()
    corner = routing.route(bm, "A", "C", start_point=(0.2, 9.8)).length_m
    anchor = routing.route(bm, "A", "C").length_m
    assert corner > anchor  # the anchor of the L sits on the long arm, the far corner is further from the door


# ---------- no point: nothing changes ----------


def test_without_points_results_are_identical_to_the_kit_model():
    """300 random pairs in 20 buildings: length, space path, text and drawn points equal the kit's."""
    with (DATA / "manifest.csv").open(encoding="utf-8", newline="") as handle:
        paths = sorted(row["path"] for row in csv.DictReader(handle))
    rng = random.Random(11)
    compared = 0
    for relative in rng.sample(paths, 20):
        bm = load_map(str(DATA / relative))
        ids = sorted(bm.spaces)
        for _ in range(15):
            start, end = rng.sample(ids, 2)
            step_free = rng.random() < 0.3
            try:
                kit = bm.route(start, end, step_free)
            except MapError:
                with pytest.raises(MapError):
                    routing.route(bm, start, end, step_free, None, None, None, None)
                continue
            kit_points = list(bm.last_route_points)
            ours = routing.route(bm, start, end, step_free, None, None, None, None)
            assert (ours.length_m, ours.space_path, ours.steps) == (kit.length_m, kit.space_path, kit.steps)
            assert bm.last_route_points == kit_points
            compared += 1
    assert compared >= 150


# ---------- sweep over every building ----------


def random_point(bm: BuildingMap, space_id: str, rng: random.Random) -> tuple[float, float] | None:
    polygon = outline(bm.spaces[space_id]["polygon"])
    low_x, low_y, high_x, high_y = polygon.bounds
    for _ in range(200):
        candidate = (rng.uniform(low_x, high_x), rng.uniform(low_y, high_y))
        if polygon.contains(Point(candidate)):
            return candidate
    return None


@pytest.mark.parametrize("building_dir", BUILDINGS, ids=[Path(path).name for path in BUILDINGS])
def test_random_inside_points_never_crash_and_stay_within_bounds(building_dir):
    bm = load_map(building_dir)
    rooms = sorted(space_id for space_id in bm.spaces if space_id != OUTSIDE)
    rng = random.Random(len(rooms))
    kept = bm.last_route
    try:
        for _ in range(3):
            start, end = rng.sample(rooms, 2) if len(rooms) > 1 else (rooms[0], rooms[0])
            first, last = random_point(bm, start, rng), random_point(bm, end, rng)
            if first is None or last is None:
                continue
            try:
                anchors = routing.route(bm, start, end)
            except MapError:
                with pytest.raises(MapError):
                    routing.route(bm, start, end, start_point=first, destination_point=last)
                continue
            result = routing.route(bm, start, end, start_point=first, destination_point=last)
            assert math.isfinite(result.length_m) and result.space_path[0] == start and result.space_path[-1] == end
            assert bm.last_route_points[0][1] == first and bm.last_route_points[-1][1] == last
            if bm.spaces[start]["floor_id"] == bm.spaces[end]["floor_id"]:
                assert result.length_m >= math.dist(first, last) - 0.01
            slack = 0.5  # wall clearance on both ends and the rounding of the edge weights
            bound = anchors.length_m + anchor_walk(bm, start, first) + anchor_walk(bm, end, last) + slack
            assert result.length_m <= bound, (start, end, result.length_m, bound)
            from_only = routing.route(bm, start, end, start_point=first)
            assert from_only.length_m <= anchors.length_m + anchor_walk(bm, start, first) + slack
    finally:
        bm.last_route = kept


# ---------- web ----------


@pytest.fixture
def app() -> App:
    return App(DATA)


def a_room_with_a_corner_point(bm: BuildingMap) -> tuple[str, str, tuple[float, float]]:
    """(start room, other room on the same floor reachable from it, a point inside the start room)."""
    rooms = sorted(space_id for space_id, space in bm.spaces.items() if space["type"] == "room")
    for start in rooms:
        point = random_point(bm, start, random.Random(5))
        for end in rooms:
            if end != start and bm.spaces[end]["floor_id"] == bm.spaces[start]["floor_id"] and point:
                try:
                    routing.route(bm, start, end)
                except MapError:
                    continue
                return start, end, point
    pytest.skip("no usable pair")


def test_web_route_starts_at_the_exact_point_and_keeps_it_in_the_state(app):
    key = multi_floor_building_with_lift()
    bm = app.session(key).map
    start, end, point = a_room_with_a_corner_point(bm)
    floor_id = bm.spaces[start]["floor_id"]
    _, plain = app.post("/api/route", {"building": key, "start": start, "destination": end})
    _, payload = app.post(
        "/api/route",
        {
            "building": key,
            "start": start,
            "destination": end,
            "start_point": {"x": point[0], "y": point[1], "floor_id": floor_id},
        },
    )
    route = payload["route"]
    assert route["ok"] and "notes" not in route
    assert route["segments"][0]["points"][0] == [round(point[0], 2), round(point[1], 2)]
    assert plain["route"]["segments"][0]["points"][0] == [round(bm.anchor(start)[0], 2), round(bm.anchor(start)[1], 2)]
    assert route["space_path"] == plain["route"]["space_path"]
    assert payload["state"]["route"]["segments"][0]["points"][0] == route["segments"][0]["points"][0]
    # the destination point ends the line
    _, both = app.post(
        "/api/route",
        {"building": key, "start": start, "destination": end, "destination_point": {"x": point[0], "y": point[1]}},
    )
    assert both["route"]["notes"]  # a point of another room is ignored


def test_web_route_ignores_bad_points_with_a_note(app):
    key = multi_floor_building_with_lift()
    bm = app.session(key).map
    start, end, point = a_room_with_a_corner_point(bm)
    plain = app.post("/api/route", {"building": key, "start": start, "destination": end})[1]["route"]
    for bad in (
        {"x": 1e9, "y": 0},
        {"x": "a", "y": 1},
        {"x": float("nan"), "y": 1},
        {"x": point[0], "y": point[1], "floor_id": "no-such-floor"},
        [1, 2],
    ):
        route = app.post("/api/route", {"building": key, "start": start, "destination": end, "start_point": bad})[1][
            "route"
        ]
        assert route["ok"] and route["notes"] and "ignored" in route["notes"][0]
        assert route["length_m"] == plain["length_m"] and route["segments"] == plain["segments"]


# ---------- agent tools: the position decides ----------


def test_routes_without_a_start_use_the_exact_position_point(tmp_path):
    key = multi_floor_building_with_lift()
    bm = BuildingMap.load(DATA / key)
    start, end, point = a_room_with_a_corner_point(bm)
    guide = GuideState()
    tools = {tool.name: tool for tool in make_tools(bm, tmp_path, guide)}
    assert "start_point" not in tools["find_route"].to_dict()["input_schema"]["properties"]
    guide.position = make_position(bm, start, None, "said", 0)
    plain = tools["find_route"](destination=end)
    assert "exact position" not in plain
    guide.position = make_position(bm, start, point, "click", 0)
    routed = tools["find_route"](destination=end)
    assert routed.count("from your exact position") == 1
    expected = routing.route(copy.copy(bm), start, end, start_point=point).length_m
    assert f'"length_m": {expected}' in routed
    assert bm.last_route_points[0][1] == point
    directed = tools["give_directions"](destination=end)
    assert directed.count("from your exact position") == 1 and f'"length_m": {expected}' in directed
    explicit = tools["find_route"](start=start, destination=end)  # a named start is the room's anchor
    assert "exact position" not in explicit and f'"length_m": {routing.route(bm, start, end).length_m}' in explicit


def test_benchmark_messages_never_use_a_point(tmp_path):
    key = multi_floor_building_with_lift()
    bm = BuildingMap.load(DATA / key)
    start, end, point = a_room_with_a_corner_point(bm)
    guide = GuideState()
    guide.position = make_position(bm, start, point, "click", 0)
    guide.last_user_text = "How long is the route? Answer: <number>"
    tools = {tool.name: tool for tool in make_tools(bm, tmp_path, guide)}
    result = tools["find_route"](destination=end)
    assert "exact position" not in result and f'"length_m": {routing.route(bm, start, end).length_m}' in result


def test_a_position_point_outside_its_room_falls_back_to_the_anchor(tmp_path):
    key = multi_floor_building_with_lift()
    bm = BuildingMap.load(DATA / key)
    start, end, _ = a_room_with_a_corner_point(bm)
    guide = GuideState()
    guide.position = make_position(bm, start, (1e6, 1e6), "device", 0)
    tools = {tool.name: tool for tool in make_tools(bm, tmp_path, guide)}
    result = tools["find_route"](destination=end)
    assert "exact position" not in result and f'"length_m": {routing.route(bm, start, end).length_m}' in result


def test_recording_map_remembers_points_for_the_page(tmp_path):
    key = multi_floor_building_with_lift()
    session = api.Session(key, DATA / key, api.RecordingMap.load(DATA / key))
    bm = session.map
    start, end, point = a_room_with_a_corner_point(bm)
    previous = bm.last_route
    routing.route(bm, start, end, start_point=point)
    assert session.adopt_agent_route(previous, session.route_version)
    assert session.route_request["start_point"] == list(point)
    drawn = api.current_route(session)
    assert drawn["segments"][0]["points"][0] == [round(point[0], 2), round(point[1], 2)]
