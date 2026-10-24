from building_agent.find_space import find_space
from building_agent.params_eval import (
    MISSING,
    PRICE_INPUT_PER_MTOK,
    PRICE_OUTPUT_PER_MTOK,
    building_source,
    check_unlabelled,
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


SCHEMA = {"required": ["start", "floor_id", "room_type"]}


def unlabelled_case():
    building_dir, _ = labelled_questions("errand")[0]
    bm = load_map(building_dir)
    unique = next(s for s in bm.spaces.values() if "match" in find_space(bm, s["name"]))
    return bm, unique


def response(**args):
    return {"tool": "errand", "input": args}


def test_unlabelled_usable():
    bm, space = unlabelled_case()
    args = {"start": space["name"], "floor_id": space["floor_id"], "room_type": space["room_type"]}
    assert check_unlabelled(bm, "errand", "q", response(**args), SCHEMA) == []


def test_unlabelled_ambiguous_name():
    bm, space = unlabelled_case()
    twin = {**space, "id": "twin-of-" + space["id"]}
    bm.spaces[twin["id"]] = twin
    args = {"start": space["name"], "floor_id": space["floor_id"], "room_type": space["room_type"]}
    try:
        reasons = check_unlabelled(bm, "errand", "q", response(**args), SCHEMA)
    finally:
        del bm.spaces[twin["id"]]
    assert any(r.startswith("start: ambiguous space") and twin["id"] in r for r in reasons)


def test_unlabelled_unknown_floor_type_and_missing_param():
    bm, space = unlabelled_case()
    reasons = check_unlabelled(bm, "errand", "q", response(start=space["id"], floor_id="nope", room_type="zzz"), SCHEMA)
    assert any("unknown floor" in r for r in reasons)
    assert any("unknown type" in r for r in reasons)
    reasons = check_unlabelled(bm, "errand", "q", response(start=space["id"]), SCHEMA)
    assert sorted(reasons) == ["missing param floor_id", "missing param room_type"]


def test_unlabelled_wrong_tool_and_source():
    bm, _ = unlabelled_case()
    assert check_unlabelled(bm, "errand", "q", {"tool": "other", "input": {}}, SCHEMA)[0].startswith("wrong tool")
    assert building_source("resplan-102") == "resplan"
