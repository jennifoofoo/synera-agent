"""query_tools answers the plan questions no wired tool can (checked against the labelled dev kinds)."""

from pathlib import Path

import pytest

from building_agent.kinds.floor_area_total import KIND as AREA
from building_agent.kinds.largest_room import KIND as LARGEST
from building_agent.query_tools import doors_by_width, floor_totals, make_query_tools, room_dimensions, rooms_table
from starter_agent.building_map import MapError
from tests.conftest import load_map

DEV = Path("data/dev/proc-factory-dev-003")
pytestmark = pytest.mark.skipif(not DEV.exists(), reason="dev data not fetched")


def test_rooms_table_agrees_with_the_kinds():
    bm = load_map(str(DEV))
    floor = next(f for f in bm.floors.values() if f["level"] == 1)
    table = rooms_table(bm, 1, "office")
    total = AREA.fn(bm, floor_id=floor["id"], room_type="office")
    assert table["total"] == total["count"]
    assert table["total_area_m2"] == pytest.approx(total["total_m2"], abs=0.02)
    biggest = LARGEST.fn(bm, floor_id=floor["id"], room_type="office")
    assert table["rooms"][0]["space_id"] == biggest["space_id"]
    ascending = rooms_table(bm, 1, "office", order="area_asc")["rooms"]
    assert ascending[0]["area_m2"] <= ascending[1]["area_m2"]
    assert rooms_table(bm, 1, "office", limit=3)["total"] == table["total"]


def test_floor_totals_cover_every_type():
    bm = load_map(str(DEV))
    totals = floor_totals(bm, 1)
    assert totals["total_area_m2"] == pytest.approx(sum(v["area_m2"] for v in totals["by_type"].values()), abs=0.05)
    assert totals["rooms_area_m2"] < totals["total_area_m2"]


def test_doors_by_width_splits_the_openings():
    bm = load_map(str(DEV))
    everything = doors_by_width(bm)
    narrow = doors_by_width(bm, narrower_than=1.0)
    wide = doors_by_width(bm, wider_than=1.0)
    assert 0 < narrow["count"] < everything["count"]
    assert narrow["count"] + wide["count"] <= everything["count"]  # a width of exactly 1.0 is in neither
    assert doors_by_width(bm, include_entrances=True)["count"] > everything["count"]


def test_room_dimensions_and_errors():
    bm = load_map(str(DEV))
    size = room_dimensions(bm, "Office 1.04")
    assert size["box_width_m"] * size["box_depth_m"] >= size["area_m2"] - 0.01
    with pytest.raises(MapError):
        rooms_table(bm, 42)
    with pytest.raises(MapError):
        room_dimensions(bm, "Ballroom 9.99")


def test_tools_return_json_and_report_errors():
    bm = load_map(str(DEV))
    tools = {tool.name: tool for tool in make_query_tools(bm)}
    assert set(tools) == {"list_rooms", "floor_summary", "list_doors", "room_size"}
    assert '"total"' in tools["list_rooms"].func(floor_level=0, room_type="office")
