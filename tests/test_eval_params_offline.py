from building_agent.find_space import find_space
from building_agent.params_eval import (
    MISSING,
    PRICE_INPUT_PER_MTOK,
    PRICE_OUTPUT_PER_MTOK,
    classify_mismatch,
    compare_params,
    estimate_cost,
    group_mismatches,
)
from tests.conftest import labelled_questions, load_map


def errand_case():
    building_dir, question = labelled_questions("errand")[0]
    return load_map(building_dir), question["inputs"]


def test_id_matches():
    bm, inputs = errand_case()
    assert compare_params(bm, inputs, dict(inputs)) == []


def test_name_resolved_via_find_space():
    bm, _ = errand_case()
    target = next(s for s in bm.spaces.values() if "match" in find_space(bm, s["name"]))
    assert compare_params(bm, {"start": target["id"]}, {"start": target["name"]}) == []


def test_wrong_floor_is_mismatch():
    bm, inputs = errand_case()
    other = next(floor_id for floor_id in bm.floors if floor_id != inputs["floor_id"])
    got = {**inputs, "floor_id": other}
    assert compare_params(bm, inputs, got) == [("floor_id", inputs["floor_id"], other)]


def test_unknown_name_is_mismatch():
    bm, inputs = errand_case()
    got = {**inputs, "start": "no such room"}
    assert [d[0] for d in compare_params(bm, inputs, got)] == ["start"]


def test_type_param_spaces_are_normalized():
    bm, _ = errand_case()
    assert compare_params(bm, {"room_type": "living_room"}, {"room_type": "Living room"}) == []


def test_estimate_cost():
    assert estimate_cost(1_000_000, 1_000_000) == PRICE_INPUT_PER_MTOK + PRICE_OUTPUT_PER_MTOK


def test_classify_and_group():
    bm, inputs = errand_case()
    other = next(floor_id for floor_id in bm.floors if floor_id != inputs["floor_id"])
    assert classify_mismatch(bm, "floor_id", inputs["floor_id"], other) == "wrong floor id"
    assert classify_mismatch(bm, "start", inputs["start"], "no such room") == "room: name not unique or unknown"
    assert classify_mismatch(bm, "TOOL", "errand", "other") == "wrong tool"
    assert classify_mismatch(bm, "x", 1, MISSING) == "parameter missing"
    groups = group_mismatches({"q1": bm}, [("errand", "q1", "floor_id", inputs["floor_id"], other)] * 3)
    assert {label: len(items) for label, items in groups.items()} == {"wrong floor id": 3}
