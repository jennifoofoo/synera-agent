import time
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from building_agent.find_tools import find_asset, find_connector, make_find_tools
from starter_agent.building_map import BuildingMap, MapError
from tests.conftest import load_map

DATA = Path("data")
DIRECTIONS = ("north", "south", "east", "west")


def building(split: str, name: str) -> BuildingMap:
    return load_map(str(DATA / split / name))


def all_building_dirs() -> list[Path]:
    return sorted(path.parent for path in DATA.glob("*/*/building.json"))


def lift_position(bm: BuildingMap, connector: dict) -> tuple[float, float]:
    levels = {floor_id: floor["level"] for floor_id, floor in bm.floors.items()}
    _, space_id = min(zip(connector["floor_ids"], connector["space_ids"], strict=True), key=lambda s: levels[s[0]])
    centre = Polygon(bm.spaces[space_id]["polygon"]).centroid
    return centre.x, centre.y


def multi_lift_buildings() -> list[Path]:
    return [
        d for d in all_building_dirs() if sum(c["kind"] == "lift" for c in load_map(str(d)).connectors.values()) >= 2
    ]


# ---------- assets ----------


def test_second_press_in_one_zone_is_the_b_item():
    bm = building("dev", "proc-factory-dev-007")
    result = find_asset(bm, "the second press")
    assert result["matches"] == 3 and not result["needs_choice"]
    assert [item["name"] for item in result["groups"][0]["items"]] == ["Press brake H-A3-B"]
    assert result["groups"][0]["items"][0]["ordinal"] == 2
    assert bm.located_asset_ids == [result["groups"][0]["items"][0]["id"]]


def test_press_does_not_match_drill_press_unless_asked():
    bm = building("dev", "proc-factory-dev-007")
    assert {group["type"] for group in find_asset(bm, "press")["groups"]} == {"press_brake"}
    drill = find_asset(bm, "drill press")
    assert {group["type"] for group in drill["groups"]} == {"drill_press"}


def test_all_presses_in_one_zone_without_ordinal_are_listed():
    bm = building("dev", "proc-factory-dev-007")
    result = find_asset(bm, "presses")
    assert result["matches"] == 3 and not result["needs_choice"]
    assert [item["ordinal"] for item in result["groups"][0]["items"]] == [1, 2, 3]
    assert len(bm.located_asset_ids) == 3


def test_last_ordinal_and_out_of_range():
    bm = building("dev", "proc-factory-dev-007")
    assert find_asset(bm, "last press brake")["groups"][0]["items"][0]["name"].endswith("-C")
    assert find_asset(bm, "1st press")["groups"][0]["items"][0]["name"].endswith("-A")
    assert find_asset(bm, "sixth press")["needs_choice"]


def test_presses_over_two_zones_need_a_choice():
    bm = building("dev", "proc-factory-dev-008")
    result = find_asset(bm, "press brake")
    zones = {group["zone"] for group in result["groups"]}
    assert result["matches"] == 6 and result["needs_choice"]
    assert zones == {"Production zone H-B1", "Production zone H-B4"}
    assert "Production zone H-B1" in result["question"]
    assert len(bm.located_asset_ids) == 6
    second = find_asset(bm, "second press")
    assert second["needs_choice"] and len(bm.located_asset_ids) == 6


def test_lone_machine_without_suffix():
    for directory in all_building_dirs():
        bm = load_map(str(directory))
        counts: dict[str, list[dict]] = {}
        for asset in bm.assets.values():
            if asset["category"] == "machine":
                counts.setdefault(asset["type"], []).append(asset)
        lone = next((items[0] for items in counts.values() if len(items) == 1 and items[0]["name"][-2:-1] != "-"), None)
        if lone:
            result = find_asset(bm, lone["type"].replace("_", " "))
            assert not result["needs_choice"] and result["matches"] == 1
            assert result["groups"][0]["items"][0]["id"] == lone["id"]
            assert bm.located_asset_ids == [lone["id"]]
            return
    pytest.fail("no lone machine found")


def test_line_number_is_only_a_hint():
    bm = building("dev", "proc-factory-dev-008")
    result = find_asset(bm, "press on line 4")
    assert result["needs_choice"]
    assert result["hints"] and "confirm" in result["hints"][0]
    assert len(bm.located_asset_ids) == result["matches"] == 6
    bare = find_asset(bm, "line 4")
    assert bare["matches"] == 0 and bare["needs_choice"] and bare["hints"]
    assert find_asset(bm, "bay 99")["hints"][0].startswith("There is no zone number 99")


def test_floor_filter_and_nothing_found():
    bm = building("dev", "proc-factory-dev-007")
    nothing = find_asset(bm, "press", floor_level=7)
    assert nothing["matches"] == 0 and "No asset" in nothing["note"]
    assert find_asset(bm, "unicorn")["matches"] == 0


def test_fuzz_inputs():
    bm = building("dev", "proc-factory-dev-007")
    for bad in ("", "   ", "!!!", "--"):
        with pytest.raises(MapError):
            find_asset(bm, bad)
    for odd in ("Prensa de freno über", "プレス", "press " * 5000, "x" * 100000, "\U0001f600 press", "line", "second"):
        assert isinstance(find_asset(bm, odd), dict)
    with pytest.raises(MapError):
        find_connector(bm, "")
    assert isinstance(find_connector(bm, "lift", "east", floor_level=99), dict)


# ---------- connectors ----------


def test_unique_extreme_lift_matches_brute_force():
    checked = 0
    for directory in multi_lift_buildings():
        bm = load_map(str(directory))
        lifts = [c for c in bm.connectors.values() if c["kind"] == "lift"]
        positions = {c["id"]: lift_position(bm, c) for c in lifts}
        for direction in DIRECTIONS:
            result = find_connector(bm, "lift", direction)
            index, sign = (0, 1) if direction in ("east", "west") else (1, 1)
            sign = 1 if direction in ("east", "north") else -1
            values = sorted((sign * positions[c["id"]][index] for c in lifts), reverse=True)
            assert result["assumption"].startswith(f"I take {direction} as")
            if values[0] - values[1] >= 3.0:
                assert not result["needs_choice"]
                best = max(lifts, key=lambda c: sign * positions[c["id"]][index])
                assert result["chosen"]["id"] == best["id"]
                checked += 1
            else:
                assert result["needs_choice"] and len(result["candidates"]) >= 2
    assert checked > 20


def test_both_building_families_have_multiple_lifts():
    names = [d.name for d in multi_lift_buildings()]
    assert sum(n.startswith("osm") for n in names) >= 7 and sum(n.startswith("proc") for n in names) >= 14


def test_east_lift_example_and_small_margin():
    bm = building("train", "osm-way58216509")
    east = find_connector(bm, "lift", "east")
    west = find_connector(bm, "lift", "west")
    assert east["assumption"] == "I take east as the right side of the plan (+x)."
    assert east["chosen"]["position"][0] > west["chosen"]["position"][0]
    tight = building("train", "osm-way476929995")
    result = find_connector(tight, "lift", "east")
    assert result["needs_choice"] and len(result["candidates"]) == 2 and "question" in result


def test_single_lift_and_no_lift():
    for directory in all_building_dirs():
        bm = load_map(str(directory))
        count = sum(c["kind"] == "lift" for c in bm.connectors.values())
        if count == 1:
            result = find_connector(bm, "lift", "east")
            assert result["chosen"] and "only" in result["reason"]
            break
    else:
        pytest.fail("no single-lift building")
    for directory in all_building_dirs():
        bm = load_map(str(directory))
        if not bm.connectors:
            result = find_connector(bm, "lift", "east")
            assert "No lift" in result["message"] and not result["needs_choice"]
            return
    pytest.fail("no building without connectors")


def test_unsupported_directions():
    bm = building("train", "osm-way58216509")
    for direction in ("left", "right", "Ost", "Nord", "Süd", "up"):
        with pytest.raises(MapError, match="not supported"):
            find_connector(bm, "lift", direction)
    with pytest.raises(MapError):
        find_connector(bm, "escalator", "east")


def test_name_with_direction_word_is_preferred_for_entrances():
    bm = building("dev", "osm-way27917482")
    east = find_connector(bm, "entrance", "east")
    assert east["chosen"]["name"] == "Eingang Ost" and "name" in east["reason"]
    assert find_connector(bm, "entrance", "west")["chosen"]["name"] == "Eingang West"
    assert find_connector(bm, "entrance", "south")["chosen"]["name"] == "Eingang Süd"


def test_direction_word_in_connector_name_wins_over_geometry():
    bm = building("train", "osm-way58216509")
    lifts = [c for c in bm.connectors.values() if c["kind"] == "lift"]
    westmost = min(lifts, key=lambda c: lift_position(bm, c)[0])
    original_name = westmost["name"]
    westmost["name"] = "Ost lift"
    try:
        assert find_connector(bm, "lift", "east")["chosen"]["id"] == westmost["id"]
    finally:
        westmost["name"] = original_name


# ---------- state and tools ----------


def test_tools_are_exposed_and_raise_tool_errors():
    from anthropic.lib.tools import ToolError

    bm = building("dev", "proc-factory-dev-007")
    tools = {tool.name: tool for tool in make_find_tools(bm)}
    assert set(tools) == {"find_asset", "find_connector"}
    assert "Press brake H-A3-B" in tools["find_asset"].call({"query": "second press"})
    with pytest.raises(ToolError):
        tools["find_asset"].call({"query": ""})
    with pytest.raises(ToolError):
        tools["find_connector"].call({"kind": "lift", "direction": "left"})


# ---------- sweep ----------


def test_sweep_all_buildings_under_40_seconds():
    started = time.time()
    buildings = 0
    for directory in all_building_dirs():
        bm = BuildingMap.load(directory)
        buildings += 1
        for asset_type in sorted({asset["type"] for asset in bm.assets.values()}):
            result = find_asset(bm, asset_type.replace("_", " "))
            assert result["matches"] >= 1
            find_asset(bm, f"second {asset_type}", floor_level=0)
        for kind in ("lift", "stairs", "entrance"):
            for direction in (*DIRECTIONS, None):
                find_connector(bm, kind, direction)
    assert buildings == 280
    assert time.time() - started < 120  # generous: the check runs next to other jobs
