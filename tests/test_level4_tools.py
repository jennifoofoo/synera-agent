"""Offline tests of the Level 4 conversation tools. The vision call is replaced by an artificial extraction of a
real dev floor, so no API key and no network are needed."""

import json
import os
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError
from shapely.geometry import Polygon

from building_agent.guide_tools import GuideState
from building_agent.level4 import tools as level4_tools
from building_agent.level4.extract import ExtractResult
from building_agent.level4.schema import Extraction
from building_agent.level4.tools import BMHolder, make_level4_tools
from starter_agent.building_map import BuildingMap
from tests.level4_helpers import floor_case, load_building

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64
BUILDING, LEVEL = "resplan-439", 0


class Rig:
    def __init__(self, tmp_path: Path, monkeypatch, case=None, bar: bool = False):
        self.case = case or floor_case(BUILDING, LEVEL)
        self.uploads = tmp_path / "uploads"
        self.uploads.mkdir()
        (self.uploads / "plan.png").write_bytes(PNG)
        self.calls = 0
        self.saved: list[Path] = []
        extraction = self.case.extraction
        if bar:
            extraction.scale_bar_px, extraction.scale_bar_m = 100.0, 100.0 * self.case.scale.metres_per_px

        def fake_extract(path, client=None, allowed_root=None, **kwargs):
            self.calls += 1
            return ExtractResult(extraction, 1000, 2000, 1.5, 0.022)

        monkeypatch.setattr(level4_tools, "extract_floor", fake_extract)
        xs = [x for s in self.case.truth["spaces"] for x, _ in s["polygon"]]
        self.width_m = max(xs) - min(xs)
        self.holder = BMHolder(BuildingMap(load_building(BUILDING)))
        self.first_map = self.holder.bm
        self.state = GuideState()
        self.buildings = tmp_path / "buildings"
        made = make_level4_tools(
            self.holder, tmp_path / "out", self.state, self.saved.append, self.uploads, self.buildings
        )
        self.tools = {tool.name: tool for tool in made}

    def turn(self) -> None:
        self.state.begin_turn()

    def call(self, name: str, **kwargs) -> dict:
        return json.loads(self.tools[name](**kwargs))

    def build(self, **kwargs) -> dict:
        args = {"image_path": "plan.png", "level": LEVEL, "known_length_m": self.width_m}
        return self.call("build_from_plan", **{**args, **kwargs})

    @property
    def draft(self):
        return self.state.level4

    def pairs(self) -> list[tuple[str, str]]:
        return [
            (o["space_ids"][0], o["space_ids"][1])
            for o in self.draft.building["openings"]
            if "outside" not in o["space_ids"]
        ]

    def show_card(self) -> dict:
        self.turn()
        card = self.call("preview_draft")
        self.turn()
        return card

    def confirmed_save(self, reply: str = "ja", **kwargs) -> dict:
        self.show_card()
        return self.call("save_building", confirmed=True, user_reply=reply, **kwargs)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    return Rig(tmp_path, monkeypatch)


def area(building: dict) -> float:
    return sum(Polygon(s["polygon"]).area for s in building["spaces"])


# ---------- build ----------


def test_build_with_known_length_makes_a_draft_not_the_active_map(rig):
    summary = rig.build()
    assert summary["rooms"] == len(rig.case.truth["spaces"])
    assert summary["entrances"] >= 1
    assert summary["scale_source"] == "known_length"
    assert "problems" in summary
    assert rig.holder.bm is rig.first_map and not rig.saved
    assert not rig.buildings.exists()


def test_build_without_scale_asks_for_one_and_reuses_the_reading(rig):
    with pytest.raises(ToolError, match="length they know"):
        rig.build(known_length_m=None)
    assert rig.draft.building is None
    rig.build()
    assert rig.calls == 1


def test_scale_bar_is_used_when_printed(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, bar=True)
    assert rig.build(known_length_m=None)["scale_source"] == "scale_bar"


def test_second_floor_is_added_to_the_same_draft(rig):
    rig.build()
    rig.build(level=1)
    assert [f["level"] for f in rig.draft.building["floors"]] == [0, 1]


# ---------- fixes ----------


def test_add_and_remove_door(rig):
    rig.build()
    first, second = rig.pairs()[0]
    removed = rig.call("fix_draft", action="remove_door", ref=first, other_ref=second)
    assert "removed" in removed["done"]
    assert (first, second) not in rig.pairs()
    added = rig.call("fix_draft", action="add_door", ref=first, other_ref=second)
    assert "added" in added["done"]
    with pytest.raises(ToolError, match="already have a door"):
        rig.call("fix_draft", action="add_door", ref=first, other_ref=second)
    with pytest.raises(ToolError, match="No room"):
        rig.call("fix_draft", action="add_door", ref=first, other_ref="nowhere")


def test_remove_missing_door_and_bad_action(rig):
    rig.build()
    first, second = rig.pairs()[0]
    rig.call("fix_draft", action="remove_door", ref=first, other_ref=second)
    with pytest.raises(ToolError, match="no door"):
        rig.call("fix_draft", action="remove_door", ref=first, other_ref=second)
    with pytest.raises(ToolError, match="action must be"):
        rig.call("fix_draft", action="explode")


def test_set_room_type(rig):
    rig.build()
    space = rig.draft.building["spaces"][0]
    rig.call("fix_draft", action="set_room_type", ref=space["id"], room_type="Stair Well")
    assert rig.draft.building["spaces"][0]["room_type"] == "stair_well"
    with pytest.raises(ToolError):
        rig.call("fix_draft", action="set_room_type", ref=space["id"], room_type="no way!")


def test_set_scale_reconverts_and_keeps_fixes(rig):
    rig.build()
    first, second = rig.pairs()[0]
    rig.call("fix_draft", action="remove_door", ref=first, other_ref=second)
    before = area(rig.draft.building)
    rig.call("fix_draft", action="set_scale", known_length_m=rig.width_m * 2)
    assert area(rig.draft.building) == pytest.approx(before * 4, rel=0.02)
    assert (first, second) not in rig.pairs()
    assert rig.calls == 1


# ---------- card and saving ----------


def test_preview_card_wording(rig):
    rig.build()
    card = rig.call("preview_draft")
    assert card["can be saved"] is True
    assert "nothing saved" in card["status"]
    assert card["I understood"][0]["rooms"] == len(rig.case.truth["spaces"])
    assert card["problems found"] == "No problems found."


def test_save_only_after_card_and_clear_yes_in_the_next_message(rig):
    rig.build()
    rig.turn()
    with pytest.raises(ToolError, match="No card"):
        rig.call("save_building", confirmed=True, user_reply="ja")
    rig.call("preview_draft")
    with pytest.raises(ToolError, match="Ask the person first"):
        rig.call("save_building", confirmed=True, user_reply="ja")
    rig.turn()
    result = rig.call("save_building", confirmed=True, user_reply="Ja, bitte")
    assert result["saved"] is True
    path = Path(result["path"])
    assert path == rig.buildings / rig.draft.building_id / "building.json"
    assert rig.saved == [path]
    assert rig.holder.bm is not rig.first_map


def test_saved_building_loads_and_routes(rig):
    rig.build()
    result = rig.confirmed_save("yes")
    loaded = BuildingMap.load(Path(result["path"]))
    assert rig.holder.bm.data == loaded.data
    ids = sorted(loaded.spaces)
    assert all(loaded.route(ids[0], other).length_m > 0 for other in ids[1:4])


@pytest.mark.parametrize("reply", ["mach einfach", "ok whatever", "ja aber nur wenn", "ja ja", "vielleicht", ""])
def test_unclear_replies_do_not_save(rig, reply):
    rig.build()
    rig.show_card()
    with pytest.raises(ToolError, match="not a clear yes"):
        rig.call("save_building", confirmed=True, user_reply=reply)
    assert not rig.saved
    assert rig.holder.bm is rig.first_map


def test_no_answer_keeps_the_draft(rig):
    rig.build()
    rig.show_card()
    assert rig.call("save_building", confirmed=False, user_reply="nein")["saved"] is False
    assert rig.draft.building is not None and not rig.saved


def test_stale_card_expires(rig):
    rig.build()
    rig.show_card()
    rig.turn()
    with pytest.raises(ToolError, match="out of date"):
        rig.call("save_building", confirmed=True, user_reply="ja")
    assert not rig.saved


def test_a_fix_after_the_card_invalidates_it(rig):
    rig.build()
    rig.turn()
    rig.call("preview_draft")
    first, second = rig.pairs()[0]
    rig.call("fix_draft", action="remove_door", ref=first, other_ref=second)
    rig.turn()
    with pytest.raises(ToolError, match="No card"):
        rig.call("save_building", confirmed=True, user_reply="ja")


def test_card_is_single_use(rig):
    rig.build()
    rig.confirmed_save("ja")
    with pytest.raises(ToolError):
        rig.call("save_building", confirmed=True, user_reply="ja")


def test_errors_block_saving_unless_explicitly_accepted(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, case=floor_case(BUILDING, LEVEL, drop_doors=1.0))
    rig.build()
    rig.turn()
    card = rig.call("preview_draft")
    assert card["can be saved"] is False and "saving blocked" in card
    rig.turn()
    with pytest.raises(ToolError, match="block saving"):
        rig.call("save_building", confirmed=True, user_reply="ja")
    rig.show_card()
    with pytest.raises(ToolError, match="block saving"):
        rig.call("save_building", confirmed=True, user_reply="ja", accept_problems=True)
    rig.show_card()
    result = rig.call("save_building", confirmed=True, user_reply="ja, trotzdem speichern", accept_problems=True)
    assert result["saved"] is True and result["accepted_problems"]


# ---------- safety ----------


def test_paths_outside_the_upload_folder_and_wrong_types_are_rejected(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    holder = BMHolder(BuildingMap(load_building(BUILDING)))
    made = make_level4_tools(holder, tmp_path / "out", GuideState(), None, uploads, tmp_path / "b")
    build = next(tool for tool in made if tool.name == "build_from_plan")
    (tmp_path / "secret.png").write_bytes(PNG)
    (uploads / "link.png").symlink_to(tmp_path / "secret.png")
    (uploads / "tool.exe").write_bytes(b"MZ" + b"0" * 100)
    (uploads / "fake.png").write_bytes(b"MZ" + b"0" * 100)
    bad_paths = ["../secret.png", str(tmp_path / "secret.png"), "link.png", "tool.exe", "fake.png", "missing.png"]
    for bad in [*bad_paths, "/etc/passwd"]:
        with pytest.raises(ToolError):
            build(image_path=bad, known_length_m=10)


def test_atomic_write_leaves_no_partial_file(rig, monkeypatch):
    rig.build()
    rig.show_card()

    def boom(*args):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(ToolError, match="Nothing was changed"):
        rig.call("save_building", confirmed=True, user_reply="ja")
    assert not any(p.is_file() for p in rig.buildings.rglob("*"))
    assert rig.holder.bm is rig.first_map and not rig.saved


# ---------- fuzz ----------


@pytest.mark.parametrize("length", [0, -3, float("nan"), float("inf")])
def test_unusable_scales_are_tool_errors(rig, length):
    with pytest.raises(ToolError):
        rig.build(known_length_m=length)
    assert rig.draft.building is None


def test_huge_scale_is_flagged_and_blocks_saving(rig):
    rig.build(known_length_m=5e6)
    rig.turn()
    assert "unlikely size" in rig.call("preview_draft")["problems found"]
    rig.turn()
    with pytest.raises(ToolError, match="block saving"):
        rig.call("save_building", confirmed=True, user_reply="ja")


def test_empty_extraction_is_a_tool_error(tmp_path, monkeypatch):
    case = floor_case(BUILDING, LEVEL)
    case.extraction = Extraction(100, 100, [], [])
    rig = Rig(tmp_path, monkeypatch, case=case)
    with pytest.raises(ToolError):
        rig.build()
    with pytest.raises(ToolError, match="no draft"):
        rig.call("preview_draft")


def test_tools_without_a_draft_are_tool_errors(rig):
    calls = [
        ("preview_draft", {}),
        ("fix_draft", {"action": "add_door"}),
        ("save_building", {"confirmed": True, "user_reply": "ja"}),
    ]
    for name, args in calls:
        with pytest.raises(ToolError):
            rig.tools[name](**args)
