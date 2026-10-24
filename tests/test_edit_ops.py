"""Offline tests for remove_door, widen_door and move_asset, including the confirmation guard."""

import copy
import json
import random
from functools import cache
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError
from shapely.geometry import Point, Polygon

from building_agent import edit_ops, routing
from building_agent.asset_catalog import ASSET_CATALOG
from building_agent.edit_ops import asset_shape
from building_agent.find_tools import find_asset
from building_agent.guide_tools import GuideState, building_signature, make_guide_tools
from building_agent.impact import analyse
from building_agent.structured import located_entries
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError

BUILDINGS = sorted(Path("data").glob("*/*/building.json"))


def load(path: Path) -> BuildingMap:
    return BuildingMap.load(path)


@cache
def first_dev() -> Path:
    return min(Path("data/dev").glob("*/building.json"))


def fresh() -> BuildingMap:
    return load(first_dev())


def assert_in_sync(bm: BuildingMap) -> None:
    assert [o["id"] for o in bm.data["openings"]] == list(bm.openings)
    assert all(a is b for a, b in zip(bm.data["openings"], bm.openings.values(), strict=True))
    assert len({a["id"] for a in bm.data["assets"]}) == len(bm.data["assets"]) == len(bm.assets)
    assert all(bm.assets[a["id"]] is a for a in bm.data["assets"])


def inner_door(bm: BuildingMap) -> dict:
    return next(o for o in bm.openings.values() if OUTSIDE not in o["space_ids"])


def square(x: float, size: float = 10.0) -> list[list[float]]:
    return [[x, 0.0], [x + size, 0.0], [x + size, size], [x, size]]


def factory() -> BuildingMap:
    """Hall H-A1 with machines A, B, C; empty hall H-A2; hall H-A3 with one lone press; a door and an entrance."""
    spaces = [
        {"id": f"B-F0-S{n}", "floor_id": "B-F0", "type": "room", "room_type": "hall", "name": f"Hall {ref}", "ref": ref}
        | {"polygon": square(10.4 * n)}
        for n, ref in enumerate(["H-A1", "H-A2", "H-A3"])
    ]

    def asset(number: int, name: str, kind: str, space: int, x: float) -> dict:
        return {
            "id": f"B-A{number}",
            "name": name,
            "category": "machine",
            "type": kind,
            "space_id": f"B-F0-S{space}",
            "floor_id": "B-F0",
            "position": [10.4 * space + x, 5.0],
            "footprint": {"width_m": 1.5, "depth_m": 1.5, "rotation_deg": 0},
            "source": "generated",
        }

    assets = [
        asset(1, "CNC mill H-A1-A", "cnc_mill", 0, 2),
        asset(2, "CNC mill H-A1-B", "cnc_mill", 0, 5),
        asset(3, "CNC mill H-A1-C", "cnc_mill", 0, 8),
        asset(4, "Press H-A3", "press", 2, 5),
    ]
    door = {"kind": "door", "floor_id": "B-F0", "step_free": True, "width_m": 0.9, "synthetic": False}
    openings = [
        door | {"id": "B-O1", "space_ids": ["B-F0-S0", "B-F0-S1"], "position": [11.0, 5.0]},
        door | {"id": "B-O2", "space_ids": ["B-F0-S1", "B-F0-S2"], "position": [23.0, 5.0]},
        door | {"id": "B-O3", "space_ids": ["B-F0-S0", "outside"], "position": [0.0, 5.0], "kind": "entrance"},
    ]
    floors = [{"id": "B-F0", "name": "Ground", "level": 0, "elevation_m": 0.0}]
    info = {"name": "Factory", "source": "test"}
    building = {"building": info, "floors": floors, "spaces": spaces, "assets": assets}
    return BuildingMap(building | {"vertical_connectors": [], "openings": openings})


def names(bm: BuildingMap, *ids: str) -> list[str]:
    return [bm.assets[i]["name"] for i in ids]


# ---------- remove_door ----------


def test_remove_door_keeps_both_views_in_sync_and_records_it():
    bm = fresh()
    door = inner_door(bm)
    bm.closed.add(door["id"])
    count = len(bm.openings)
    edit_ops.remove_door(bm, door["id"])
    assert len(bm.openings) == count - 1 and door["id"] not in bm.closed
    assert door["id"] not in bm.openings
    assert bm.removed_openings == [door["id"]]
    assert_in_sync(bm)


def test_remove_door_by_room_pair():
    bm = fresh()
    door = inner_door(bm)
    first, second = door["space_ids"]
    edit_ops.remove_door(bm, first, second)
    assert door["id"] not in bm.openings


def test_removing_a_door_cuts_a_room_off_and_the_card_says_so():
    for path in BUILDINGS[:60]:
        bm = load(path)
        for opening in list(bm.openings.values()):
            if OUTSIDE in opening["space_ids"]:
                continue
            report = analyse(bm, doors_remove=[opening["id"]])
            if report.lost_route:
                room = report.lost_route[0]
                edit_ops.remove_door(bm, opening["id"])
                assert room not in routing.build_graph(bm, False).members or not routing_reaches(bm, room)
                return
    pytest.fail("no door that disconnects a room")


def routing_reaches(bm: BuildingMap, space_id: str) -> bool:
    entrance = next((o for o in bm.openings.values() if OUTSIDE in o["space_ids"]), None)
    if entrance is None:
        return False
    start = bm.other_side(entrance, OUTSIDE)
    try:
        routing.route(bm, start, space_id)
        return True
    except MapError:
        return False


def test_route_finds_the_alternative_after_a_removal():
    for path in BUILDINGS[:60]:
        bm = load(path)
        for opening in list(bm.openings.values()):
            if OUTSIDE in opening["space_ids"]:
                continue
            first, second = opening["space_ids"]
            if bm.spaces[first]["floor_id"] != bm.spaces[second]["floor_id"]:
                continue
            before = routing.route(bm, first, second).length_m
            copy_map = copy.deepcopy(bm)
            edit_ops.remove_door(copy_map, opening["id"])
            try:
                after = routing.route(copy_map, first, second).length_m
            except MapError:
                continue
            if after > before:
                return
    pytest.fail("no door with a longer alternative")


def test_last_entrance_is_protected_but_not_the_others():
    bm = fresh()
    entrances = [o for o in bm.openings.values() if OUTSIDE in o["space_ids"]]
    assert entrances
    for entrance in entrances[:-1]:
        edit_ops.remove_door(bm, entrance["id"])
    with pytest.raises(MapError, match="last entrance"):
        edit_ops.remove_door(bm, entrances[-1]["id"])
    assert entrances[-1]["id"] in bm.openings


def test_new_door_ids_do_not_collide_after_a_removal():
    bm = factory()
    edit_ops.remove_door(bm, "B-O1")
    first = edit_ops.add_door_safe(bm, "H-A1", "H-A2")
    edit_ops.remove_door(bm, "B-O2")
    second = edit_ops.add_door_safe(bm, "H-A2", "H-A3")
    assert first["id"] != second["id"] and {first["id"], second["id"]} <= set(bm.openings)
    assert_in_sync(bm)


def test_apply_change_add_door_after_a_removal_keeps_ids_unique():
    from building_agent.guide_tools import apply_change

    bm = factory()
    edit_ops.remove_door(bm, "B-O1")
    apply_change(bm, "add_door", "H-A1", "H-A2", True)
    edit_ops.remove_door(bm, "B-O2")
    apply_change(bm, "add_door", "H-A2", "H-A3", True)
    ids = [o["id"] for o in bm.data["openings"]]
    assert len(ids) == len(set(ids)) == len(bm.openings) == 3
    assert_in_sync(bm)


def test_add_door_id_collision_is_resolved():
    bm = fresh()
    door = inner_door(bm)
    first, second = door["space_ids"]
    floor = bm.spaces[first]["floor_id"]
    squatter = copy.deepcopy(door)
    squatter["id"] = f"{floor}-O-new{len(bm.openings) + 1}"
    squatter["space_ids"] = [first, OUTSIDE]  # not a duplicate of the pair that is added
    bm.openings[squatter["id"]] = squatter
    bm.data["openings"].append(squatter)
    bm.openings.pop(door["id"])
    bm.data["openings"].remove(door)
    new = edit_ops.add_door_safe(bm, first, second)
    assert new["id"] != squatter["id"] and bm.openings[new["id"]] is new
    assert_in_sync(bm)


# ---------- widen_door ----------


def test_widen_door_changes_only_the_width_in_both_views():
    bm = fresh()
    door = inner_door(bm)
    spaces, step_free = list(door["space_ids"]), door["step_free"]
    free_before = routing.build_graph(bm, True).graph.number_of_edges()
    edit_ops.widen_door(bm, door["id"], None, 2.4)
    assert door["width_m"] == 2.4 and bm.data["openings"][list(bm.openings).index(door["id"])]["width_m"] == 2.4
    assert door["space_ids"] == spaces and door["step_free"] == step_free
    assert routing.build_graph(bm, True).graph.number_of_edges() == free_before
    assert bm.widened_openings == {door["id"]: 2.4}
    assert_in_sync(bm)


@pytest.mark.parametrize("width", [0.5, 5.1, -1, float("nan"), None, True])
def test_widen_door_rejects_bad_widths(width):
    bm = fresh()
    with pytest.raises(MapError):
        edit_ops.widen_door(bm, inner_door(bm)["id"], None, width)


def test_widen_door_same_width_and_unknown_door_fail():
    bm = fresh()
    door = inner_door(bm)
    with pytest.raises(MapError):
        edit_ops.widen_door(bm, door["id"], None, door["width_m"])
    with pytest.raises(MapError):
        edit_ops.widen_door(bm, "no-such-door", None, 1.5)


# ---------- move_asset ----------


def asset_and_room(bm: BuildingMap):
    asset = next(a for a in bm.assets.values() if a["type"] != "desk")
    target = next(
        s["id"]
        for s in bm.spaces.values()
        if s["id"] != asset["space_id"] and s["type"] == "room" and s["floor_id"] == asset["floor_id"]
    )
    return asset, target


def test_move_asset_updates_space_floor_position_and_stays_in_sync():
    bm = factory()
    asset = bm.assets["B-A2"]
    edit = edit_ops.move_asset(bm, "B-A2", "H-A2")
    assert asset["id"] == "B-A2" and asset["space_id"] == "B-F0-S1" and asset["floor_id"] == "B-F0"
    assert Polygon(bm.spaces["B-F0-S1"]["polygon"]).contains(Point(*asset["position"]))
    assert edit["to_space"] == "B-F0-S1" and bm.moved_assets["B-A2"]["space_id"] == "B-F0-S1"
    assert_in_sync(bm)


def test_letters_move_the_middle_machine_away():
    bm = factory()
    edit_ops.move_asset(bm, "B-A2", "H-A2")
    assert names(bm, "B-A1", "B-A2", "B-A3") == ["CNC mill H-A1-A", "CNC mill H-A2", "CNC mill H-A1-C"]
    assert bm.assets["B-A2"]["aliases"] == ["CNC mill H-A1-B"]


def test_letters_second_move_leaves_one_sibling_without_letter():
    bm = factory()
    edit_ops.move_asset(bm, "B-A2", "H-A2")
    edit_ops.move_asset(bm, "B-A1", "H-A2")
    assert names(bm, "B-A3", "B-A2", "B-A1") == ["CNC mill H-A1", "CNC mill H-A2-A", "CNC mill H-A2-B"]
    assert_in_sync(bm)


def test_letters_arriving_next_to_a_lone_asset_and_next_letter_after_highest():
    bm = factory()
    bm.assets["B-A4"].update(name="CNC mill H-A3", type="cnc_mill")  # a lone mill in H-A3
    edit_ops.move_asset(bm, "B-A1", "H-A3")
    assert names(bm, "B-A4", "B-A1") == ["CNC mill H-A3-A", "CNC mill H-A3-B"]
    edit_ops.move_asset(bm, "B-A2", "H-A3")
    assert bm.assets["B-A2"]["name"] == "CNC mill H-A3-C"
    assert bm.assets["B-A3"]["name"] == "CNC mill H-A1"  # last one left in H-A1 loses its letter
    assert_in_sync(bm)


def test_old_names_still_resolve_through_aliases():
    bm = factory()
    edit_ops.move_asset(bm, "CNC mill H-A1-B", "H-A2")
    assert edit_ops.resolve_asset(bm, "CNC mill H-A1-B")["id"] == "B-A2"
    assert edit_ops.resolve_asset(bm, "cnc mill h-a2")["id"] == "B-A2"
    edit_ops.move_asset(bm, "CNC mill H-A1-B", "H-A3")  # old name moves it again
    assert bm.assets["B-A2"]["space_id"] == "B-F0-S2"


def test_ambiguous_name_lists_candidates():
    bm = fresh()
    first = next(iter(bm.assets.values()))
    twin = copy.deepcopy(first)
    twin["id"] = first["id"] + "-twin"
    bm.assets[twin["id"]] = twin
    bm.data["assets"].append(twin)
    with pytest.raises(MapError, match="several assets"):
        edit_ops.resolve_asset(bm, first["name"])


def test_locate_sees_the_new_room_after_a_move():
    bm = factory()
    edit_ops.move_asset(bm, "B-A2", "H-A2")
    found = find_asset(bm, "cnc mill")
    rooms = {group["space_id"]: [item["id"] for item in group["items"]] for group in found["groups"]}
    assert rooms == {"B-F0-S0": ["B-A1", "B-A3"], "B-F0-S1": ["B-A2"]}
    assert "B-A2" in bm.located_asset_ids
    bm.located_asset_ids = ["B-A2"]
    entry = located_entries(bm)[0]
    assert entry["space_id"] == "B-F0-S1" and entry["asset_id"] == "B-A2"


def test_move_resets_located_assets():
    bm = factory()
    bm.located_asset_ids = ["B-A1"]
    edit_ops.move_asset(bm, "B-A2", "H-A2")
    assert bm.located_asset_ids == []


def test_move_asset_fuzz():
    bm = fresh()
    asset, target = asset_and_room(bm)
    for bad_asset, bad_target in [
        ("no-such-asset", target),
        (asset["id"], "no-such-room"),
        (asset["id"], OUTSIDE),
        (asset["id"], asset["space_id"]),
        (asset["id"], ""),
    ]:
        with pytest.raises(MapError):
            edit_ops.move_asset(bm, bad_asset, bad_target)
    assert_in_sync(bm)


def test_move_into_a_too_small_room_is_refused():
    bm = fresh()
    asset, target = asset_and_room(bm)
    asset["footprint"] = {"width_m": 80.0, "depth_m": 80.0, "rotation_deg": 0}
    with pytest.raises(MapError, match="too small"):
        edit_ops.move_asset(bm, asset["id"], target)
    assert asset["space_id"] != target


def test_move_lands_inside_the_room_clear_of_other_assets():
    bm = factory()
    for number in (1, 2, 3):
        edit_ops.move_asset(bm, f"B-A{number}", "H-A3")
    room = Polygon(bm.spaces["B-F0-S2"]["polygon"])
    shapes = [asset_shape(a, *a["position"]) for a in bm.assets.values() if a["space_id"] == "B-F0-S2"]
    assert len(shapes) == 4
    assert all(room.contains(shape) for shape in shapes)
    assert all(a.distance(b) > 0 for i, a in enumerate(shapes) for b in shapes[i + 1 :])
    assert names(bm, "B-A1", "B-A2", "B-A3") == [f"CNC mill H-A3-{c}" for c in "ABC"]


def test_full_room_has_no_free_spot():
    bm = factory()
    bm.assets["B-A1"]["footprint"] = {"width_m": 9.9, "depth_m": 9.9, "rotation_deg": 0}
    bm.assets["B-A1"]["position"] = [10.4 * 2 + 5, 5.0]
    bm.assets["B-A1"]["space_id"] = "B-F0-S2"
    with pytest.raises(MapError, match="no free spot"):
        edit_ops.move_asset(bm, "B-A2", "H-A3")


# ---------- confirmation guard ----------


def tools_for(bm, tmp_path):
    state = GuideState()
    return {t.name: t for t in make_guide_tools(bm, tmp_path, state)}, state


def proposals():
    bm = fresh()
    door = inner_door(bm)
    asset, target = asset_and_room(bm)
    return [
        {"action": "remove_door", "element": door["id"]},
        {"action": "widen_door", "element": door["id"], "width_m": 2.0},
        {"action": "move_asset", "element": asset["id"], "to_space": target},
        {"action": "add_asset", "element": target, "asset_type": "chair", "hint": {"anchor": "NW"}},
        {"action": "move_asset", "element": asset["id"], "hint": {"anchor": "SE"}},
    ]


@pytest.mark.parametrize("index", [0, 1, 2, 3, 4])
def test_guard_same_turn_vague_yes_and_stale_card(index, tmp_path):
    kwargs = proposals()[index]
    bm = fresh()
    tools, state = tools_for(bm, tmp_path)
    snapshot = building_signature(bm)

    state.begin_turn()
    card = json.loads(tools["propose_change"](**kwargs))
    assert "waiting" in card["status"] and building_signature(bm) == snapshot
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="ja")  # same turn
    assert building_signature(bm) == snapshot

    state.begin_turn()
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="hmm, vielleicht")  # vague
    assert building_signature(bm) == snapshot

    state.begin_turn()
    tools["propose_change"](**kwargs)
    state.begin_turn()
    state.begin_turn()  # card is one message too old
    with pytest.raises(ToolError):
        tools["confirm_change"](confirmed=True, user_reply="ja")
    assert building_signature(bm) == snapshot


@pytest.mark.parametrize("index", [0, 1, 2, 3, 4])
def test_guard_confirmed_apply_saves_the_edited_building(index, tmp_path):
    kwargs = proposals()[index]
    bm = fresh()
    tools, state = tools_for(bm, tmp_path / "out")
    before = building_signature(bm)
    state.begin_turn()
    tools["propose_change"](**kwargs)
    state.begin_turn()
    result = json.loads(tools["confirm_change"](confirmed=True, user_reply="Ja, mach das"))
    assert result["applied"] and building_signature(bm) != before
    saved = json.loads((tmp_path / "out" / "building_edited.json").read_text())
    assert len(saved["openings"]) == len(bm.openings)
    assert_in_sync(bm)


def test_card_sentences_and_stale_signature(tmp_path):
    bm = fresh()
    door = inner_door(bm)
    tools, state = tools_for(bm, tmp_path)
    state.begin_turn()
    card = json.loads(tools["propose_change"](action="remove_door", element=door["id"]))
    assert "Remove" in card["I understood"] and card["effect on the whole building"]
    state.begin_turn()
    bm.closed.add(next(iter(bm.connectors), door["id"]))  # building changes behind the card
    with pytest.raises(ToolError, match="changed"):
        tools["confirm_change"](confirmed=True, user_reply="ja")
    state.begin_turn()
    card = json.loads(tools["propose_change"](action="widen_door", element=door["id"], width_m=2.0))
    assert "2.0 m" in card["I understood"]


def test_directions_go_stale_after_a_move(tmp_path):
    bm = fresh()
    tools, state = tools_for(bm, tmp_path)
    state.begin_turn()
    door = inner_door(bm)
    first, second = door["space_ids"]
    tools["give_directions"](start=first, destination=second)
    asset, target = asset_and_room(bm)
    edit_ops.move_asset(bm, asset["id"], target)
    with pytest.raises(ToolError, match="changed"):
        tools["next_steps"]()


# ---------- sweep ----------


def test_sweep_every_building_applies_each_op_without_crashing():
    for path in BUILDINGS:
        bm = load(path)
        inner = next((o for o in bm.openings.values() if OUTSIDE not in o["space_ids"]), None)
        if inner:
            edit_ops.widen_door(bm, inner["id"], None, 2.5 if inner.get("width_m") != 2.5 else 3.0)
            edit_ops.remove_door(bm, inner["id"])
        asset = next(iter(bm.assets.values()), None)
        if asset:
            for space in bm.spaces.values():
                if space["id"] != asset["space_id"] and space["type"] == "room":
                    try:
                        edit_ops.move_asset(bm, asset["id"], space["id"])
                        break
                    except MapError:
                        continue
        assert_in_sync(bm)


def test_sweep_add_asset_with_a_random_anchor_then_undo_restores_the_building():
    """One catalogue asset in a random room of every building; footprint inside, mirror in sync, undo exact."""
    anchors = ["NW", "NE", "SW", "SE", "N", "S", "E", "W", "center"]
    types = sorted(ASSET_CATALOG)
    placed = refused = 0
    for path in BUILDINGS:
        rng = random.Random(path.parent.name)
        bm = load(path)
        rooms = [s for s in bm.spaces.values() if s["type"] == "room"]
        if not rooms:
            continue
        room = rng.choice(rooms)
        before = building_signature(bm)
        snapshot = edit_ops.take_snapshot(bm, "add")
        try:
            edit = edit_ops.add_asset(bm, rng.choice(types), room["id"], {"anchor": rng.choice(anchors)})
        except MapError:
            refused += 1
            assert building_signature(bm) == before
            continue
        placed += 1
        asset = bm.assets[edit["id"]]
        assert Polygon(room["polygon"]).buffer(1e-6).contains(asset_shape(asset, *asset["position"])), path
        assert set(asset) == {
            "id",
            "name",
            "category",
            "type",
            "space_id",
            "floor_id",
            "position",
            "footprint",
            "source",
        }
        assert_in_sync(bm)
        edit_ops.restore_snapshot(bm, snapshot)
        assert building_signature(bm) == before and edit["id"] not in bm.assets
        assert bm.removed_assets == [edit["id"]]
        assert_in_sync(bm)
    assert placed > 200, (placed, refused)


def test_restore_snapshot_keeps_opening_dict_identity():
    bm = fresh()
    opening_id = next(iter(bm.openings))
    live = bm.openings[opening_id]
    snapshot = edit_ops.take_snapshot(bm, "x")
    live["width_m"] = 4.0
    edit_ops.restore_snapshot(bm, snapshot)
    assert bm.openings[opening_id] is live and live["width_m"] != 4.0
    assert_in_sync(bm)
