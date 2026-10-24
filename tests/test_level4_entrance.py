"""Level 4: entrances (add_entrance, the question when none exists), save rules and draft reset. Offline."""

import json
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError

from building_agent.entrance_distance import distances_to_exit
from building_agent.level4.convert import FloorInput, convert_floors
from building_agent.level4.schema import ExtractedDoor, ExtractedRoom, Extraction, Scale
from building_agent.level4.tools import apply_fix
from building_agent.level4.validate import validate
from starter_agent.building_map import OUTSIDE, BuildingMap
from tests.level4_helpers import floor_case
from tests.test_level4_tools import BUILDING, LEVEL, Rig


def no_entrance_case():
    case = floor_case(BUILDING, LEVEL)
    case.extraction.doors = [d for d in case.extraction.doors if OUTSIDE not in d.rooms]
    return case


@pytest.fixture
def bare(tmp_path, monkeypatch):
    return Rig(tmp_path, monkeypatch, case=no_entrance_case())


@pytest.fixture
def rig_clean(tmp_path, monkeypatch):
    return Rig(tmp_path, monkeypatch)


def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def entrances(rig) -> list[dict]:
    return [o for o in rig.draft.building["openings"] if OUTSIDE in o["space_ids"]]


def codes(rig) -> set[str]:
    return {f.code for f in rig.draft.findings.items}


def west_room(rig) -> dict:
    return min(rig.draft.building["spaces"], key=lambda s: min(x for x, _ in s["polygon"]))


def test_draft_without_entrance_asks_which_room_and_lists_candidates(bare):
    summary = bare.build()
    assert summary["entrances"] == 0
    question = summary["question"]
    assert "which room" in question and "add_entrance" in question
    listed = question.split("Likely rooms: ")[1].rstrip(".").split(", ")
    assert 1 <= len(listed) <= 5
    bare.turn()
    card = bare.call("preview_draft")
    assert card["question"] == question
    assert "no entrance" in card["problems found"]


def test_candidates_put_lobbies_and_halls_first(tmp_path, monkeypatch):
    case = no_entrance_case()
    case.extraction.rooms[3].room_type = "lobby"
    rig = Rig(tmp_path, monkeypatch, case=case)
    question = rig.build()["question"]
    first = question.split("Likely rooms: ")[1].split(", ")[0].rstrip(".")
    lobby = next(s for s in rig.draft.building["spaces"] if s["room_type"] == "lobby")
    assert first == (lobby["ref"] or lobby["name"] or lobby["id"])


def test_saving_without_entrance_needs_accept_problems(bare):
    bare.build()
    bare.show_card()
    with pytest.raises(ToolError, match="block saving"):
        bare.call("save_building", confirmed=True, user_reply="ja")
    bare.show_card()
    with pytest.raises(ToolError, match="block saving"):
        bare.call("save_building", confirmed=True, user_reply="ja", accept_problems=True)


def test_add_entrance_default_uses_the_longest_outside_wall_and_clears_the_finding(bare):
    bare.build()
    assert "no_entrance" in codes(bare)
    room = bare.draft.building["spaces"][0]
    done = bare.call("fix_draft", action="add_entrance", ref=room["ref"] or room["id"])
    assert "Entrance added" in done["done"] and "question" not in done
    (entrance,) = entrances(bare)
    assert entrance["kind"] == "entrance" and entrance["step_free"] is True
    assert entrance["space_ids"] == [room["id"], OUTSIDE]
    assert "no_entrance" not in codes(bare)


def test_add_entrance_by_side(bare):
    bare.build()
    spaces = bare.draft.building["spaces"]
    xs = [x for s in spaces for x, _ in s["polygon"]]
    ys = [y for s in spaces for _, y in s["polygon"]]
    west = west_room(bare)
    bare.call("fix_draft", action="add_entrance", ref=west["id"], side="west", steps=True)
    (entrance,) = entrances(bare)
    assert entrance["position"][0] == pytest.approx(min(xs), abs=0.01)
    assert entrance["step_free"] is False
    north = max(spaces, key=lambda s: max(y for _, y in s["polygon"]))
    bare.call("fix_draft", action="add_entrance", ref=north["id"], side="north")
    assert max(o["position"][1] for o in entrances(bare)) == pytest.approx(max(ys), abs=0.01)
    with pytest.raises(ToolError, match="side must be"):
        bare.call("fix_draft", action="add_entrance", ref=north["id"], side="up")


def test_add_entrance_on_a_side_without_outside_wall_is_an_error():
    rooms = [ExtractedRoom("a", rect(0, 0, 100, 100), ref="a"), ExtractedRoom("b", rect(100, 0, 200, 100), ref="b")]
    building = convert_floors(
        [FloorInput(0, Extraction(200, 100, rooms, []), Scale(0.05, "known_length", "t"))], "T", "t1"
    )
    with pytest.raises(ToolError, match="no outside wall on the east side"):
        apply_fix(building, ("add_entrance", "a", None, "east", None, True))
    apply_fix(building, ("add_entrance", "a", None, "west", None, True))
    assert building["openings"][0]["position"][0] == pytest.approx(0.0, abs=0.01)


def test_add_entrance_nearest_point_in_pixels(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    first = Rig(tmp_path / "a", monkeypatch, case=no_entrance_case())
    first.build()
    west = west_room(first)
    first.call("fix_draft", action="add_entrance", ref=west["id"], side="west")
    wanted = entrances(first)[0]["position"]
    scale = first.case.scale.metres_per_px
    # a pixel 6 px outside the wall at that spot must give the same entrance
    point = [wanted[0] / scale - 6, first.case.extraction.height_px - wanted[1] / scale]
    (tmp_path / "b").mkdir()
    second = Rig(tmp_path / "b", monkeypatch, case=no_entrance_case())
    second.build()
    second.call("fix_draft", action="add_entrance", ref=west["name"], point_px=point)
    assert entrances(second)[0]["position"] == pytest.approx(wanted, abs=0.35)
    with pytest.raises(ToolError, match="point_px"):
        second.call("fix_draft", action="add_entrance", ref=west["name"], point_px=["a", "b"])


def test_add_entrance_unknown_room_missing_ref_and_already_has_one(bare):
    bare.build()
    with pytest.raises(ToolError, match="No room"):
        bare.call("fix_draft", action="add_entrance", ref="nowhere")
    with pytest.raises(ToolError, match="needs ref"):
        bare.call("fix_draft", action="add_entrance")
    room = bare.draft.building["spaces"][0]["id"]
    bare.call("fix_draft", action="add_entrance", ref=room)
    with pytest.raises(ToolError, match="already has an entrance"):
        bare.call("fix_draft", action="add_entrance", ref=room)


def test_add_entrance_to_an_interior_room_is_a_clear_error():
    cells = [(x, y) for y in (0, 100, 200) for x in (0, 100, 200)]
    rooms = [
        ExtractedRoom(str(i), [[x, y], [x + 100, y], [x + 100, y + 100], [x, y + 100]], ref=str(i))
        for i, (x, y) in enumerate(cells)
    ]
    extraction = Extraction(300, 300, rooms, [ExtractedDoor(("0", "outside"), [0, 250], kind="entrance")])
    building = convert_floors([FloorInput(0, extraction, Scale(0.05, "known_length", "t"))], "T", "t1")
    with pytest.raises(ToolError, match="no outside wall"):
        apply_fix(building, ("add_entrance", "4", None, None, None, True))


def test_after_add_entrance_it_saves_without_accepting_problems_and_routes_from_outside(bare):
    bare.build()
    bare.call("fix_draft", action="add_entrance", ref=bare.draft.building["spaces"][0]["id"])
    assert "no_entrance" not in {f.code for f in validate(bare.draft.building).items}
    result = bare.confirmed_save("ja")
    assert result["saved"] is True and result["entrances"] == 1
    loaded = BuildingMap.load(Path(result["path"]))
    lengths = distances_to_exit(loaded, loaded.graph(step_free=False))
    assert all(space_id in lengths for space_id in loaded.spaces)


def test_entrance_fix_survives_a_rescale(bare):
    bare.build()
    bare.call("fix_draft", action="add_entrance", ref=bare.draft.building["spaces"][0]["id"], side="west")
    bare.call("fix_draft", action="set_scale", known_length_m=bare.width_m * 2)
    assert len(entrances(bare)) == 1 and "no_entrance" not in codes(bare)


# ---------- save rules ----------


def test_success_message_and_draft_reset_after_save(rig_clean):
    rig = rig_clean
    rig.build()
    space = rig.draft.building["spaces"][0]
    original_type = space["room_type"]
    rig.call("fix_draft", action="set_room_type", ref=space["id"], room_type="kitchen")
    old_id = rig.draft.building_id
    result = rig.confirmed_save("ja")
    assert result["note"].endswith("The building has changed. Ask your question again in your next message.")
    assert rig.draft.building is None and rig.draft.fixes == [] and rig.draft.building_id != old_id
    saved = Path(result["path"]).read_text(encoding="utf-8")
    rig.turn()
    rig.build()  # a second plan starts clean, without the old fix
    assert rig.draft.building_id != old_id and rig.draft.building["spaces"][0]["room_type"] == original_type
    assert Path(result["path"]).read_text(encoding="utf-8") == saved
    rig.confirmed_save("ja")
    assert len({p.parent.name for p in rig.buildings.rglob("building.json")}) == 2


def poor_card(rig) -> dict:
    """These floors have no doors, a poor reading: the card needs 'build it anyway' first."""
    rig.turn()
    card = rig.call("preview_draft", user_reply="build it anyway")
    rig.turn()
    return card


@pytest.mark.parametrize(
    "reply", ["trotzdem speichern", "save it anyway", "Nevertheless, save it anyway", "speichern, anyway"]
)
def test_accept_path_needs_no_yes_word(tmp_path, monkeypatch, reply):
    rig = Rig(tmp_path, monkeypatch, case=floor_case(BUILDING, LEVEL, drop_doors=1.0))
    rig.build()
    assert "save it anyway" in poor_card(rig)["saving blocked"]
    result = rig.call("save_building", confirmed=True, user_reply=reply, accept_problems=True)
    assert result["saved"] is True and result["accepted_problems"]


@pytest.mark.parametrize("reply", ["nein, trotzdem nicht", "trotzdem lieber nicht", "anyway, but no", "ja"])
def test_accept_path_still_refuses_negations_and_plain_yes(tmp_path, monkeypatch, reply):
    rig = Rig(tmp_path, monkeypatch, case=floor_case(BUILDING, LEVEL, drop_doors=1.0))
    rig.build()
    poor_card(rig)
    with pytest.raises(ToolError):
        rig.call("save_building", confirmed=True, user_reply=reply, accept_problems=True)
    assert not rig.saved


def test_trotzdem_without_blocking_problems_is_not_a_yes(rig_clean):
    rig_clean.build()
    rig_clean.show_card()
    with pytest.raises(ToolError, match="not a clear yes"):
        rig_clean.call("save_building", confirmed=True, user_reply="trotzdem", accept_problems=True)


def test_add_remove_add_door_keeps_both_doors_after_save_and_reload(rig_clean):
    rig = rig_clean
    rig.build()
    p1, p2 = rig.pairs()[0], rig.pairs()[1]
    before = len(rig.draft.building["openings"])
    for pair in (p1, p2):
        rig.call("fix_draft", action="remove_door", ref=pair[0], other_ref=pair[1])
        rig.call("fix_draft", action="add_door", ref=pair[0], other_ref=pair[1])
    ids = [o["id"] for o in rig.draft.building["openings"]]
    assert len(ids) == len(set(ids)) == before
    result = rig.confirmed_save("ja")
    loaded = BuildingMap.load(Path(result["path"]))
    assert len(loaded.openings) == before
    pairs = {frozenset(o["space_ids"]) for o in loaded.openings.values()}
    assert frozenset(p1) in pairs and frozenset(p2) in pairs
    assert json.loads(Path(result["path"]).read_text(encoding="utf-8"))["openings"]
