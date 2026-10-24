"""Campus adapters: one file per adapter, the same campus from every format, tolerant of bad input."""

import importlib
import inspect
import json
import pkgutil
import random
import time

import pytest

from building_agent import campus_adapters
from building_agent.campus import (
    Campus,
    CampusError,
    UnknownCampusFormat,
    entrances,
    load_campus,
    make_example_campus,
    save_campus,
    validate_campus,
)
from building_agent.campus_adapters import describe_adapters, load_adapters
from building_agent.campus_adapters.conversation import campus_from_description
from building_agent.campus_adapters.geo import haversine_m
from tests.conftest import DATA, load_map

IDS = ["proc-campus-dev-000", "proc-factory-dev-003", "resplan-439"]


def comparable(campus: Campus, estimated: bool = True) -> dict:
    """Fields every adapter must agree on (origins only exist where the input had positions)."""
    return {
        "buildings": [(item.building_id, str(item.path)) for item in campus.buildings],
        "links": [
            (
                link.id,
                link.kind,
                link.from_building,
                link.from_entrance,
                link.to_building,
                link.to_entrance,
                link.length_m,
                link.length_estimated if estimated else None,
                link.step_free,
                link.closed,
            )
            for link in campus.links
        ],
    }


@pytest.fixture
def geo_campus(tmp_path) -> tuple[Campus, object]:
    """Reference campus, built from a geo file with entrances pinned so every format can name them exactly."""
    pinned = {item: entrances(load_map(str(DATA / "dev" / item)))[0]["id"] for item in IDS}
    buildings = [
        {
            "building_id": item,
            "lat": 48.2650 + 0.0004 * index,
            "lon": 11.6700 + 0.0006 * index,
            "entrance": pinned[item],
        }
        for index, item in enumerate(IDS)
    ]
    path = tmp_path / "geo.json"
    path.write_text(json.dumps({"buildings": buildings}), encoding="utf-8")
    campus, findings = load_campus(path)
    assert findings.ok, findings.summary()
    return campus, path


# ---------- registry ----------


def test_every_adapter_exports_an_adapter_named_like_the_file():
    modules = [info.name for info in pkgutil.iter_modules(campus_adapters.__path__) if not info.name.startswith("_")]
    assert set(modules) >= {"campus_json", "links_csv", "geo", "conversation"}
    for module_name in modules:
        module = importlib.import_module(f"building_agent.campus_adapters.{module_name}")
        adapter = getattr(module, "ADAPTER", None)
        assert adapter is not None, f"campus_adapters/{module_name}.py has no ADAPTER"
        assert adapter.name == module_name


def test_every_adapter_has_the_contract_shape():
    adapters = load_adapters()
    assert list(adapters)[:4] == ["campus_json", "links_csv", "geo", "conversation"]
    for name, adapter in adapters.items():
        assert adapter.description.strip(), f"{name}: description is empty"
        assert next(iter(inspect.signature(adapter.detect).parameters)) == "path"
        load_parameters = list(inspect.signature(adapter.load).parameters)
        assert load_parameters[:2] == ["path", "root"], f"{name}: load(path, root=None)"


def test_adapters_do_not_claim_each_others_files(geo_campus, tmp_path):
    campus, geo_path = geo_campus
    json_path = tmp_path / "campus.json"
    save_campus(campus, json_path)
    adapters = load_adapters()
    assert [name for name, adapter in adapters.items() if adapter.detect(geo_path)] == ["geo"]
    assert [name for name, adapter in adapters.items() if adapter.detect(json_path)] == ["campus_json"]


# ---------- same campus, every format ----------


def write_csv(path, campus: Campus, variant: str) -> None:
    def num(value, comma):
        return str(value).replace(".", ",") if comma else str(value)

    if variant == "A":
        header = "building_a;entrance_a;building_b;entrance_b;kind;length_m;estimated"
        sep, comma, bom = ";", True, False
    elif variant == "B":
        header = " From ; From Entrance ; To ; To Entrance ; Type ; Distance ; Estimated "
        sep, comma, bom = ";", True, True
    else:
        header = "from_building,from_entrance,to_building,to_entrance,type,dist,estimated"
        sep, comma, bom = ",", False, True
    lines = [header]
    for link in campus.links:
        cells = [
            link.from_building,
            link.from_entrance,
            link.to_building,
            link.to_entrance,
            link.kind,
            num(link.length_m, comma),
            str(link.length_estimated).lower(),
        ]
        lines.append(sep.join(f"  {item} " if variant == "B" else item for item in cells))
    text = "\r\n".join(lines) + "\r\n"
    path.write_bytes(text.encode("utf-8-sig" if bom else "utf-8"))


def test_json_csv_geo_give_the_same_campus(geo_campus, tmp_path):
    reference, _ = geo_campus
    assert len(reference.links) == 3
    assert all(link.length_estimated and link.length_m > 0 for link in reference.links)

    json_path = tmp_path / "campus.json"
    save_campus(reference, json_path)
    from_json, findings = load_campus(json_path)
    assert from_json == reference
    assert [item.code for item in findings.items] == ["length_estimated"] * len(reference.links)

    for variant in "ABC":
        csv_path = tmp_path / f"links_{variant}.csv"
        write_csv(csv_path, reference, variant)
        from_csv, _ = load_campus(csv_path)
        assert comparable(from_csv) == comparable(reference), variant
        assert from_csv.links == reference.links, variant


def test_geo_csv_gives_the_same_links_as_geo_json(geo_campus, tmp_path):
    reference, _ = geo_campus
    rows = ["Building_ID;Latitude;Longitude;Entrance"]
    pinned = {link.from_building: link.from_entrance for link in reference.links}
    pinned.update({link.to_building: link.to_entrance for link in reference.links})
    for index, item in enumerate(IDS):
        rows.append(f"{item};{48.2650 + 0.0004 * index};{11.6700 + 0.0006 * index};{pinned[item]}".replace(".", ",", 2))
    path = tmp_path / "positions.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    from_csv, _ = load_campus(path)
    assert comparable(from_csv) == comparable(reference)


def test_given_lengths_are_kept_and_missing_ones_flagged(example_data, tmp_path):
    campus, findings = load_campus(example_data / "campus.json")
    assert [link.length_m for link in campus.links[:2]] == [85.0, 40.0]
    assert not campus.links[0].length_estimated
    path = tmp_path / "links.csv"
    path.write_text(
        "from;from_entrance;to;to_entrance;kind;length\n"
        f"{campus.links[0].from_building};{campus.links[0].from_entrance};{campus.links[0].to_building};"
        f"{campus.links[0].to_entrance};walkway;85,0\n"
        f"{campus.links[1].from_building};{campus.links[1].from_entrance};{campus.links[1].to_building};"
        f"{campus.links[1].to_entrance};bridge;\n",
        encoding="utf-8",
    )
    from_csv, csv_findings = load_campus(path)
    assert from_csv.links[0].length_m == 85.0
    assert from_csv.links[1].length_m is None
    assert "link_length_missing" in {item.code for item in csv_findings.items}
    assert not csv_findings.ok and findings.ok


@pytest.fixture
def example_data(tmp_path):
    save_campus(make_example_campus(DATA), tmp_path / "campus.json")
    return tmp_path


def test_geo_picks_the_nearest_entrance_pair_and_respects_threshold(tmp_path):
    first, second = "proc-factory-dev-003", "proc-campus-dev-000"
    far = {"building_id": "resplan-439", "lat": 48.3, "lon": 11.7}
    data = {
        "buildings": [
            {"building_id": first, "lat": 48.2650, "lon": 11.6700},
            {"building_id": second, "lat": 48.2650, "lon": 11.6706},
            far,
        ]
    }
    path = tmp_path / "geo.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    campus, findings = load_campus(path)
    assert len(campus.links) == 1
    link = campus.links[0]
    assert link.length_estimated and 0 < link.length_m
    assert link.length_m <= round(haversine_m(48.2650, 11.6700, 48.2650, 11.6706) * 1.2 + 80, 1)
    assert "building_not_connected" in {item.code for item in findings.items}
    data["pairs"] = [[first, "resplan-439"]]
    path.write_text(json.dumps(data), encoding="utf-8")
    campus, _ = load_campus(path)
    assert len(campus.links) == 2


def test_haversine_known_distance():
    assert haversine_m(48.0, 11.0, 48.0, 11.0) == 0
    assert 111_000 < haversine_m(48.0, 11.0, 49.0, 11.0) < 111_400


def test_conversation_entries_become_a_campus():
    first = entrances(load_map(str(DATA / "dev" / IDS[0])))[0]["id"]
    second = entrances(load_map(str(DATA / "dev" / IDS[1])))[0]["id"]
    entries = [
        {"type": "building", "building_id": IDS[0], "origin": [0, 0]},
        {"type": "link", "building_a": IDS[0], "entrance_a": first, "building_b": IDS[1], "entrance_b": second,
         "kind": "tunnel", "length_m": "60,5"},
        "garbage",
    ]  # fmt: skip
    campus = campus_from_description(entries, root=DATA)
    assert [item.building_id for item in campus.buildings] == IDS[:2]
    assert campus.links[0].length_m == 60.5 and campus.links[0].kind == "tunnel" and campus.links[0].id == "L1"
    assert campus.load_findings and campus.load_findings[0].code == "entry_unreadable"
    assert validate_campus(campus) == []


def test_conversation_file_is_loaded(tmp_path):
    path = tmp_path / "talk.json"
    path.write_text(json.dumps({"entries": [{"type": "building", "building_id": IDS[0]}]}), encoding="utf-8")
    campus, findings = load_campus(path, root=DATA)
    assert campus.buildings[0].building_id == IDS[0]
    assert "building_not_connected" in {item.code for item in findings.items}


def test_conversation_accepts_nonsense():
    assert campus_from_description(None).links == []
    assert campus_from_description([{"type": "link"}]).links[0].from_building == ""


# ---------- unknown formats ----------


def test_unknown_file_raises_with_what_each_adapter_expects(tmp_path):
    path = tmp_path / "map.txt"
    path.write_text("here is my campus, the lab is near the canteen", encoding="utf-8")
    with pytest.raises(UnknownCampusFormat) as caught:
        load_campus(path)
    message = str(caught.value)
    assert "I do not recognise the file map.txt" in message
    for name in load_adapters():
        assert f"- {name}:" in message
    assert message.endswith(describe_adapters().splitlines()[-1])
    assert isinstance(caught.value, CampusError)


# ---------- fuzz ----------


@pytest.mark.parametrize("name", ["empty.csv", "empty.json", "empty.txt"])
def test_empty_file_is_an_unknown_format(tmp_path, name):
    (tmp_path / name).write_bytes(b"")
    with pytest.raises(UnknownCampusFormat):
        load_campus(tmp_path / name)


def test_binary_file_is_an_unknown_format(tmp_path):
    path = tmp_path / "blob.csv"
    path.write_bytes(bytes(random.Random(1).randrange(256) for _ in range(5000)))
    with pytest.raises(UnknownCampusFormat):
        load_campus(path)
    (tmp_path / "nul.json").write_bytes(b'{"buildings": [], "links": []}\x00')
    with pytest.raises(UnknownCampusFormat):
        load_campus(tmp_path / "nul.json")


def test_invalid_json_is_an_unknown_format(tmp_path):
    path = tmp_path / "campus.json"
    path.write_text('{"buildings": [', encoding="utf-8")
    with pytest.raises(UnknownCampusFormat):
        load_campus(path)


def test_utf16_excel_export_is_read(tmp_path):
    first = entrances(load_map(str(DATA / "dev" / IDS[0])))[0]["id"]
    second = entrances(load_map(str(DATA / "dev" / IDS[1])))[0]["id"]
    text = f"sep=;\nfrom;from_entrance;to;to_entrance;length\n{IDS[0]};{first};{IDS[1]};{second};12,5 m\n"
    path = tmp_path / "excel.csv"
    path.write_bytes(text.encode("utf-16"))
    campus, findings = load_campus(path, root=DATA)
    assert campus.links[0].length_m == 12.5
    assert findings.ok


FUZZ_LENGTHS = ["1e999", "1e308", "NaN", "inf", "-5", "0", "abc", "", "99999999999999999999", "1.234,5", "12 m"]


@pytest.mark.parametrize("length", FUZZ_LENGTHS)
def test_odd_lengths_never_crash(tmp_path, length):
    first = entrances(load_map(str(DATA / "dev" / IDS[0])))[0]["id"]
    second = entrances(load_map(str(DATA / "dev" / IDS[1])))[0]["id"]
    path = tmp_path / "links.csv"
    path.write_text(f"from;from_entrance;to;to_entrance;length\n{IDS[0]};{first};{IDS[1]};{second};{length}\n")
    campus, findings = load_campus(path)
    link = campus.links[0]
    assert link.length_m is None or link.length_m > 0 or "link_length_not_positive" in {i.code for i in findings.items}
    if length in ("NaN", "inf", "1e999", "abc", "", "0", "-5"):
        assert not findings.ok
    assert findings.summary()


def test_odd_json_values_never_crash(tmp_path):
    data = {
        "buildings": [{"building_id": "ü-ß-建物", "path": 5}, 7, {"id": IDS[0], "origin": ["a", None]}, {"nothing": 1}],
        "links": [
            {"id": "L1", "kind": None, "from": "x", "to": ["y"], "length_m": float("nan"), "width_m": "wide"},
            "text",
            {"from": {"building_id": "ü-ß-建物", "entrance": "☃"}, "to": {"building_id": IDS[0]}, "length_m": -3},
            {"id": "L1", "step_free": "maybe", "closed": "ja", "level_delta": 1e30},
        ],
    }
    path = tmp_path / "campus.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    campus, findings = load_campus(path)
    assert not findings.ok
    assert {"duplicate_link_id", "unknown_building"} <= {item.code for item in findings.items}
    assert campus.links[-1].closed is True and campus.links[-1].level_delta == 0


def test_duplicate_rows_and_same_entrance_twice(tmp_path):
    entrance = entrances(load_map(str(DATA / "dev" / IDS[0])))[0]["id"]
    other = entrances(load_map(str(DATA / "dev" / IDS[1])))[0]["id"]
    path = tmp_path / "links.csv"
    path.write_text(
        "building_a,entrance_a,building_b,entrance_b,length_m\n"
        f"{IDS[0]},{entrance},{IDS[1]},{other},50\n"
        f"{IDS[0]},{entrance},{IDS[1]},{other},50\n"
        f"{IDS[0]},{entrance},{IDS[0]},{entrance},10\n"
        ",,,,\n",
        encoding="utf-8",
    )
    campus, findings = load_campus(path)
    found = {item.code for item in findings.items}
    assert {"duplicate_link", "link_within_building"} <= found
    assert [link.id for link in campus.links] == ["L1", "L2", "L3"]


def test_unicode_names_survive(tmp_path):
    entrance = entrances(load_map(str(DATA / "dev" / IDS[0])))[0]["id"]
    other = entrances(load_map(str(DATA / "dev" / IDS[1])))[0]["id"]
    path = tmp_path / "campus.json"
    data = {
        "name": "Forschungscampus Größe 建物 ☃",
        "buildings": [
            {"building_id": IDS[0], "path": str(DATA / "dev" / IDS[0])},
            {"building_id": IDS[1], "path": str(DATA / "dev" / IDS[1])},
        ],
        "links": [
            {
                "id": "L1",
                "name": "Überdachter Weg ☂",
                "from": {"building_id": IDS[0], "entrance": entrance},
                "to": {"building_id": IDS[1], "entrance": other},
                "length_m": 30,
            }
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    campus, findings = load_campus(path)
    assert (
        findings.ok and campus.name.startswith("Forschungscampus Größe") and campus.links[0].name == "Überdachter Weg ☂"
    )


def test_forty_random_pairs_from_all_splits(tmp_path):
    folders = sorted(path.parent for path in DATA.glob("*/*/building.json"))
    assert len(folders) > 100
    rng = random.Random(7)
    started = time.time()
    for index in range(40):
        first, second = rng.sample(folders, 2)
        pick = [entrances(load_map(str(folder)))[0]["id"] for folder in (first, second)]
        data = {
            "id": f"pair-{index}",
            "buildings": [
                {"building_id": first.name, "path": str(first), "origin": [0, 0]},
                {
                    "building_id": second.name,
                    "path": str(second),
                    "origin": [100, rng.uniform(-50, 50)],
                    "rotation_deg": 90,
                },
            ],
            "links": [
                {
                    "id": "L1",
                    "kind": rng.choice(["walkway", "bridge", "tunnel"]),
                    "from": {"building_id": first.name, "entrance": pick[0]},
                    "to": {"building_id": second.name, "entrance": pick[1]},
                    "step_free": False,
                }
            ],
        }
        path = tmp_path / f"pair{index}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        campus, findings = load_campus(path)
        assert findings.ok, (first.name, second.name, findings.summary())
        assert campus.links[0].length_estimated and campus.links[0].length_m > 0
        assert validate_campus(campus) is not None
    assert time.time() - started < 20
