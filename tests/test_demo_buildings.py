"""Geometry rules for the demo buildings in demo/buildings/ (made from photographed plans, then fixed by hand).

The Urban Colab once had corridors overlapping the rooms beside them, doors far from any shared wall and two exits
instead of eight, so routes zig-zagged through storerooms. These checks keep a hand edit from bringing that back.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

DEMO = Path(__file__).resolve().parent.parent / "demo" / "buildings"
BUILDINGS = sorted(DEMO.glob("*/building.json"))

OVERLAP_M2 = 0.5  # two spaces may share a wall, not floor
DOOR_TO_WALL_M = 0.3  # a door lies on the wall its two spaces share
ASSET_SLACK_M = 0.1


def load(path: Path) -> tuple[dict, dict[str, Polygon]]:
    building = json.loads(path.read_text())
    return building, {s["id"]: Polygon(s["polygon"]) for s in building["spaces"]}


@pytest.mark.parametrize("path", BUILDINGS, ids=lambda p: p.parent.name)
def test_spaces_are_simple_and_do_not_overlap(path: Path) -> None:
    building, shapes = load(path)
    for space_id, shape in shapes.items():
        assert shape.is_valid, f"{space_id}: self-intersecting polygon"
        assert shape.area > 1.0, f"{space_id}: no floor area"
    by_floor: dict[str, list[str]] = {}
    for space in building["spaces"]:
        by_floor.setdefault(space["floor_id"], []).append(space["id"])
    for ids in by_floor.values():
        for a, b in combinations(ids, 2):
            shared = shapes[a].intersection(shapes[b]).area
            assert shared <= OVERLAP_M2, f"{a} and {b} overlap by {shared:.1f} m2"


@pytest.mark.parametrize("path", BUILDINGS, ids=lambda p: p.parent.name)
def test_doors_sit_on_shared_walls_and_exits_on_outer_walls(path: Path) -> None:
    building, shapes = load(path)
    floor_of = {s["id"]: s["floor_id"] for s in building["spaces"]}
    for opening in building["openings"]:
        point = Point(opening["position"])
        a, b = opening["space_ids"]
        assert a in shapes, f"{opening['id']}: unknown space {a}"
        if b == "outside":
            others = unary_union([s for k, s in shapes.items() if k != a and floor_of[k] == floor_of[a]])
            assert shapes[a].boundary.distance(point) <= DOOR_TO_WALL_M, f"{opening['id']}: exit not on the wall of {a}"
            assert others.distance(point) > 0.05, f"{opening['id']}: exit {a} -> outside opens into another space"
        else:
            wall = shapes[a].boundary.intersection(shapes[b].buffer(0.25))
            assert not wall.is_empty, f"{opening['id']}: {a} and {b} share no wall"
            assert wall.distance(point) <= DOOR_TO_WALL_M, f"{opening['id']}: {wall.distance(point):.2f} m off the wall"


@pytest.mark.parametrize("path", BUILDINGS, ids=lambda p: p.parent.name)
def test_devices_lie_in_their_space(path: Path) -> None:
    building, shapes = load(path)
    for asset in building["assets"]:
        shape = shapes[asset["space_id"]]
        assert shape.buffer(ASSET_SLACK_M).contains(Point(asset["position"])), (
            f"{asset['id']} is not in {asset['space_id']}"
        )


def test_urban_colab_has_the_exits_of_its_evacuation_plan() -> None:
    building, _ = load(DEMO / "plan-89323a15" / "building.json")
    exits = [o for o in building["openings"] if o["kind"] == "entrance"]
    assert len(exits) >= 8, "the ground-floor evacuation plan shows 8 exits"
    assert exits[0]["space_ids"][0].endswith("F0-S009"), "the demo starts at the first exit's room (demo_seed.py)"
