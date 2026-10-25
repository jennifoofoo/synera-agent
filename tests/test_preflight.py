"""Preflight: real buildings from each source pass without FAIL, deliberately broken copies are flagged."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from building_agent import preflight

DATA = Path("data")


def _first_of(prefix: str) -> Path:
    found = sorted(path.parent for path in DATA.glob(f"*/{prefix}*/building.json"))
    if not found:
        pytest.skip(f"no {prefix} building in data/")
    return found[0]


SOURCES = ["proc-campus", "proc-factory", "osm-way", "resplan", "swiss-"]


def _levels(findings, level):
    return [f for f in findings if f.level == level]


@pytest.mark.parametrize("prefix", SOURCES)
def test_real_buildings_have_no_fail(prefix):
    findings = preflight.run(_first_of(prefix), DATA)
    assert not _levels(findings, preflight.FAIL), preflight.render(findings)
    assert any(f.check.startswith("kind:") for f in findings)


def _copy(tmp_path: Path) -> tuple[Path, dict]:
    target = tmp_path / "broken"
    shutil.copytree(_first_of("proc-campus"), target)
    return target, json.loads((target / "building.json").read_text(encoding="utf-8"))


def _write(directory: Path, building: dict) -> None:
    (directory / "building.json").write_text(json.dumps(building), encoding="utf-8")


def _messages(findings, level, check=None):
    return [f for f in findings if f.level == level and (check is None or f.check == check)]


def test_missing_key_fails(tmp_path):
    directory, building = _copy(tmp_path)
    del building["assets"]
    _write(directory, building)
    findings = preflight.run(directory, DATA)
    assert _messages(findings, preflight.FAIL, "loads")[0].ids == ["assets"]
    assert not any(f.check.startswith("kind:") for f in findings)


def test_dangling_opening_fails(tmp_path):
    directory, building = _copy(tmp_path)
    building["openings"][0]["space_ids"] = [building["openings"][0]["space_ids"][0], "no-such-space"]
    _write(directory, building)
    findings = preflight.run(directory, DATA)
    assert any("no-such-space" in i for f in _messages(findings, preflight.FAIL, "refs") for i in f.ids)


def test_duplicate_id_fails(tmp_path):
    directory, building = _copy(tmp_path)
    building["spaces"].append(dict(building["spaces"][0]))
    _write(directory, building)
    assert _messages(preflight.run(directory, DATA), preflight.FAIL, "ids")


def test_invalid_polygon_is_warned(tmp_path):
    directory, building = _copy(tmp_path)
    bowtie = [[0, 0], [4, 4], [4, 0], [0, 4]]
    building["spaces"][0]["polygon"] = bowtie
    _write(directory, building)
    findings = preflight.run(directory, DATA)
    ids = [i for f in findings if f.check == "geometry" and f.level in (preflight.WARN, preflight.FAIL) for i in f.ids]
    assert building["spaces"][0]["id"] in ids


def test_zero_area_polygon_fails(tmp_path):
    directory, building = _copy(tmp_path)
    building["spaces"][0]["polygon"] = [[0, 0], [1, 1], [2, 2]]
    _write(directory, building)
    assert _messages(preflight.run(directory, DATA), preflight.FAIL, "geometry")


def test_unknown_room_type_is_warned(tmp_path):
    directory, building = _copy(tmp_path)
    building["spaces"][0]["room_type"] = "forklift_aisle"
    building["assets"][0]["type"] = "agv_robot"
    _write(directory, building)
    warned = _messages(preflight.run(directory, DATA), preflight.WARN, "vocabulary")
    values = {value for f in warned for value in f.ids}
    assert {"forklift_aisle", "agv_robot"} <= values


def test_questions_file_is_counted(tmp_path):
    directory, _ = _copy(tmp_path)
    (directory / "questions.jsonl").write_text(
        '{"id": "q1", "question": "How big?", "kind": "floor_area_total"}\n'
        '{"id": "q2", "question": "Odd?", "kind": "teleport"}\n',
        encoding="utf-8",
    )
    findings = preflight.run(directory, DATA)
    assert any("floor_area_total=1" in f.message for f in findings if f.check == "questions")
    assert _messages(findings, preflight.WARN, "questions")[0].ids == ["teleport"]


def test_cli_json_and_exit_code(tmp_path):
    directory, building = _copy(tmp_path)
    ok = subprocess.run(
        [sys.executable, "scripts/preflight.py", str(_first_of("proc-campus")), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0
    assert json.loads(ok.stdout)["status"] in ("OK", "WARN")
    del building["floors"]
    _write(directory, building)
    bad = subprocess.run(
        [sys.executable, "scripts/preflight.py", str(directory), "--json"], check=False, capture_output=True, text=True
    )
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["status"] == "FAIL"


# ---------- plausibility ----------


def _plausibility(findings):
    return [f for f in findings if f.check == "plausibility" and f.level == preflight.WARN]


def _ids(findings):
    return {i for f in _plausibility(findings) for i in f.ids}


def test_plausibility_flags_absurd_dimensions_without_changing_data(tmp_path):
    directory, building = _copy(tmp_path)
    doors = [o for o in building["openings"] if o["kind"] == "door"][:3]
    for opening, width in zip(doors, (500.0, 0.0, float("nan")), strict=True):
        opening["width_m"] = width
    room = building["spaces"][0]
    room["area_m2"] = -12.0
    _write(directory, building)
    before = (directory / "building.json").read_bytes()
    findings = preflight.run(directory, DATA)
    assert {doors[0]["id"], doors[1]["id"], doors[2]["id"], room["id"]} <= _ids(findings)
    assert not [f for f in _levels(findings, preflight.FAIL) if f.check == "plausibility"]
    assert (directory / "building.json").read_bytes() == before


@pytest.mark.parametrize("prefix", SOURCES)
def test_real_buildings_have_no_plausibility_warning(prefix):
    assert not _plausibility(preflight.run(_first_of(prefix), DATA))


def test_all_kit_buildings_have_no_plausibility_warning():
    from starter_agent.building_map import BuildingMap

    dirs = sorted(path.parent for path in DATA.glob("*/*/building.json"))
    if not dirs:
        pytest.skip("no data/")
    for directory in dirs:
        found = [f for f in preflight.check_plausibility(BuildingMap.load(directory)) if f.level != preflight.OK]
        assert not found, directory.name
