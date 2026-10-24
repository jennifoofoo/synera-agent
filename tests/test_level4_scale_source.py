"""Tolerant scale lookup in a building.json: field names, nesting, per floor or global, bad values, precedence."""

import math

import pytest

from building_agent.level4.scale_source import find_building_width, find_scale, load_building_json


@pytest.mark.parametrize(
    "key", ["m_per_px", "metres_per_pixel", "meters_per_pixel", "mpp", "m_per_pixel", "Metres-Per-Pixel", "M Per Px"]
)
def test_metres_per_pixel_names(key):
    hit = find_scale({key: 0.05})
    assert hit is not None and hit.metres_per_px == pytest.approx(0.05) and hit.key == key


@pytest.mark.parametrize("key", ["px_per_m", "pixels_per_metre", "pixels_per_meter", "ppm", "px_per_metre"])
def test_pixels_per_metre_names(key):
    assert find_scale({key: 20}).metres_per_px == pytest.approx(0.05)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(20, 0.05), (13.86, 1 / 13.86), (0.05, 0.05), (0.5, 0.5), (1000, 0.001), (0.001, 0.001)],
)
def test_plain_scale_is_read_by_size(value, expected):
    hit = find_scale({"scale": value})
    assert hit.metres_per_px == pytest.approx(expected)
    assert "guessed" in hit.reading
    assert find_scale({"resolution": value}).metres_per_px == pytest.approx(expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.05", 0.05),
        (" 20 ", 0.05),
        ("0,05", 0.05),
        ("0.02 m/px", 0.02),
        ("50 px/m", 0.02),
        ("50 pixels per metre", 0.02),
    ],
)
def test_numeric_strings_and_unit_hints(text, expected):
    assert find_scale({"scale": text}).metres_per_px == pytest.approx(expected)


def test_unit_hint_beats_size_guess():
    assert find_scale({"scale": "5 m/px"}).metres_per_px == pytest.approx(5.0)
    assert find_scale({"scale": "0.5 px/m"}).metres_per_px == pytest.approx(2.0)


@pytest.mark.parametrize(
    "bad", [0, -1, -0.05, math.nan, math.inf, -math.inf, 1e9, 1e-9, 1001, 0.0009, "abc", "", None, True, [1], {}]
)
def test_bad_values_give_none(bad):
    assert find_scale({"m_per_px": bad}) is None
    assert find_scale({"scale": bad}) is None


@pytest.mark.parametrize(
    "data",
    [
        {"building": {"scale": {"px_per_m": 20}}},
        {"floors": [{"level": 0, "px_per_m": 20}]},
        {"plan": {"scale": {"m_per_px": 0.05}}},
        {"plans": [{"image": "floor_0.png", "m_per_px": "0.05"}]},
        {"building": {"floors": {"0": {"pixels_per_metre": 20.0}}}},
        {"a": {"b": {"c": {"mpp": 0.05}}}},
    ],
)
def test_nested_variants(data):
    hit = find_scale(data, 0)
    assert hit is not None and hit.metres_per_px == pytest.approx(0.05)


def test_too_deep_is_not_searched():
    deep = {"a": {"b": {"c": {"d": {"e": {"f": {"mpp": 0.05}}}}}}}
    assert find_scale(deep) is None


def test_reports_the_key_path():
    hit = find_scale({"floors": [{"level": 1, "px_per_m": 20}]}, 1)
    assert hit.key == "floors[0].px_per_m"
    assert hit.reading == "px_per_m"


def test_floor_value_beats_global():
    data = {"px_per_m": 10, "floors": [{"level": 0, "px_per_m": 20}, {"level": 1, "px_per_m": 40}]}
    assert find_scale(data, 0).metres_per_px == pytest.approx(0.05)
    assert find_scale(data, 1).metres_per_px == pytest.approx(0.025)
    assert find_scale(data, 2).metres_per_px == pytest.approx(0.1)  # no value for floor 2: the global one


def test_other_floor_value_is_never_used():
    data = {"floors": [{"level": 0, "px_per_m": 20}]}
    assert find_scale(data, 3) is None
    assert find_scale(data, 0) is not None


def test_floor_keys_as_dict_names():
    data = {"floors": {"floor_0": {"mpp": 0.05}, "-1": {"mpp": 0.1}, "F2": {"mpp": 0.2}}}
    assert find_scale(data, 0).metres_per_px == pytest.approx(0.05)
    assert find_scale(data, -1).metres_per_px == pytest.approx(0.1)
    assert find_scale(data, 2).metres_per_px == pytest.approx(0.2)


def test_bad_floor_value_falls_back_to_global():
    data = {"px_per_m": 20, "floors": [{"level": 0, "px_per_m": -5}]}
    assert find_scale(data, 0).metres_per_px == pytest.approx(0.05)


def test_explicit_unit_name_beats_plain_name():
    data = {"scale": 100, "px_per_m": 20}
    hit = find_scale(data)
    assert hit.key == "px_per_m" and hit.metres_per_px == pytest.approx(0.05)


def test_shallower_key_beats_deeper_one():
    data = {"plan": {"mpp": 0.5}, "mpp": 0.05}
    assert find_scale(data).metres_per_px == pytest.approx(0.05)


def test_nothing_found_gives_none():
    assert find_scale({"building": {"id": "x", "floors": [{"level": 0}]}}, 0) is None
    assert find_scale([], 0) is None
    assert find_scale("text") is None
    assert find_scale(None) is None


def test_width_fields_and_polygons():
    assert find_building_width({"building": {"width_m": 23.5}}).metres == 23.5
    assert find_building_width({"floors": [{"level": 0, "width_m": 10}, {"level": 1, "width_m": 12}]}, 1).metres == 12
    assert find_building_width({"size_m": [30, 20]}).metres == 30
    assert find_building_width({"width_m": -3}) is None
    assert find_building_width({"width_m": math.nan}) is None
    assert find_building_width({"size": [800, 600]}) is None  # pixels, not metres
    data = {
        "floors": [{"id": "f0", "level": 0}],
        "spaces": [
            {"floor_id": "f0", "polygon": [[0, 0], [4, 0], [4, 3]]},
            {"floor_id": "f0", "polygon": [[4, 0], [10, 0], [10, 3]]},
        ],
    }
    assert find_building_width(data, 0).metres == pytest.approx(10)


def test_load_building_json_is_defensive(tmp_path):
    assert load_building_json(tmp_path / "missing.json") is None
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert load_building_json(tmp_path / "bad.json") is None
    (tmp_path / "number.json").write_text("42", encoding="utf-8")
    assert load_building_json(tmp_path / "number.json") is None
    (tmp_path / "ok.json").write_text('{"mpp": 0.05}', encoding="utf-8")
    assert load_building_json(tmp_path / "ok.json") == {"mpp": 0.05}
    (tmp_path / "nan.json").write_text('{"mpp": NaN}', encoding="utf-8")
    assert find_scale(load_building_json(tmp_path / "nan.json")) is None
