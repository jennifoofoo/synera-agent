"""Level 4: the judge route metric (our door-to-door route on the extracted building, measured on the original)."""

import pytest

from building_agent.level4.convert import FloorInput, convert_floors_with_findings
from tests.level4_helpers import floor_case, measure

FLOORS = [("proc-campus-dev-000", 0), ("resplan-439", 0), ("swiss-31", 1)]


def converted_for(case):
    return convert_floors_with_findings([FloorInput(case.level, case.extraction, case.scale)], "Judge", "j1")[0]


@pytest.mark.parametrize(("building_id", "level"), FLOORS)
def test_judge_metric_without_noise_is_near_zero_and_valid(building_id, level):
    case = floor_case(building_id, level)
    result = measure(case, converted_for(case))
    assert result["judge_pairs"] > 0
    assert result["judge_invalid"] == 0
    assert result["judge_no_route"] == 0
    assert result["judge_err_median"] < 0.01
    assert result["judge_full_share"] >= 0.95


def test_judge_metric_counts_a_missing_door_as_no_route():
    case = floor_case("resplan-439", 0, drop_doors=1.0)
    result = measure(case, converted_for(case))
    assert result["judge_no_route"] == result["judge_pairs"] > 0
    assert result["judge_err_mean"] == 1.0
