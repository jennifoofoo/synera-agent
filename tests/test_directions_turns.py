import itertools
import math
import re

from building_agent.directions import (
    LANDMARK_RADIUS_M,
    DirectionsSession,
    chunk_steps,
    metres,
    turn_directions,
    turn_plan,
    turn_word,
)
from building_agent.routing import route
from starter_agent.building_map import BuildingMap, MapError
from tests.conftest import DATA, load_map


def square(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def space(sid, floor, name, box):
    return {
        "id": sid,
        "floor_id": floor,
        "type": "room",
        "room_type": "corridor",
        "name": name,
        "ref": None,
        "polygon": square(*box),
        "synthetic": False,
    }


def door(oid, a, b, x, y):
    return {
        "id": oid,
        "floor_id": "F0",
        "space_ids": [a, b],
        "kind": "door",
        "position": [x, y],
        "width_m": 1.0,
        "step_free": True,
        "synthetic": False,
    }


def asset(aid, kind, category, sid, x, y):
    return {
        "id": aid,
        "name": kind,
        "category": category,
        "type": kind,
        "space_id": sid,
        "floor_id": "F0",
        "position": [x, y],
        "source": "dataset",
    }


def synthetic_building() -> BuildingMap:
    """Floor 0: A B E F in a row (y 0..10), C above B, K above A. Floor 1: U1 above K via a lift."""
    floors = [
        {"id": "F0", "name": "Ground floor", "level": 0, "elevation_m": 0.0},
        {"id": "F1", "name": "First floor", "level": 1, "elevation_m": 3.0},
    ]
    spaces = [
        space("A", "F0", "Room A", (0, 0, 10, 10)),
        space("B", "F0", "Corridor 0.01", (10, 0, 20, 10)),
        space("E", "F0", "Room E", (20, 0, 30, 10)),
        space("F", "F0", "Room F", (30, 0, 40, 10)),
        space("C", "F0", "Room C", (10, 10, 20, 20)),
        space("K", "F0", "Room K", (0, 10, 10, 20)),
        space("D", "F0", "Room D", (10, 20, 20, 30)),
        space("U1", "F1", "Upper hall", (0, 10, 10, 20)),
        space("U2", "F1", "Upper room", (10, 10, 20, 20)),
    ]
    openings = [
        door("O-AB", "A", "B", 10, 5),
        door("O-BE", "B", "E", 20, 5),
        door("O-EF", "E", "F", 30, 5),
        door("O-BC", "B", "C", 15, 10),
        door("O-CD", "C", "D", 15, 20),
        door("O-AK", "A", "K", 5, 10),
        door("O-U", "U1", "U2", 10, 15) | {"floor_id": "F1"},
    ]
    assets = [
        asset("coffee", "coffee_machine", "equipment", "B", 17, 8),
        asset("chair", "chair", "furniture", "B", 15, 9),
        asset("far_mill", "cnc_mill", "machine", "C", 19.5, 19.5),
    ]
    lift = {
        "id": "V1",
        "kind": "lift",
        "name": "Lift 1",
        "floor_ids": ["F0", "F1"],
        "space_ids": ["K", "U1"],
        "step_free": True,
        "synthetic": True,
    }
    data = {
        "building": {"name": "Synthetic", "source": "test"},
        "floors": floors,
        "spaces": spaces,
        "assets": assets,
        "vertical_connectors": [lift],
        "openings": openings,
    }
    return BuildingMap(data)


def test_turn_word_thresholds():
    assert turn_word((1, 0), (1, 0.5)) == "straight"
    assert turn_word((1, 0), (1, math.tan(math.radians(29)))) == "straight"
    assert turn_word((1, 0), (0, 1)) == "left"
    assert turn_word((1, 0), (0, -1)) == "right"
    assert turn_word((1, 0), (-1, 0.1)) == "around"
    assert turn_word((1, 0), (-1, -0.1)) == "around"
    assert turn_word((1, 0), (0.1, 0)) is None


WALK_LINE = re.compile(r"^(Leave .+ through the door|Walk (\d+ m|a few metres|on|straight on for (\d+ m|a few metres)))\b")
METRES = re.compile(r"\b\d+ m\b|a few metres")


def test_turn_first_exact_words():
    """Turn-first like a navigation app: action and metres first, the turn at the door, rooms only when they help.

    The first step cannot know where the person faces, so it leaves the room and turns after its door (the walk
    from the room's anchor to the door gives the direction)."""
    bm = synthetic_building()
    steps = turn_directions(bm, route(bm, "A", "D"))
    assert steps[0] == "Leave Room A through the door (5 m), then turn left."
    assert steps[1] == "Walk 7 m, then turn left at the coffee machine."
    assert steps[2] == "Walk 10 m to Room D straight ahead."
    assert steps[3].startswith("You have arrived at Room D")


def test_destination_side_and_landmark_on_first_step():
    bm = synthetic_building()
    steps = turn_directions(bm, route(bm, "C", "A"))
    assert steps[0] == "Leave Room C through the door by the coffee machine (5 m), then turn right."
    assert steps[1] == "Walk 7 m to Room A on your right."


def test_straight_and_merged_run():
    bm = synthetic_building()
    steps = turn_directions(bm, route(bm, "A", "E"))
    assert steps[0] == "Leave Room A through the door (5 m) and go straight on."
    assert steps[1] == "Walk 10 m to Room E straight ahead."
    plan = turn_plan(bm, route(bm, "A", "F"))
    assert plan[1].text == "Walk 20 m to Room F straight ahead."
    assert plan[1].rooms == ["E", "F"]
    assert len(plan) == 3


def test_metres_rounding():
    assert metres(None) is None
    assert metres(2.9) == "a few metres"
    assert metres(3.4) == "3 m"
    assert metres(12.6) == "13 m"
    assert metres(23) == "25 m"
    assert metres(27.4) == "25 m"


def test_room_names_only_when_they_help():
    bm = synthetic_building()
    plan = turn_plan(bm, route(bm, "A", "D"))
    assert "Corridor 0.01" not in " ".join(step.text for step in plan)
    bm.spaces["B"]["room_type"] = "lobby"
    plan = turn_plan(bm, route(bm, "A", "D"))
    assert plan[0].text == "Leave Room A through the door (5 m), then turn left (towards Corridor 0.01)."


def test_landmark_filters_boring_and_far():
    bm = synthetic_building()
    plan = turn_plan(bm, route(bm, "A", "D"))
    assert plan[1].landmark.id == "coffee"
    text = " ".join(step.text for step in plan)
    assert "chair" not in text and "cnc" not in text


def test_lift_and_stairs_keep_their_wording():
    bm = synthetic_building()
    plan = turn_plan(bm, route(bm, "A", "U2"))
    texts = [step.text for step in plan]
    assert any("Take Lift 1 (lift) to First floor." in text for text in texts)
    for step in plan:
        if "Lift" in step.text:
            assert step.turn is None
    after_lift = texts[next(i for i, t in enumerate(texts) if "Lift" in t) + 1]
    assert after_lift == "Walk 5 m to Upper room straight ahead."
    bm.connectors["V1"]["kind"] = "stairs"
    bm.connectors["V1"]["name"] = "Stairs 1"
    texts = turn_directions(bm, route(bm, "A", "U2"))
    assert any(text.startswith("Take Stairs 1 (stairs)") for text in texts)


def test_missing_door_position_falls_back():
    bm = synthetic_building()
    result = route(bm, "A", "C")
    del bm.openings["O-BC"]
    steps = turn_directions(bm, result)
    assert all(steps) and "Turn" not in " ".join(steps)


def test_same_room_route_and_determinism():
    bm = synthetic_building()
    assert len(turn_directions(bm, route(bm, "A", "A"))) == 1
    result = route(bm, "A", "F")
    assert turn_directions(bm, result) == turn_directions(bm, result)


def test_session_uses_turn_steps_in_chunks_of_three():
    bm = synthetic_building()
    session = DirectionsSession.from_route(bm, route(bm, "A", "U2"))
    assert all(len(chunk) <= 3 for chunk in session.chunks)
    assert session.next()[0].startswith("Leave Room A")
    assert chunk_steps(["a", "b", "c", "d"]) == [["a", "b", "c"], ["d"]]


SWEEP = [str(path.parent) for split in ("dev", "train") for path in sorted((DATA / split).glob("*/building.json"))]


def small_buildings(limit: int = 30) -> list[str]:
    picked = []
    for building_dir in SWEEP[:: max(1, len(SWEEP) // 60)]:
        if len(load_map(building_dir).spaces) <= 400:
            picked.append(building_dir)
        if len(picked) >= limit:
            break
    return picked


def sweep_routes(bm: BuildingMap, count: int = 5):
    ids = sorted(bm.spaces)
    picks = ids[:: max(1, len(ids) // 8)]
    found = []
    for start, end in itertools.permutations(picks, 2):
        try:
            found.append(route(bm, start, end))
        except MapError:
            continue
        if len(found) >= count:
            break
    return found


def test_sweep_over_buildings():
    buildings = small_buildings()
    assert len(buildings) >= 20
    checked = turns = 0
    for building_dir in buildings:
        bm = load_map(building_dir)
        for result in sweep_routes(bm):
            plan = turn_plan(bm, result)
            checked += 1
            assert 1 <= len(plan) <= len(result.space_path)
            assert [step.text for step in plan] == turn_directions(bm, result)
            for step in plan:
                assert step.text.strip()
                is_walk = step.rooms and not step.text.startswith(("Take ", "Go through the entrance", "Leave the"))
                if is_walk:  # turn-first: the action leads, metres follow, a turn word only where geometry gives one
                    assert WALK_LINE.match(step.text), step.text
                    assert METRES.search(step.text) or step.text.startswith("Walk on"), step.text
                    if step.turn in ("left", "right"):
                        assert f"turn {step.turn}" in step.text or f"on your {step.turn}" in step.text, step.text
                if not step.rooms:
                    assert step.text.startswith(("You have arrived at", "You are already at")), step.text
                if "Take" in step.text:
                    assert step.turn is None and not re.search(r"Turn|straight", step.text)
                if step.turn in ("left", "right", "around"):
                    turns += 1
                if step.landmark and step.door_position:
                    landmark = step.landmark
                    assert landmark.label not in [bm.spaces[room]["name"] for room in step.rooms]
                    if landmark.kind == "asset":
                        asset_ = bm.assets[landmark.id]
                        assert math.dist(asset_["position"], step.door_position) <= LANDMARK_RADIUS_M
                    else:
                        assert landmark.id in bm.spaces
            session = DirectionsSession.from_route(bm, result)
            assert all(len(chunk) <= 3 for chunk in session.chunks)
    assert checked >= 100
    assert turns > 0
