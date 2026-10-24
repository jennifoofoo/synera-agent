"""Offline tests of the stairs and lifts between floors (Level 4): typing, linking, the fixes and the card wording.

Two sources: artificial extractions of real dev floors (tests/level4_helpers) and the cached real vision answers of
the live test (agent_output/level4_cache, skipped when the cache is not there)."""

import dataclasses
import json
import random
import sys
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError

from building_agent.guide_tools import GuideState
from building_agent.level4 import tools as level4_tools
from building_agent.level4.convert import (
    FloorInput,
    convert_floors_with_findings,
    detect_connector,
    relink_connectors,
)
from building_agent.level4.extract import ExtractResult
from building_agent.level4.schema import ExtractedRoom, Extraction, Scale
from building_agent.level4.tools import BMHolder, make_level4_tools
from building_agent.level4.validate import Collector, describe, validate
from starter_agent.building_map import BuildingMap
from tests.level4_helpers import floor_case, load_building

PROC, SWISS, OSM = "proc-campus-dev-000", "swiss-1785", "osm-way360544293"
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64
FILL = {"stair": "orange", "lift": "purple"}


def codes(findings) -> set[str]:
    return {item.code for item in findings.items}


def strip_types(extraction: Extraction, keep_names: bool, fill: bool = False) -> Extraction:
    """What the vision model gave on the live test: stairs and lifts typed as plain rooms."""
    rooms = []
    for room in extraction.rooms:
        connector = room.type in ("stair", "lift")
        rooms.append(
            dataclasses.replace(
                room,
                type="room" if connector else room.type,
                room_type="generic_room" if connector else room.room_type,
                name=room.name if keep_names else None,
                fill=FILL.get(room.type) if fill else None,
            )
        )
    return dataclasses.replace(extraction, rooms=rooms)


def floors_of(building_id: str, levels=(0, 1), **options) -> list[FloorInput]:
    inputs = []
    for level in levels:
        case = floor_case(building_id, level)
        inputs.append(FloorInput(level, strip_types(case.extraction, **options), case.scale))
    return inputs


def true_pairs(building_id: str) -> set[frozenset]:
    """The refs of the stops of every original connector between level 0 and 1."""
    original = BuildingMap(load_building(building_id))
    levels = {f["id"]: f["level"] for f in original.data["floors"]}
    pairs = set()
    for connector in original.connectors.values():
        stops = {levels[original.spaces[s]["floor_id"]]: original.spaces[s].get("ref") for s in connector["space_ids"]}
        if {0, 1} <= set(stops):
            pairs.add(frozenset((connector["kind"], stops[0], stops[1])))
    return pairs


def built_pairs(building: dict) -> set[frozenset]:
    levels = {f["id"]: f["level"] for f in building["floors"]}
    refs = {s["id"]: (s.get("ref"), levels[s["floor_id"]]) for s in building["spaces"]}
    pairs = set()
    for connector in building["vertical_connectors"]:
        stops = {refs[s][1]: refs[s][0] for s in connector["space_ids"]}
        if {0, 1} <= set(stops):
            pairs.add(frozenset((connector["kind"], stops[0], stops[1])))
    return pairs


# ---------- typing ----------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Staircase 1", "stair"),
        ("Stair hall 0.35", None),
        ("Stairs and Lift", "stair"),
        ("Elevator lobby", None),
        ("Lift motor room", None),
        ("Treppenhaus", "stair"),
        ("Lift 2", "lift"),
        ("Aufzug", "lift"),
        ("Elevator B", "lift"),
        ("Lifting room", None),
        ("Shifted storage", None),
        ("Stairway to heaven bar", None),
        ("Kitchen", None),
    ],
)
def test_word_rules_match_whole_words_only(name, expected):
    assert detect_connector("room", "generic_room", name, None)[0] == expected


def test_model_type_and_room_type_win_and_a_specific_room_type_is_never_retyped():
    assert detect_connector("stair", "generic_room", None, None) == ("stair", "model")
    assert detect_connector("corridor", "stairwell", None, None)[0] == "stair"
    assert detect_connector("room", "kitchen", "Lift kitchen", None)[0] is None
    assert detect_connector("room", "generic_room", None, "Treppe 2")[0] == "stair"
    assert detect_connector("room", "generic_room", None, None, "orange")[0] == "stair"
    assert detect_connector("room", "generic_room", None, None, "purple")[0] == "lift"
    assert detect_connector("room", "generic_room", "Office", None, "orange")[0] is None  # a name beats the colour
    assert detect_connector("room", "office", None, None, "orange")[0] is None


def test_a_kitchen_called_lifting_room_stays_a_room():
    floors = []
    for level in (0, 1):
        extraction = floor_case(PROC, level).extraction
        extraction.rooms.append(ExtractedRoom("k", [[0, 0], [30, 0], [30, 30], [0, 30]], ref="K", name="Lifting room"))
        floors.append(FloorInput(level, strip_types(extraction, True), floor_case(PROC, level).scale))
    building, _ = convert_floors_with_findings(floors, "T", "t1")
    kitchen = [s for s in building["spaces"] if s["name"] == "Lifting room"]
    assert kitchen and all(s["type"] == "room" for s in kitchen)


def test_stairs_typed_as_room_are_found_by_name():
    building, findings = convert_floors_with_findings(floors_of(PROC, keep_names=True), "T", "t1")
    assert built_pairs(building) == true_pairs(PROC)
    assert len(building["vertical_connectors"]) == 6
    assert "connector_typed_by_hint" in codes(findings)
    assert not validate(building).errors


def test_stairs_typed_as_room_are_found_by_plan_colour():
    building, _ = convert_floors_with_findings(floors_of(PROC, keep_names=False, fill=True), "T", "t1")
    assert built_pairs(building) == true_pairs(PROC)
    assert sorted(c["kind"] for c in building["vertical_connectors"]) == ["lift"] * 3 + ["stairs"] * 3


def test_without_any_hint_nothing_is_invented():
    building, findings = convert_floors_with_findings(floors_of(PROC, keep_names=False), "T", "t1")
    assert building["vertical_connectors"] == []
    assert "connector_typed_by_hint" not in codes(findings)
    assert "no_vertical_connectors" in codes(validate(building))


# ---------- linking when the numbers differ per floor ----------


def swiss_floors(**options) -> list[FloorInput]:
    inputs = []
    for level in (0, 1):
        case = floor_case(SWISS, level)
        rooms = [
            dataclasses.replace(r, type="corridor", room_type="stairwell", name=f"Stair hall {r.ref}")
            if r.name and r.name.startswith("Stair hall")
            else dataclasses.replace(r, name=None)
            for r in case.extraction.rooms
        ]
        inputs.append(FloorInput(level, dataclasses.replace(case.extraction, rooms=rooms), case.scale))
    return inputs


def test_swiss_stair_hall_links_stairs_and_asks_for_the_lift():
    building, _ = convert_floors_with_findings(swiss_floors(), "T", "t1")
    kinds = [c["kind"] for c in building["vertical_connectors"]]
    assert "stairs" in kinds and "lift" not in kinds  # a hall space is not turned into a lift that nobody named
    linked = {s for c in building["vertical_connectors"] for s in c["space_ids"]}
    refs = {s["ref"] for s in building["spaces"] if s["id"] in linked}
    assert "0.35" in refs and refs & {"1.34", "1.35"}
    assert level4_tools.connector_question(building).startswith("lift_not_found")
    assert "no_vertical_connectors" not in codes(validate(building))
    assert len(building["vertical_connectors"]) >= 1 and "connector_missing_stop" not in codes(validate(building))


def test_one_stair_on_each_floor_links_by_order_even_when_far_apart():
    first = floors_of(PROC, keep_names=True)
    for floor in first:  # keep a single stair and nothing else, far apart in the two floors
        keep = "0.04" if floor.level == 0 else "1.14"
        floor.extraction.rooms = [
            r if r.ref == keep or r.type != "room" or r.name is None else dataclasses.replace(r, name=None)
            for r in floor.extraction.rooms
            if not (r.name and ("Stair" in r.name or "Lift" in r.name) and r.ref != keep)
        ]
    building, findings = convert_floors_with_findings(first, "T", "t1")
    assert len(building["vertical_connectors"]) == 1
    assert "connector_linked_by_order" in codes(findings)


def test_floors_cropped_differently_are_centred_for_the_match():
    floors = floors_of(PROC, keep_names=False, fill=True)
    moved = []
    for floor in floors:
        shift = 500.0 if floor.level == 1 else 0.0
        rooms = [
            dataclasses.replace(r, polygon_px=[[x + shift, y] for x, y in r.polygon_px]) for r in floor.extraction.rooms
        ]
        doors = [
            dataclasses.replace(d, position_px=[d.position_px[0] + shift, d.position_px[1]])
            for d in floor.extraction.doors
        ]
        moved.append(
            FloorInput(floor.level, dataclasses.replace(floor.extraction, rooms=rooms, doors=doors), floor.scale)
        )
    building, findings = convert_floors_with_findings(moved, "T", "t1")
    assert len(building["vertical_connectors"]) == 6
    assert "connector_aligned_by_centre" in codes(findings)


def test_osm_lifts_with_equal_frames_link_without_wrong_pairs():
    floors = []
    for level in (0, 1):
        case = floor_case(OSM, level)
        floors.append(FloorInput(level, strip_types(case.extraction, keep_names=True), case.scale))
    building, _ = convert_floors_with_findings(floors, "T", "t1")
    built = built_pairs(building)
    assert true_pairs(OSM) <= built  # every real lift pair
    assert len(built) - len(true_pairs(OSM)) <= 1  # plus at most the one more lift-typed room pair the plan has


# ---------- the conversation: build, fix, card, save ----------


class FloorRig:
    """The tools with one artificial extraction per image name (no API, no network)."""

    def __init__(self, tmp_path: Path, monkeypatch, extractions: dict[str, Extraction]):
        self.uploads = tmp_path / "uploads"
        self.uploads.mkdir()
        for name in extractions:
            (self.uploads / name).write_bytes(PNG)
        self.extractions = extractions
        self.saved: list[Path] = []
        monkeypatch.setattr(
            level4_tools,
            "extract_floor",
            lambda path, client=None, allowed_root=None, **kw: ExtractResult(
                self.extractions[Path(path).name], 1, 1, 0.1, 0.01
            ),
        )
        self.holder = BMHolder(BuildingMap(load_building("resplan-439")))
        self.state = GuideState()
        made = make_level4_tools(
            self.holder, tmp_path / "out", self.state, self.saved.append, self.uploads, tmp_path / "buildings"
        )
        self.tools = {tool.name: tool for tool in made}

    def turn(self) -> None:
        self.state.begin_turn()

    def call(self, name: str, **kwargs) -> dict:
        return json.loads(self.tools[name](**kwargs))

    def build(self, name: str, level: int, width_m: float | None = None, **kwargs) -> dict:
        xs = [x for r in self.extractions[name].rooms for x, _ in r.polygon_px]
        scale = (width_m or 1.0) / (max(xs) - min(xs)) if width_m else None
        return (
            self.call("build_from_plan", image_path=name, level=level, known_length_m=width_m, **kwargs)
            if scale
            else {}
        )

    @property
    def draft(self):
        return self.state.level4

    def card(self) -> dict:
        self.turn()
        card = self.call("preview_draft")
        self.turn()
        return card


def width_of(building_id: str, level: int) -> float:
    xs = [x for s in floor_case(building_id, level).truth["spaces"] for x, _ in s["polygon"]]
    return max(xs) - min(xs)


def bare_swiss() -> list[FloorInput]:
    """The swiss floors as the model typed them: no word, no type that says stairs."""
    floors = swiss_floors()
    for floor in floors:
        floor.extraction.rooms = [
            dataclasses.replace(r, name=None, room_type="generic_room") for r in floor.extraction.rooms
        ]
    return floors


def two_floor_rig(tmp_path, monkeypatch, building_id=PROC, floors=None, **options) -> FloorRig:
    floors = floors or floors_of(building_id, **options)
    rig = FloorRig(tmp_path, monkeypatch, {f"f{f.level}.png": f.extraction for f in floors})
    rig.turn()
    for floor in floors:
        rig.build(f"f{floor.level}.png", floor.level, width_of(building_id, floor.level))
    return rig


def test_set_room_type_sets_the_type_and_relinks(tmp_path, monkeypatch):
    rig = two_floor_rig(tmp_path, monkeypatch, keep_names=False)
    assert rig.draft.building["vertical_connectors"] == []
    done = rig.call("fix_draft", action="set_room_type", ref="0.04", room_type="stairwell", level=0)["done"]
    assert "stairwell" in done
    assert rig.draft.building["vertical_connectors"] == []  # one floor only: nothing to link to yet
    reply = rig.call("fix_draft", action="set_room_type", ref="1.04", room_type="stairwell", level=1)
    (connector,) = rig.draft.building["vertical_connectors"]
    assert connector["kind"] == "stairs" and len(connector["space_ids"]) == 2
    spaces = {s["ref"]: s for s in rig.draft.building["spaces"]}
    assert spaces["0.04"]["type"] == "stair" and spaces["1.04"]["type"] == "stair"
    assert "linked" in reply["done"]
    rig.call("fix_draft", action="set_room_type", ref="0.05", room_type="lift", level=0)
    rig.call("fix_draft", action="set_room_type", ref="1.05", room_type="elevator", level=1)
    assert sorted(c["kind"] for c in rig.draft.building["vertical_connectors"]) == ["lift", "stairs"]
    rig.call("fix_draft", action="set_room_type", ref="1.05", room_type="office", level=1)  # taking it back
    assert [c["kind"] for c in rig.draft.building["vertical_connectors"]] == ["stairs"]


def test_link_floors_joins_rooms_with_different_numbers_and_survives_a_rescale(tmp_path, monkeypatch):
    rig = two_floor_rig(tmp_path, monkeypatch, SWISS, floors=bare_swiss())
    assert rig.draft.building["vertical_connectors"] == []
    done = rig.call(
        "fix_draft", action="link_floors", ref="0.35", other_ref="1.34", kind="stairs", level=0, other_level=1
    )["done"]
    assert "linked" in done
    rig.call("fix_draft", action="link_floors", ref="0.35", other_ref="1.34", kind="lift", level=0, other_level=1)
    kinds = sorted(c["kind"] for c in rig.draft.building["vertical_connectors"])
    assert kinds == ["lift", "stairs"]
    rig.call("fix_draft", action="set_scale", known_length_m=width_of(SWISS, 0) * 1.1, level=0)
    assert sorted(c["kind"] for c in rig.draft.building["vertical_connectors"]) == ["lift", "stairs"]
    assert not any(f.code == "no_vertical_connectors" for f in rig.draft.findings.items)
    with pytest.raises(ToolError, match="already linked"):
        rig.call("fix_draft", action="link_floors", ref="0.35", other_ref="1.34", kind="lift", level=0, other_level=1)


def test_link_floors_refuses_bad_requests(tmp_path, monkeypatch):
    rig = two_floor_rig(tmp_path, monkeypatch, keep_names=False)
    link = {"action": "link_floors", "kind": "stairs"}
    with pytest.raises(ToolError, match="same floor"):
        rig.call("fix_draft", ref="0.04", other_ref="0.09", level=0, other_level=0, **link)
    with pytest.raises(ToolError, match="kind"):
        rig.call("fix_draft", action="link_floors", kind="ladder", ref="0.04", other_ref="1.04")
    with pytest.raises(ToolError, match="needs ref"):
        rig.call("fix_draft", ref="0.04", **link)
    with pytest.raises(ToolError, match="No room"):
        rig.call("fix_draft", ref="0.04", other_ref="9.99", **link)
    assert rig.draft.building["vertical_connectors"] == []


def test_link_floors_only_joins_neighbouring_floors(tmp_path, monkeypatch):
    floors = floors_of(PROC, levels=(0, 1), keep_names=False)
    third = dataclasses.replace(floors[1], level=2)
    rig = FloorRig(
        tmp_path,
        monkeypatch,
        {"f0.png": floors[0].extraction, "f1.png": floors[1].extraction, "f2.png": third.extraction},
    )
    rig.turn()
    for level in (0, 1, 2):
        rig.build(f"f{level}.png", level, width_of(PROC, 0))
    with pytest.raises(ToolError, match="neighbours"):
        rig.call("fix_draft", action="link_floors", kind="stairs", ref="0.04", other_ref="1.04", level=0, other_level=2)
    rig.call("fix_draft", action="link_floors", kind="stairs", ref="0.04", other_ref="1.04", level=0, other_level=1)
    assert len(rig.draft.building["vertical_connectors"]) == 1


def test_card_says_no_stairs_found_instead_of_no_way_out(tmp_path, monkeypatch):
    rig = two_floor_rig(tmp_path, monkeypatch, keep_names=False)
    card = rig.card()
    problems = card["problems found"]
    assert "I found 2 floors but no stairs or lifts between them. Which rooms are the stairs and lifts?" in problems
    assert "no way out" not in problems  # the upper floor is not blamed on missing doors
    assert card["can be saved"] is False
    assert "stairs or lifts" in card["question"] and "link_floors" in card["question"]
    assert "stairs or lifts" in card["saving blocked"]


def test_connector_free_draft_saves_only_after_an_explicit_anyway(tmp_path, monkeypatch):
    rig = two_floor_rig(tmp_path, monkeypatch, keep_names=False)
    rig.card()
    with pytest.raises(ToolError, match="block"):
        rig.call("save_building", confirmed=True, user_reply="yes, save it")
    rig.card()
    result = rig.call("save_building", confirmed=True, user_reply="yes, save it anyway", accept_problems=True)
    assert result["saved"] and "stairs or lifts" in result["accepted_problems"]


def test_plain_yes_saves_a_two_floor_draft_with_connectors(tmp_path, monkeypatch):
    rig = two_floor_rig(tmp_path, monkeypatch, keep_names=True)
    card = rig.card()
    assert card["can be saved"] is True and "no_vertical" not in card["problems found"]
    assert "question" not in card
    result = rig.call("save_building", confirmed=True, user_reply="yes, save it")
    assert result["saved"] and len(rig.holder.bm.connectors) == 6


def test_unrepaired_floors_get_a_question_with_candidates_after_the_second_floor(tmp_path, monkeypatch):
    floors = bare_swiss()
    rig = FloorRig(tmp_path, monkeypatch, {f"f{f.level}.png": f.extraction for f in floors})
    rig.turn()
    assert "question" not in rig.build("f0.png", 0, width_of(SWISS, 0))  # one floor: nothing to join yet
    summary = rig.build("f1.png", 1, width_of(SWISS, 1))
    assert "no stairs or lifts" in summary["question"]
    assert "floor 0: 0.35" in summary["question"] or "floor 0: 0.34" in summary["question"]


# ---------- scale ----------


def test_a_large_building_is_only_a_warning_when_the_person_gave_the_length(tmp_path, monkeypatch):
    floor = floors_of(PROC, levels=(0,), keep_names=True)[0]
    rig = FloorRig(tmp_path, monkeypatch, {"f0.png": floor.extraction})
    rig.turn()
    rig.build("f0.png", 0, 600.0)
    found = codes(rig.draft.findings)
    assert "scale_unusual_known" in found and "scale_implausible" not in found
    assert not any(f.code == "scale_unusual_known" for f in rig.draft.findings.errors)
    rig.turn()
    rig.call("fix_draft", action="set_scale", known_length_m=100.0, along="door", level=0)
    # a door width as the ruler is a guess, so the old error stays for it
    assert "scale_implausible" in codes(rig.draft.findings)


def test_a_printed_scale_bar_keeps_the_size_error(tmp_path, monkeypatch):
    floor = floors_of(PROC, levels=(0,), keep_names=True)[0]
    extraction = floor.extraction
    extraction.scale_bar_px, extraction.scale_bar_m = 100.0, 100.0 * floor.scale.metres_per_px * 50
    rig = FloorRig(tmp_path, monkeypatch, {"f0.png": extraction})
    rig.turn()
    rig.call("build_from_plan", image_path="f0.png", level=0)
    assert "scale_implausible" in codes(rig.draft.findings) and not rig.draft.findings.ok


def test_validate_downgrades_the_size_error_only_for_a_trusted_scale():
    building, _ = convert_floors_with_findings(
        [FloorInput(0, floors_of(PROC, (0,), keep_names=True)[0].extraction, Scale(0.5, "known_length"))], "T", "t1"
    )
    assert "scale_implausible" in codes(validate(building))
    trusted = validate(building, trusted_scale=True)
    assert "scale_implausible" not in codes(trusted) and "scale_unusual_known" in codes(trusted)


# ---------- the cached real answers of the live test ----------


def live_rig(tmp_path, monkeypatch, building_id: str):
    sys.path.insert(0, "scripts")
    import level4_live_test as live

    images = [Path("data/dev") / building_id / f"floor_{level}_plain.png" for level in (0, 1)]
    if not all(image.exists() and live.cached_raw(image) for image in images):
        pytest.skip("cached live extractions are not available")
    monkeypatch.setattr(level4_tools, "extract_floor", level4_tools.extract_floor)  # restore the original afterwards
    rig = live.LiveRig(tmp_path, building_id)
    rig.turn()
    for level in (0, 1):
        live.build_one(rig, building_id, level, images[level], f"f{level}.png", live.floor_width_m(building_id, level))
    return live, rig


def test_cached_proc_two_floors_reach_the_upper_bound(tmp_path, monkeypatch):
    live, rig = live_rig(tmp_path, monkeypatch, PROC)
    result = live.evaluate_building(PROC, BuildingMap(rig.draft.building))
    assert len(result["produced_connectors"]) == 6 and result["connectors_recovered"] == 6
    assert result["connectors_not_matching_an_original"] == 0
    for mode in ("normal", "step_free"):
        cross = result["cross_floor"][mode]
        assert cross["pairs"] == 292 and cross["full"] == 292 and cross["no_route"] == 0 and cross["invalid"] == 0
    rig.turn()
    card = rig.call("preview_draft")
    assert card["can be saved"] is True
    rig.turn()
    assert rig.call("save_building", confirmed=True, user_reply="yes, save it")["saved"]


def test_cached_swiss_asks_and_link_floors_repairs_it(tmp_path, monkeypatch):
    live, rig = live_rig(tmp_path, monkeypatch, SWISS)
    assert rig.draft.building["vertical_connectors"] == []  # the halls carry no word and no colour: ask, do not guess
    assert "no_vertical_connectors" in codes(rig.draft.findings)
    for kind, first, second in (("stairs", "0.35", "1.34"), ("lift", "0.35", "1.34"), ("stairs", "0.35", "1.35")):
        rig.call("fix_draft", action="link_floors", ref=first, other_ref=second, kind=kind, level=0, other_level=1)
    result = live.evaluate_building(SWISS, BuildingMap(rig.draft.building))
    # Every pair the kit 1.1.0 labels can walk (the pair counts follow the building data, not constants) is walked
    # with full marks on the repaired building, normal and step free.
    assert result["original_connectors_0_1"]["count"] == 3  # the stairs, the lift and the second stairs of the labels
    for mode in ("normal", "step_free"):
        cross = result["cross_floor"][mode]
        assert cross["pairs"] > 0 and cross["full"] == cross["pairs"]
        assert cross["invalid"] == 0 and cross["no_route"] == 0


def test_cached_osm_does_not_crash_and_links_nothing_wrong(tmp_path, monkeypatch):
    _, rig = live_rig(tmp_path, monkeypatch, OSM)
    assert rig.draft.building["vertical_connectors"] == []
    found = codes(rig.draft.findings)
    assert "no_vertical_connectors" in found and "scale_implausible" not in found
    rig.turn()
    assert "no stairs or lifts" in rig.call("preview_draft")["question"]


# ---------- odd input ----------


def test_floors_without_rooms_and_three_floors_do_not_crash():
    floors = floors_of(PROC, levels=(0, 1), keep_names=True)
    empty = FloorInput(2, dataclasses.replace(floors[0].extraction, rooms=[], doors=[]), floors[0].scale)
    building, findings = convert_floors_with_findings([*floors, empty], "T", "t1")
    assert "floor_empty" in codes(findings) and len(building["vertical_connectors"]) == 6
    third = dataclasses.replace(floors[1], level=2)
    building, _ = convert_floors_with_findings([*floors, third], "T", "t1")
    assert len(building["vertical_connectors"]) == 6
    assert all(len(c["floor_ids"]) == 3 for c in building["vertical_connectors"])
    assert "connector_missing_stop" not in codes(validate(building))


def test_levels_with_a_gap_link_the_floors_next_to_each_other_in_the_building():
    floors = floors_of(PROC, levels=(0, 1), keep_names=True)
    floors = [floors[0], dataclasses.replace(floors[1], level=2)]
    building, _ = convert_floors_with_findings(floors, "T", "t1")
    assert len(building["vertical_connectors"]) == 6
    assert "connector_missing_stop" not in codes(validate(building))


def test_duplicate_refs_and_random_hints_never_crash_or_break_the_connectors():
    rng = random.Random(7)
    base = floors_of(PROC, keep_names=True)
    for _ in range(25):
        floors = []
        for level in (0, 1, 2):
            source = base[level % 2]
            rooms = []
            for room in source.extraction.rooms:
                name = rng.choice([None, "Stair", "Lift", "stair hall", "Office", "Aufzug 1", room.name])
                rooms.append(dataclasses.replace(room, ref=rng.choice([room.ref, "X", "X", None]), name=name))
            rng.shuffle(rooms)
            extraction = dataclasses.replace(source.extraction, rooms=rooms[: rng.randint(0, len(rooms))])
            floors.append(FloorInput(level, extraction, source.scale))
        rng.shuffle(floors)
        try:
            building, _ = convert_floors_with_findings(floors, "T", "t1")
        except ValueError:
            continue  # nothing usable at all is the one allowed refusal
        found = validate(building)
        assert "building_invalid" not in codes(found) and "connector_missing_stop" not in codes(found)
        spaces = {s["id"]: s for s in building["spaces"]}
        for connector in building["vertical_connectors"]:
            assert len(set(connector["floor_ids"])) == len(connector["floor_ids"]) >= 2
            assert all(
                spaces[s]["floor_id"] == f for s, f in zip(connector["space_ids"], connector["floor_ids"], strict=True)
            )
        relink_connectors(building, Collector())  # linking again changes nothing
        again = describe(validate(building))
        assert "building_invalid" not in again


# ---------- one floor: nothing is retyped from words or colour ----------


def test_single_floor_named_lobbies_halls_and_motor_rooms_stay_what_they_are():
    case = floor_case(PROC, 0)
    names = {
        "0.18": ("Elevator lobby", "hall", "lobby"),
        "0.02": ("Stair hall", "room", "lobby"),
        "0.03": ("Lift motor room", "room", "generic_room"),
        "0.06": (None, "room", "generic_room"),
    }
    rooms = []
    for room in strip_types(case.extraction, keep_names=True, fill=True).rooms:
        if room.ref in names:
            name, kind, room_type = names[room.ref]
            room = dataclasses.replace(
                room, name=name, type=kind, room_type=room_type, fill="orange" if not name else None
            )
        rooms.append(room)
    building, findings = convert_floors_with_findings(
        [FloorInput(0, dataclasses.replace(case.extraction, rooms=rooms), case.scale)], "T", "t1"
    )
    by_ref = {s["ref"]: s for s in building["spaces"]}
    assert by_ref["0.18"]["type"] == "hall" and by_ref["0.02"]["type"] == "room" and by_ref["0.03"]["type"] == "room"
    assert by_ref["0.06"]["type"] == "room"  # an orange room alone on one floor is not a stair
    assert "connector_typed_by_hint" not in codes(findings)
    assert "0.18" in level4_tools.entrance_candidates(building)  # the hall is still offered as the entrance


@pytest.mark.parametrize(
    "model_type,room_type,name",
    [
        ("hall", "lobby", "Elevator lobby"),
        ("room", "lobby", "Stair hall"),
        ("room", "generic_room", "Lift motor room"),
        ("corridor", "generic_room", "Stairs"),
        ("room", "generic_room", "Lifting room"),
    ],
)
def test_several_floors_do_not_retype_these_either(model_type, room_type, name):
    floors = []
    for level in (0, 1):
        case = floor_case(PROC, level)
        rooms = [
            dataclasses.replace(r, type=model_type, room_type=room_type, name=name) if r.ref in ("0.18", "1.18") else r
            for r in strip_types(case.extraction, keep_names=False).rooms
        ]
        floors.append(FloorInput(level, dataclasses.replace(case.extraction, rooms=rooms), case.scale))
    building, _ = convert_floors_with_findings(floors, "T", "t1")
    room = next(s for s in building["spaces"] if s["ref"] == "0.18")
    assert room["type"] == model_type


def test_a_stairs_and_lift_room_gets_both_connectors_and_routes_step_free():
    from building_agent import routing

    floors = floors_of(PROC, keep_names=False)
    for floor in floors:
        for index, room in enumerate(floor.extraction.rooms):
            if room.ref in ("0.04", "1.04"):
                floor.extraction.rooms[index] = dataclasses.replace(room, name="Stairs and Lift")
    building, _ = convert_floors_with_findings(floors, "T", "t1")
    both = [c for c in building["vertical_connectors"] if c["name"] == "Stairs and Lift"]
    assert sorted(c["kind"] for c in both) == ["lift", "stairs"]
    assert both[0]["space_ids"] == both[1]["space_ids"]
    spaces = {s["ref"]: s["id"] for s in building["spaces"]}
    result = routing.route(BuildingMap(building), spaces["0.06"], spaces["1.06"], step_free=True)
    assert result.length_m > 0
