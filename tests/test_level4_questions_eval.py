"""The Level 4 questions eval (scripts/level4_questions_eval.py) on one small real building: builds from the svg, asks the
labelled questions, answers same-floor questions like the label. Skipped without data/."""

import sys

import pytest

from building_agent.registry import load_kinds
from tests.level4_helpers import DATA_DEV

sys.path.insert(0, "scripts")
import level4_questions_eval as evaluation

BUILDING = "resplan-439"

pytestmark = pytest.mark.skipif(not (DATA_DEV / BUILDING).exists(), reason="kit data missing (scripts/get_data.sh)")


def test_one_building_is_built_and_asked():
    info = evaluation.building_info(DATA_DEV / BUILDING)
    result = evaluation.run_building(info, "svg", info["levels"], load_kinds())
    assert result["built"] and result["spaces"] == 8
    rows = [row for row in result["rows"] if row["status"] != "skipped"]
    assert rows and all(row["status"] in ("correct", "wrong", "unresolved", "error") for row in rows)
    routes = [row for row in rows if row["kind"] == "route"]
    assert routes and sum(row["status"] == "correct" for row in routes) >= len(routes) // 2  # same floor, exact rooms
    skipped = {row["kind"] for row in result["rows"] if row["status"] == "skipped"}
    assert skipped <= set(evaluation.SKIPPED)


def test_choose_covers_every_source_and_prefers_multi_floor():
    chosen = evaluation.choose(8)
    assert len(chosen) == 8
    assert {info["source"] for info in chosen} >= {"swiss", "osm", "proc", "resplan"}
    assert len({info["id"] for info in chosen}) == 8


def test_number_tolerance_follows_the_readme():
    assert evaluation.tolerance_ok(100.9, {"value": 100.0, "relative_tolerance": 0.01, "absolute_tolerance": 1.0})
    assert not evaluation.tolerance_ok(5, {"value": 6, "relative_tolerance": 0.0, "absolute_tolerance": 0.0})
