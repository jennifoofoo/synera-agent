from building_agent.find_space import find_space
from building_agent.params_eval import compare_params
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
