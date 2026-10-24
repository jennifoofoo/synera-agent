import json
from pathlib import Path

from building_agent.asset_catalog import ASSET_CATALOG
from building_agent.asset_knowledge import ASSET_KNOWLEDGE

DATA = Path("data")
HARMLESS_FURNITURE_WITH_NOTE = {"chemical_cabinet"}


def types_in_data() -> set[str]:
    found: set[str] = set()
    for path in DATA.glob("*/*/building.json"):
        found |= {asset["type"] for asset in json.loads(path.read_text(encoding="utf-8"))["assets"]}
    return found


def test_every_type_in_the_data_has_knowledge():
    missing = types_in_data() - set(ASSET_KNOWLEDGE)
    assert not missing, f"add knowledge for new asset types: {sorted(missing)}"
    assert len(types_in_data()) == 96
    assert set(ASSET_CATALOG) == set(ASSET_KNOWLEDGE)


def test_kind_matches_catalog_category():
    for asset_type, knowledge in ASSET_KNOWLEDGE.items():
        assert knowledge.kind == ASSET_CATALOG[asset_type]["category"], asset_type


def test_summaries_are_short_plain_sentences():
    for asset_type, knowledge in ASSET_KNOWLEDGE.items():
        assert 20 <= len(knowledge.summary) <= 140, asset_type
        assert knowledge.summary.endswith(".") and "\n" not in knowledge.summary, asset_type
        assert len(knowledge.safety) <= 160, asset_type


def test_no_em_dashes_anywhere():
    for knowledge in ASSET_KNOWLEDGE.values():
        text = knowledge.summary + knowledge.safety + " ".join(knowledge.tasks)
        assert "—" not in text and "–" not in text


def test_task_phrases_are_lowercase_ascii_and_enough():
    for asset_type, knowledge in ASSET_KNOWLEDGE.items():
        assert len(knowledge.tasks) >= 3, asset_type
        assert len(set(knowledge.tasks)) == len(knowledge.tasks), f"duplicate phrase in {asset_type}"
        for phrase in knowledge.tasks:
            assert phrase == phrase.lower() and phrase.isascii(), (asset_type, phrase)


def test_safety_is_not_invented_for_harmless_types():
    for asset_type, knowledge in ASSET_KNOWLEDGE.items():
        if knowledge.kind == "furniture" and asset_type not in HARMLESS_FURNITURE_WITH_NOTE:
            assert knowledge.safety == "", asset_type
        if knowledge.kind == "fixture":
            assert knowledge.safety == "", asset_type
    for asset_type in ("welding_station", "press_brake", "waterjet_cutter", "laser_cutter", "cnc_mill", "forklift"):
        assert ASSET_KNOWLEDGE[asset_type].safety, asset_type
    for asset_type in ("chair", "desk", "plant", "printer", "whiteboard", "sofa", "bed"):
        assert ASSET_KNOWLEDGE[asset_type].safety == "", asset_type
