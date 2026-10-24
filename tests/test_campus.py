"""Campus structure and validation: every finding in plain words, no crash on bad data."""

import copy
import json
from pathlib import Path

import pytest

from building_agent.campus import (
    Campus,
    CampusBuilding,
    CampusError,
    Link,
    entrances,
    load_campus,
    make_example_campus,
    save_campus,
    validate_campus,
)
from tests.conftest import DATA, load_map

CAMPUS_A, FACTORY, RESPLAN = "proc-campus-dev-000", "proc-factory-dev-003", "resplan-439"


@pytest.fixture
def example() -> Campus:
    return make_example_campus(DATA)


def codes(campus: Campus) -> dict[str, str]:
    return {finding.code: finding.message for finding in validate_campus(campus)}


def test_entrances_lists_outside_openings_with_the_room_behind():
    found = entrances(load_map(str(DATA / "dev" / CAMPUS_A)))
    assert len(found) == 2
    first = found[0]
    assert set(first) >= {"id", "room", "space_id", "position", "step_free"}
    assert first["room"]
    assert any(not item["step_free"] for item in found)


def test_example_campus_is_clean(example):
    assert validate_campus(example) == []
    assert len(example.buildings) == 3 and len(example.links) == 2


def test_example_campus_round_trips_through_campus_json(example, tmp_path):
    path = tmp_path / "campus.json"
    save_campus(example, path)
    loaded, findings = load_campus(path)
    assert loaded == example
    assert findings.ok and not findings.items


def test_unknown_building(example):
    example.links[0].to_building = "nowhere-1"
    assert (
        "Link L1 refers to building 'nowhere-1', which is not part of the campus." in codes(example)["unknown_building"]
    )


def test_building_path_missing(example, tmp_path):
    example.buildings[0].path = tmp_path / "gone"
    assert "Building 'proc-campus-dev-000' has no folder at" in codes(example)["building_path_missing"]
    example.buildings[0].path = None
    assert "building_path_missing" in codes(example)


def test_building_without_building_json(example, tmp_path):
    example.buildings[0].path = tmp_path
    assert (
        codes(example)["building_json_missing"] == "The folder of building 'proc-campus-dev-000' has no building.json."
    )


def test_building_json_unreadable(example, tmp_path):
    (tmp_path / "building.json").write_text("{not json", encoding="utf-8")
    example.buildings[0].path = tmp_path
    assert "could not be read" in codes(example)["building_unreadable"]


def test_entrance_not_present(example):
    example.links[0].from_entrance = "no-such-door"
    assert "'no-such-door' is not present in building 'proc-campus-dev-000'" in codes(example)["entrance_not_found"]


def test_entrance_that_is_an_inner_door(example):
    inner = next(
        opening_id
        for opening_id, opening in load_map(str(DATA / "dev" / CAMPUS_A)).openings.items()
        if "outside" not in opening["space_ids"]
    )
    example.links[0].from_entrance = inner
    assert "is not an entrance (it does not lead outside)" in codes(example)["entrance_not_found"]


def test_empty_entrance(example):
    example.links[0].to_entrance = ""
    assert "names no entrance of building" in codes(example)["entrance_not_found"]


def test_link_inside_one_building(example):
    example.links[0].to_building = example.links[0].from_building
    assert codes(example)["link_within_building"] == "Link L1 connects building 'proc-campus-dev-000' to itself."


def test_same_entrance_twice_in_one_link(example):
    link = example.links[0]
    link.to_building, link.to_entrance = link.from_building, link.from_entrance
    assert "link_within_building" in codes(example)


def test_duplicate_link_ids(example):
    example.links[1].id = "L1"
    assert codes(example)["duplicate_link_id"] == "The link id 'L1' is used more than once."


def test_duplicate_building(example):
    example.buildings.append(copy.copy(example.buildings[0]))
    assert "is listed more than once" in codes(example)["duplicate_building"]


def test_duplicate_link_rows(example):
    twin = copy.copy(example.links[0])
    twin.id = "L9"
    example.links.append(twin)
    assert "Link L9 repeats another link between the same two entrances." == codes(example)["duplicate_link"]


def test_length_estimated_from_origins_on_load(example, tmp_path):
    data = example.to_dict()
    data["links"][0]["length_m"] = None
    data["links"][0]["length_estimated"] = False
    path = tmp_path / "campus.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    campus, findings = load_campus(path)
    link = campus.links[0]
    assert link.length_estimated and link.length_m > 0
    messages = [finding.message for finding in findings.items if finding.code == "length_estimated"]
    assert messages and "is an estimate" in messages[0] and "times 1.2" in messages[0]
    assert findings.ok


def test_length_missing_without_origins(example):
    example.links[0].length_m = None
    for building in example.buildings:
        building.origin = None
    assert "cannot be estimated" in codes(example)["link_length_missing"]


@pytest.mark.parametrize("length", [0, -5.0, float("nan"), float("inf")])
def test_length_not_positive(example, length):
    example.links[0].length_m = length
    assert "must be more than 0" in codes(example)["link_length_not_positive"]


def test_very_long_link_is_a_warning(example):
    example.links[0].length_m = 1e9
    assert "unusually far" in codes(example)["link_length_very_long"]


def test_step_free_conflict(example):
    step_entrance = next(item for item in entrances(load_map(str(DATA / "dev" / CAMPUS_A))) if not item["step_free"])
    link = example.links[0]
    link.from_entrance = step_entrance["id"]
    link.step_free = True
    message = codes(example)["step_free_conflict"]
    assert message.startswith("Link L1 is marked step-free, but the entrance") and "has steps" in message
    link.step_free = False
    assert "step_free_conflict" not in codes(example)


def test_building_not_connected(example):
    example.links = example.links[:1]
    assert codes(example)["building_not_connected"] == (
        "Building 'resplan-439' has no link to any other building, so it is not connected."
    )


def test_unknown_kind(example):
    example.links[0].kind = "teleport"
    assert "which is not one of walkway, bridge, tunnel" in codes(example)["unknown_kind"]


def test_bad_width(example):
    example.links[0].width_m = -1.0
    assert "link_width_invalid" in codes(example)


def test_findings_levels(example):
    example.links[0].kind = "teleport"
    example.links = example.links[:1]
    levels = {finding.code: finding.level for finding in validate_campus(example)}
    assert levels["unknown_kind"] == "error" and levels["building_not_connected"] == "warning"


def test_load_campus_missing_file_raises_campus_error(tmp_path):
    with pytest.raises(CampusError):
        load_campus(tmp_path / "nope.json")


def test_load_campus_accepts_a_folder(example, tmp_path):
    save_campus(example, tmp_path / "campus.json")
    campus, _ = load_campus(tmp_path)
    assert campus == example


def test_empty_campus_validates():
    assert validate_campus(Campus("x", "x")) == []
    assert Campus("x", "x").building("a") is None
    assert Link(id="L", from_building="a", from_entrance="b", to_building="c", to_entrance="d").kind == "walkway"
    assert CampusBuilding("a").origin is None


def test_example_does_not_write_into_data():
    before = sorted(Path("data/dev").glob(f"{CAMPUS_A}/*"))
    make_example_campus(DATA)
    assert before == sorted(Path("data/dev").glob(f"{CAMPUS_A}/*"))
    assert FACTORY and RESPLAN
