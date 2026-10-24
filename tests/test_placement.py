"""Offline tests for hint-based placement (place, move_asset with a hint) and add_asset."""

import json

import pytest
from shapely.affinity import rotate
from shapely.geometry import Point, Polygon

from building_agent import edit_ops
from building_agent.asset_catalog import ASSET_CATALOG, catalog_entry
from building_agent.edit_ops import asset_shape
from starter_agent.building_map import BuildingMap, MapError
from tests.test_edit_ops import assert_in_sync, factory, fresh

ROOM = "B-F0-S1"  # empty 10 x 10 m hall H-A2, x from 10.4 to 20.4
NINE_FIELDS = {"id", "name", "category", "type", "space_id", "floor_id", "position", "footprint", "source"}
ANCHORS = ["NW", "NE", "SW", "SE", "N", "S", "E", "W", "center"]


def shape_of(bm: BuildingMap, asset_id: str) -> Polygon:
    asset = bm.assets[asset_id]
    return asset_shape(asset, *asset["position"])


def room_of(bm: BuildingMap, space_id: str = ROOM) -> Polygon:
    return Polygon(bm.spaces[space_id]["polygon"])


def set_polygon(bm: BuildingMap, space_id: str, coords: list) -> None:
    bm.spaces[space_id]["polygon"][:] = [list(point) for point in coords]


def add(bm: BuildingMap, asset_type: str, hint: dict | None = None, room: str = "H-A2") -> dict:
    return edit_ops.add_asset(bm, asset_type, room, hint)


# ---------- anchors ----------


@pytest.mark.parametrize("anchor", ANCHORS)
def test_every_anchor_lands_inside_and_touches_the_right_walls(anchor):
    bm = factory()
    edit = add(bm, "cnc_mill", {"anchor": anchor})
    shape, room = shape_of(bm, edit["id"]), room_of(bm)
    assert room.contains(shape) and edit["placement"]["exact"] is True
    min_x, min_y, max_x, max_y = room.bounds
    gaps = {
        "N": max_y - shape.bounds[3],
        "S": shape.bounds[1] - min_y,
        "E": max_x - shape.bounds[2],
        "W": shape.bounds[0] - min_x,
    }
    for letter in {"N": "N", "S": "S", "E": "E", "W": "W"}:
        if letter in anchor and anchor != "center":
            assert gaps[letter] == pytest.approx(0.05, abs=0.002)
    if anchor == "center":
        assert shape.centroid.distance(room.centroid) < 0.2


def test_back_against_the_wall_rotation_follows_the_wall():
    bm = factory()
    north = add(bm, "cnc_mill", {"anchor": "N"})
    south = add(bm, "cnc_mill", {"anchor": "S"})
    east = add(bm, "cnc_mill", {"anchor": "E"})
    assert north["rotation_deg"] == 180.0 and south["rotation_deg"] == 0.0
    assert abs(east["rotation_deg"]) == 90.0


def test_rotation_deg_overrides_the_wall_rotation_and_extent_is_pulled_in():
    bm = factory()
    edit = add(bm, "cnc_mill", {"anchor": "SW", "rotation_deg": 90})
    shape = shape_of(bm, edit["id"])
    assert edit["rotation_deg"] == 90 and shape.bounds[0] == pytest.approx(10.45, abs=0.002)
    assert room_of(bm).contains(shape)


def test_anchor_aliases_and_bad_hints():
    bm = factory()
    assert add(bm, "chair", {"anchor": "centre"})["placement"]["anchor"] == "CENTER"
    assert add(bm, "chair", {"anchor": "north-west"})["placement"]["anchor"] == "NW"
    for bad in [{"anchor": "up"}, {"anchor": "NW", "near": "H-A1"}, {"colour": "red"}, {"point": [1]}, "NW"]:
        with pytest.raises(MapError):
            add(bm, "chair", bad)
    with pytest.raises(MapError):
        add(bm, "chair", {"rotation_deg": float("nan"), "anchor": "N"})
    assert_in_sync(bm)


def test_blocked_corner_reports_the_actual_spot():
    bm = factory()
    first = add(bm, "cnc_mill", {"anchor": "NW"})
    second = add(bm, "cnc_mill", {"anchor": "NW"})
    assert first["placement"]["exact"] and not second["placement"]["exact"]
    assert second["placement"]["distance_m"] > 0.1
    assert shape_of(bm, first["id"]).distance(shape_of(bm, second["id"])) >= edit_ops.CLEARANCE_M
    assert room_of(bm).contains(shape_of(bm, second["id"]))


# ---------- rotated, L-shaped, too small, full ----------


@pytest.mark.parametrize("anchor", ["NW", "NE", "SW", "SE", "N", "S", "E", "W"])
def test_rotated_building_follows_the_walls(anchor):
    bm = factory()
    box = room_of(bm)
    tilted = rotate(box, 20, origin=box.centroid)
    set_polygon(bm, ROOM, list(tilted.exterior.coords)[:-1])
    edit = add(bm, "cnc_mill", {"anchor": anchor})
    shape, room = shape_of(bm, edit["id"]), room_of(bm)
    assert room.contains(shape) and edit["placement"]["exact"]
    assert (edit["rotation_deg"] - 20 + 45) % 90 == pytest.approx(45, abs=0.2)
    assert shape.distance(room.exterior) == pytest.approx(0.05, abs=0.01)


def test_l_shaped_room_stays_inside_and_corners_work():
    bm = factory()
    set_polygon(bm, ROOM, [(10.4, 0), (20.4, 0), (20.4, 4), (14.4, 4), (14.4, 10), (10.4, 10)])
    room = room_of(bm)
    for anchor in ANCHORS:
        fresh_bm = BuildingMap(json.loads(json.dumps(bm.data)))
        edit = edit_ops.add_asset(fresh_bm, "desk", "H-A2", {"anchor": anchor})
        assert room.contains(shape_of(fresh_bm, edit["id"])), anchor
    corner = edit_ops.add_asset(bm, "desk", "H-A2", {"anchor": "SE"})
    assert corner["placement"]["exact"] and corner["position"][0] > 19


def test_hint_in_a_room_with_a_notch_reports_a_moved_spot():
    bm = factory()
    set_polygon(bm, ROOM, [(10.4, 0), (20.4, 0), (20.4, 10), (15.4, 10), (15.4, 6), (10.4, 6)])
    edit = add(bm, "cnc_mill", {"anchor": "NW"})
    assert room_of(bm).contains(shape_of(bm, edit["id"]))


def test_too_small_room_is_refused_with_a_clear_error():
    bm = factory()
    set_polygon(bm, ROOM, [(10.4, 0), (13.4, 0), (13.4, 3), (10.4, 3)])
    with pytest.raises(MapError, match="too small"):
        add(bm, "injection_moulding_machine", {"anchor": "NW"})
    before = len(bm.assets)
    assert len(bm.assets) == before and len(bm.data["assets"]) == before


def test_full_room_has_no_free_spot_for_a_hint():
    bm = factory()
    blocker = add(bm, "chair")
    bm.assets[blocker["id"]]["footprint"] = {"width_m": 9.9, "depth_m": 9.9, "rotation_deg": 0}
    bm.assets[blocker["id"]]["position"] = [15.4, 5.0]
    with pytest.raises(MapError, match="no free spot"):
        add(bm, "chair", {"anchor": "SE"})
    with pytest.raises(MapError, match="no free spot"):
        edit_ops.move_asset(bm, "B-A1", ROOM, {"anchor": "NW"})


def test_five_by_two_machine_fits_in_every_corner_and_turns_when_needed():
    bm = factory()
    for anchor in ANCHORS:
        edit = edit_ops.add_asset(
            BuildingMap(json.loads(json.dumps(bm.data))), "injection_moulding_machine", "H-A2", {"anchor": anchor}
        )
        assert edit["width_m"] == 5.0 and edit["depth_m"] == 2.0
    set_polygon(bm, ROOM, [(10.4, 0), (13.4, 0), (13.4, 7), (10.4, 7)])
    edit = add(bm, "injection_moulding_machine", {"anchor": "N"})
    assert room_of(bm).contains(shape_of(bm, edit["id"]))
    assert "turned 90 degrees to fit" in edit["placement"]["notes"]


# ---------- point, near, rotate, room_at ----------


def test_point_inside_the_room_is_used_exactly():
    bm = factory()
    edit = edit_ops.move_asset(bm, "B-A1", ROOM, {"point": [14.0, 3.0]})
    assert edit["position"] == [14.0, 3.0] and edit["placement"]["exact"]


def test_point_outside_the_room_is_a_clear_error_and_changes_nothing():
    bm = factory()
    before = json.dumps(bm.data["assets"])
    with pytest.raises(MapError, match="not inside"):
        edit_ops.move_asset(bm, "B-A1", ROOM, {"point": [5.0, 3.0]})
    with pytest.raises(MapError, match="No room"):
        edit_ops.move_asset(bm, "B-A1", None, {"point": [-50.0, 3.0]})
    assert json.dumps(bm.data["assets"]) == before


def test_point_on_an_occupied_spot_moves_to_the_nearest_free_one():
    bm = factory()
    edit = edit_ops.move_asset(bm, "B-A1", "H-A1", {"point": [5.0, 5.0]})  # B-A2 stands there
    assert not edit["placement"]["exact"] and edit["placement"]["distance_m"] > 0
    assert shape_of(bm, "B-A1").distance(shape_of(bm, "B-A2")) >= edit_ops.CLEARANCE_M


def test_click_picks_the_room_containing_the_point():
    bm = factory()
    assert edit_ops.room_at(bm, [15.0, 5.0], "B-F0") == ROOM
    assert edit_ops.room_at(bm, [-3.0, 5.0], "B-F0") is None
    edit = edit_ops.move_asset(bm, "B-A1", None, {"point": [15.0, 5.0]})
    assert edit["to_space"] == ROOM and bm.assets["B-A1"]["name"] == "CNC mill H-A2"


def test_other_floor_is_respected():
    bm = factory()
    bm.floors["B-F1"] = {"id": "B-F1", "name": "Upper", "level": 1, "elevation_m": 3.0}
    upper = {**bm.spaces[ROOM], "id": "B-F1-S0", "floor_id": "B-F1", "name": "Hall Up", "ref": "H-UP"}
    bm.spaces[upper["id"]] = upper
    bm.data["spaces"].append(upper)
    assert edit_ops.room_at(bm, [15.0, 5.0], "B-F1") == "B-F1-S0"
    edit = edit_ops.move_asset(bm, "B-A1", None, {"point": [15.0, 5.0], "floor_id": "B-F1"})
    assert bm.assets["B-A1"]["floor_id"] == "B-F1" and edit["to_space"] == "B-F1-S0"


def test_near_an_asset_and_near_a_room():
    bm = factory()
    edit = edit_ops.move_asset(bm, "B-A3", None, {"near": "B-A1"})
    assert edit["to_space"] == "B-F0-S0" and edit["placement"]["near"] == "CNC mill H-A1-A"
    assert shape_of(bm, "B-A3").distance(shape_of(bm, "B-A1")) >= edit_ops.CLEARANCE_M
    assert edit["placement"]["gap_m"] < 1.5
    edit_ops.move_asset(bm, "B-A2", ROOM, {"near": "H-A1"})
    assert bm.assets["B-A2"]["position"][0] < 14
    with pytest.raises(MapError, match="not in"):
        edit_ops.move_asset(bm, "B-A3", ROOM, {"near": "B-A1"})
    with pytest.raises(MapError, match="itself"):
        edit_ops.move_asset(bm, "B-A1", None, {"near": "B-A1"})


def test_same_room_move_keeps_the_name_and_letters():
    bm = factory()
    edit = edit_ops.move_asset(bm, "B-A2", None, {"anchor": "SW"})
    assert bm.assets["B-A2"]["name"] == "CNC mill H-A1-B" and "aliases" not in bm.assets["B-A2"]
    assert edit["from_space"] == edit["to_space"] and bm.moved_assets["B-A2"]["position"] == edit["position"]
    with pytest.raises(MapError, match="already in"):
        edit_ops.move_asset(bm, "B-A2", "H-A1")


def test_rotate_in_place():
    bm = factory()
    before = bm.assets["B-A2"]["position"][:]
    edit = edit_ops.move_asset(bm, "B-A2", None, {"rotation_deg": 90})
    assert bm.assets["B-A2"]["footprint"]["rotation_deg"] == 90 and bm.assets["B-A2"]["position"] == before
    assert edit["placement"]["mode"] == "rotate"


def test_move_to_another_room_with_a_hint_renames_and_places():
    bm = factory()
    edit = edit_ops.move_asset(bm, "B-A2", ROOM, {"anchor": "NE"})
    assert bm.assets["B-A2"]["name"] == "CNC mill H-A2" and bm.assets["B-A2"]["aliases"] == ["CNC mill H-A1-B"]
    assert room_of(bm).contains(shape_of(bm, "B-A2")) and edit["placement"]["anchor"] == "NE"
    assert_in_sync(bm)


# ---------- add_asset ----------


def test_add_asset_has_exactly_the_nine_fields_and_the_catalogue_size():
    bm = factory()
    edit = add(bm, "cnc_mill")
    asset = bm.assets[edit["id"]]
    assert set(asset) == NINE_FIELDS
    assert asset["footprint"] == {"width_m": 3.0, "depth_m": 2.5, "rotation_deg": 0}
    assert asset["source"] == "generated" and asset["category"] == "machine" and asset["type"] == "cnc_mill"
    assert asset["space_id"] == ROOM and asset["floor_id"] == "B-F0" and len(asset["position"]) == 2
    assert asset["name"] == "CNC mill H-A2"


def test_add_asset_id_follows_the_building_scheme():
    bm = factory()
    assert add(bm, "chair")["id"] == "B-A00005"
    assert add(bm, "chair")["id"] == "B-A00006"
    real = fresh()
    prefix = next(iter(real.assets)).rsplit("-A", 1)[0]
    last = max(int(a.rsplit("-A", 1)[1]) for a in real.assets)
    room = next(s["id"] for s in real.spaces.values() if s["type"] == "room" and Polygon(s["polygon"]).area > 12)
    assert edit_ops.add_asset(real, "chair", room)["id"] == f"{prefix}-A{last + 1:05d}"


def test_add_asset_names_and_sibling_letters():
    bm = factory()
    first = add(bm, "cnc_mill")
    second = add(bm, "cnc_mill")
    third = add(bm, "cnc_mill")
    assert bm.assets[first["id"]]["name"] == "CNC mill H-A2-A" and bm.assets[first["id"]]["aliases"] == [
        "CNC mill H-A2"
    ]
    assert second["renamed_siblings"] == [{"id": first["id"], "old": "CNC mill H-A2", "new": "CNC mill H-A2-A"}]
    assert bm.assets[second["id"]]["name"] == "CNC mill H-A2-B" and third["name"] == "CNC mill H-A2-C"
    assert edit_ops.resolve_asset(bm, "CNC mill H-A2").get("id") == first["id"]
    bm.assets["B-A4"].update(name="CNC mill H-A3", type="cnc_mill")
    other = edit_ops.add_asset(bm, "cnc_mill", "H-A3")
    assert other["name"] == "CNC mill H-A3-B" and bm.assets["B-A4"]["name"] == "CNC mill H-A3-A"


def test_add_asset_custom_name_and_duplicate_name():
    bm = factory()
    assert add(bm, "chair")["name"] == "Chair H-A2"
    edit = edit_ops.add_asset(bm, "chair", "H-A2", None, name="Boss chair")
    assert edit["name"] == "Boss chair"
    with pytest.raises(MapError, match="exists already"):
        edit_ops.add_asset(bm, "chair", "H-A2", None, name="boss chair")


def test_add_asset_mirror_and_records():
    bm = factory()
    bm.located_asset_ids = ["B-A1"]
    edit = add(bm, "cnc_mill", {"anchor": "N"})
    assert bm.assets[edit["id"]] is bm.data["assets"][-1]
    assert bm.located_asset_ids == [] and bm.added_assets[edit["id"]]["name"] == "CNC mill H-A2"
    assert bm.last_edit is edit and edit["action"] == "add_asset"
    assert_in_sync(bm)


def test_add_asset_unknown_type_lists_close_names_and_never_guesses():
    bm = factory()
    with pytest.raises(MapError, match="cnc_mill"):
        add(bm, "cnc_mil")
    with pytest.raises(MapError, match="Known types"):
        add(bm, "zzzzqq")
    with pytest.raises(MapError, match="Unknown asset type"):
        add(bm, "")
    with pytest.raises(MapError):
        edit_ops.add_asset(bm, "chair", "no-such-room")
    assert len(bm.assets) == 4 and not hasattr(bm, "added_assets")


def test_catalogue_is_complete_and_label_lookup_works():
    assert 90 <= len(ASSET_CATALOG) <= 110
    for entry in ASSET_CATALOG.values():
        assert set(entry) == {"category", "label", "width_m", "depth_m"} and entry["width_m"] > 0 < entry["depth_m"]
    assert catalog_entry("CNC Mill")[0] == "cnc_mill" and catalog_entry("3d printer")[0] == "3d_printer"


def test_new_asset_footprint_is_not_shared_between_assets():
    bm = factory()
    first, second = add(bm, "chair"), add(bm, "chair")
    bm.assets[first["id"]]["footprint"]["width_m"] = 9
    assert bm.assets[second["id"]]["footprint"]["width_m"] == 0.5 == ASSET_CATALOG["chair"]["width_m"]


def test_point_hint_inside_polygon_check_uses_the_polygon_not_the_bounds():
    bm = factory()
    set_polygon(bm, ROOM, [(10.4, 0), (20.4, 0), (20.4, 4), (14.4, 4), (14.4, 10), (10.4, 10)])
    assert not room_of(bm).contains(Point(18, 8))
    with pytest.raises(MapError, match="not inside"):
        add(bm, "chair", {"point": [18, 8]})
