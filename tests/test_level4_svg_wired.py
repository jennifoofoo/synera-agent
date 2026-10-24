"""build_from_plan with a vector file (svg) next to the plan, and scale from a building.json: offline, the vision call is
replaced. Uses real kit floors (skipped without data/)."""

import json
import shutil

import pytest
from anthropic.lib.tools import ToolError

from building_agent.guide_tools import GuideState
from building_agent.level4 import tools as level4_tools
from building_agent.level4.extract import ExtractError, ExtractResult
from building_agent.level4.svg_read import read_svg
from building_agent.level4.tools import BMHolder, make_level4_tools
from starter_agent.building_map import BuildingMap
from tests.level4_helpers import DATA_DEV, floor_case, load_building

BUILDING, LEVEL = "resplan-439", 0

pytestmark = pytest.mark.skipif(not (DATA_DEV / BUILDING).exists(), reason="kit data missing (scripts/get_data.sh)")


class Rig:
    def __init__(self, tmp_path, monkeypatch, vision: bool = True, svg: bool = True):
        self.case = floor_case(BUILDING, LEVEL)
        self.uploads = tmp_path / "uploads"
        self.uploads.mkdir()
        self.source = DATA_DEV / BUILDING
        shutil.copy(self.source / f"floor_{LEVEL}.png", self.uploads / "plan.png")
        if svg:
            shutil.copy(self.source / f"floor_{LEVEL}.svg", self.uploads / "plan.svg")
        self.svg_truth = read_svg(self.source / f"floor_{LEVEL}.svg")
        self.vision_calls = 0
        extraction = self.case.extraction

        def fake_extract(path, client=None, allowed_root=None, **kwargs):
            self.vision_calls += 1
            if not vision:
                raise ExtractError("No API key.")
            return ExtractResult(extraction, 1000, 2000, 1.5, 0.022)

        monkeypatch.setattr(level4_tools, "extract_floor", fake_extract)
        xs = [x for s in self.case.truth["spaces"] for x, _ in s["polygon"]]
        self.width_m = max(xs) - min(xs)
        self.state = GuideState()
        holder = BMHolder(BuildingMap(load_building(BUILDING)))
        made = make_level4_tools(holder, tmp_path / "out", self.state, None, self.uploads, tmp_path / "b")
        self.tools = {tool.name: tool for tool in made}

    def call(self, name, **kwargs):
        return json.loads(self.tools[name](**kwargs))

    def build(self, **kwargs):
        args = {"image_path": "plan.png", "level": LEVEL, "known_length_m": self.width_m}
        return self.call("build_from_plan", **{**args, **kwargs})

    def card(self):
        self.state.begin_turn()
        return self.call("preview_draft")


def test_svg_gives_rooms_and_doors_and_the_card_says_so(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    summary = rig.build()
    assert "vector file" in summary["read_from"]
    assert summary["rooms"] == len(rig.svg_truth.rooms)
    doors = [d for d in rig.svg_truth.doors if d.kind != "entrance"]
    assert summary["doors"] + summary["entrances"] >= len(doors) - 2  # snapping may merge a twin marker
    card = rig.card()
    assert "vector file" in card["I understood"][0]["read from"]
    assert any("Read from the vector file" in note for note in card["notes"])


def test_svg_rooms_are_the_exact_outlines_with_numbers_and_names(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    rig.build()
    spaces = rig.state.level4.building["spaces"]
    refs = {s["ref"] for s in spaces if s["ref"]}
    true_refs = {s["ref"] for s in rig.case.truth["spaces"]}
    assert refs and refs <= true_refs
    assert any(s["name"] != f"Room {s['ref']}" and s["ref"] in s["name"] for s in spaces)  # type word plus number


def test_no_svg_uses_the_vision_pipeline(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, svg=False)
    summary = rig.build()
    assert "vision model" in summary["read_from"]
    assert rig.vision_calls == 1


def test_vision_failure_with_svg_still_builds_from_the_svg(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, vision=False)
    summary = rig.build()
    assert "vector file" in summary["read_from"] and summary["rooms"] == len(rig.svg_truth.rooms)
    notes = rig.card()["notes"]
    assert any("could not be read from the image" in note for note in notes)


def test_vision_failure_without_svg_is_still_an_error(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, vision=False, svg=False)
    with pytest.raises(ToolError, match="No API key"):
        rig.build()


@pytest.mark.parametrize("content", ["not an svg", "<svg width='9pt' height='9pt'></svg>", "<script>alert(1)</script>"])
def test_non_kit_svg_is_refused_cleanly(tmp_path, monkeypatch, content):
    rig = Rig(tmp_path, monkeypatch)
    (rig.uploads / "plan.svg").write_text(content, encoding="utf-8")
    summary = rig.build()
    assert "vision model" in summary["read_from"]
    assert any("not a plan in the kit's drawing style" in note for note in rig.card()["notes"])


def test_svg_with_scripts_or_links_is_refused(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    text = (rig.source / f"floor_{LEVEL}.svg").read_text(encoding="utf-8")
    (rig.uploads / "plan.svg").write_text(text.replace("</svg>", "<script>alert(1)</script></svg>"), encoding="utf-8")
    assert "vision model" in rig.build()["read_from"]


def test_svg_of_another_size_is_refused(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    other = DATA_DEV / "swiss-31" / "floor_0.svg"
    if not other.exists():
        pytest.skip("kit data missing")
    shutil.copy(other, rig.uploads / "plan.svg")
    summary = rig.build()
    assert "vision model" in summary["read_from"]
    assert any("does not match the size" in note for note in rig.card()["notes"])


def test_svg_outside_the_upload_folder_is_never_read(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, svg=False)
    outside = tmp_path / "secret.svg"
    shutil.copy(rig.source / f"floor_{LEVEL}.svg", outside)
    (rig.uploads / "plan.svg").symlink_to(outside)
    assert "vision model" in rig.build()["read_from"]


def test_plain_png_finds_the_svg_without_plain(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, svg=False)
    shutil.copy(rig.source / f"floor_{LEVEL}_plain.png", rig.uploads / "floor_0_plain.png")
    shutil.copy(rig.source / f"floor_{LEVEL}.svg", rig.uploads / "floor_0.svg")
    assert "vector file" in rig.build(image_path="floor_0_plain.png")["read_from"]


def test_confirmation_guard_is_unchanged_with_svg(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    rig.build()
    rig.card()
    with pytest.raises(ToolError, match="Ask the person first|new message|answer"):
        rig.call("save_building", confirmed=True, user_reply="ja")


# ---------- scale from building.json ----------


def px_per_m(rig) -> float:
    xs = [x for room in rig.svg_truth.rooms for x, _ in room.polygon_px]
    return (max(xs) - min(xs)) / rig.width_m


def test_scale_from_building_json_field(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    (rig.uploads / "plan.building.json").write_text(
        json.dumps({"building": {"floors": [{"level": 0, "px_per_m": px_per_m(rig)}]}}), encoding="utf-8"
    )
    summary = rig.build(known_length_m=None)
    assert summary["scale_source"] == "building_json"
    assert "building.json (building.floors[0].px_per_m" in summary["scale"]
    xs = [x for s in rig.state.level4.building["spaces"] for x, _ in s["polygon"]]
    assert max(xs) - min(xs) == pytest.approx(rig.width_m, rel=0.01)
    assert "building.json" in rig.card()["I understood"][0]["scale"]


def test_building_json_in_the_folder_is_found(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    (rig.uploads / "building.json").write_text(json.dumps({"m_per_px": 1 / px_per_m(rig)}), encoding="utf-8")
    assert rig.build(known_length_m=None)["scale_source"] == "building_json"


def test_scale_from_building_width_and_svg(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    (rig.uploads / "plan.building.json").write_text(
        json.dumps({"building": {"width_m": rig.width_m}}), encoding="utf-8"
    )
    summary = rig.build(known_length_m=None)
    assert summary["scale_source"] == "building_json"
    assert "building width" in summary["scale"] and "svg" in summary["scale"]


def test_width_without_svg_is_not_used(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, svg=False)
    (rig.uploads / "plan.building.json").write_text(
        json.dumps({"building": {"width_m": rig.width_m}}), encoding="utf-8"
    )
    with pytest.raises(ToolError, match="length they know"):
        rig.build(known_length_m=None)


def test_person_length_beats_building_json(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    (rig.uploads / "plan.building.json").write_text(json.dumps({"px_per_m": 5}), encoding="utf-8")
    assert rig.build()["scale_source"] == "known_length"


def test_bad_building_json_falls_back_to_asking(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, svg=False)
    (rig.uploads / "plan.building.json").write_text(json.dumps({"px_per_m": -4, "mpp": "x"}), encoding="utf-8")
    with pytest.raises(ToolError, match="length they know"):
        rig.build(known_length_m=None)
    (rig.uploads / "plan.building.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ToolError, match="length they know"):
        rig.build(known_length_m=None)
