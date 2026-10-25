"""Place knowledge with time (docs/specs/place-knowledge.md): store, time logic, timed closures, queries, photos,
API and graph export. Offline; time is always injected."""

import base64
import io
import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from building_agent.knowledge import (
    MAX_SIDE_PX,
    KnowledgeError,
    KnowledgeStore,
    aas_export,
    apply_timed_closures,
    area_spaces,
    building_of,
    graph_jsonld,
    later,
)
from building_agent.knowledge_export import ROOM_TYPES
from building_agent.time_words import BERLIN, until_time
from starter_agent.building_map import BuildingMap
from web.server import App, make_handler

DATA = Path("data")
SUNDAY = datetime(2026, 10, 25, 9, 0, tzinfo=BERLIN)  # a Sunday


def factory_key() -> str:
    """A dev building with hall zones ('... H-A1'), machines and a lift (chosen from data, not hard-coded)."""
    for path in sorted((DATA / "dev").glob("*/building.json")):
        building = json.loads(path.read_text(encoding="utf-8"))
        halls = {
            space["id"]: space["name"].split(" H-")[-1][:1] for space in building["spaces"] if " H-" in space["name"]
        }
        machine_halls = {halls.get(asset["space_id"]) for asset in building["assets"] if asset["category"] == "machine"}
        if {"A", "B"} <= machine_halls and any(c["kind"] == "lift" for c in building["vertical_connectors"]):
            return path.parent.relative_to(DATA).as_posix()
    pytest.skip("no dev factory with halls, machines and a lift")


@pytest.fixture
def bm() -> BuildingMap:
    return BuildingMap.load(DATA / factory_key() / "building.json")


@pytest.fixture
def store(tmp_path) -> KnowledgeStore:
    return KnowledgeStore(tmp_path / "knowledge")


def machine_in(bm: BuildingMap, hall: str) -> dict:
    halls = area_spaces(bm, hall)
    return next(a for a in bm.assets.values() if a["category"] == "machine" and a["space_id"] in halls)


def lift_of(bm: BuildingMap) -> dict:
    return next(c for c in bm.connectors.values() if c["kind"] == "lift")


def lift_edges(bm: BuildingMap, lift_id: str) -> int:
    return sum(1 for *_, data in bm.graph(False).edges(data=True) if data.get("via") == lift_id)


# ---------- time words ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Aufzug 1 ist bis morgen kaputt", datetime(2026, 10, 26, 18, 0)),
        ("lift 1 is broken until tomorrow", datetime(2026, 10, 26, 18, 0)),
        ("bis Freitag gesperrt", datetime(2026, 10, 30, 18, 0)),
        ("bis 14 Uhr", datetime(2026, 10, 25, 14, 0)),
        ("until 2 pm", datetime(2026, 10, 25, 14, 0)),
        ("bis 8 Uhr", datetime(2026, 10, 26, 8, 0)),  # 8:00 has passed: tomorrow
        ("für 2 Stunden", datetime(2026, 10, 25, 11, 0)),
        ("für zwei Stunden", datetime(2026, 10, 25, 11, 0)),
        ("for 30 minutes", datetime(2026, 10, 25, 9, 30)),
        ("bis morgen 10 Uhr", datetime(2026, 10, 26, 10, 0)),
        ("bis morgen früh", datetime(2026, 10, 26, 8, 0)),
        ("bis Ende der Woche", datetime(2026, 10, 30, 18, 0)),
    ],
)
def test_until_time_resolves_phrases(text, expected):
    assert until_time(text, SUNDAY) == expected.replace(tzinfo=BERLIN)


@pytest.mark.parametrize("text", ["irgendwann", "bald", "the lift is broken", "bis 25 Uhr", "", None])
def test_until_time_unclear_is_none(text):
    assert until_time(text, SUNDAY) is None


def test_until_friday_said_on_friday_evening_is_next_friday():
    friday_evening = datetime(2026, 10, 30, 19, 0, tzinfo=BERLIN)
    assert until_time("bis Freitag", friday_evening) == datetime(2026, 11, 6, 18, 0, tzinfo=BERLIN)
    friday_morning = datetime(2026, 10, 30, 9, 0, tzinfo=BERLIN)
    assert until_time("bis Freitag", friday_morning) == datetime(2026, 10, 30, 18, 0, tzinfo=BERLIN)


# ---------- time logic ----------


def test_valid_expired_and_boundary_at_valid_to(bm, store):
    room = next(iter(bm.spaces))
    end = SUNDAY + timedelta(hours=2)
    fact = store.add(bm, kind="note", anchor={"space_id": room}, text="Hebel links", valid_to=end, now=SUNDAY)
    assert [f.id for f in store.query(bm, space_id=room, at=SUNDAY)] == [fact.id]
    assert [f.id for f in store.query(bm, space_id=room, at=end - timedelta(seconds=1))] == [fact.id]
    assert store.query(bm, space_id=room, at=end) == []  # exactly valid_to: no longer valid
    [old] = store.query(bm, space_id=room, at=end, status="expired")
    assert old.status == "expired"
    assert store.query(bm, space_id=room, at=SUNDAY - timedelta(seconds=1)) == []  # not yet valid


def test_resolve_ends_fact_and_history_is_newest_first(bm, store):
    machine = machine_in(bm, "Halle A")
    issue = store.add(
        bm, kind="issue", anchor={"asset_id": machine["id"]}, text="Ventil tropft", author="Techniker A", now=SUNDAY
    )
    noon = later(SUNDAY, hours=3)
    done = store.resolve(bm, issue.id, text="Ventil repariert", author="Techniker B", now=noon)
    assert done.resolves == issue.id and done.status == "resolved"
    assert store.query(bm, asset_id=machine["id"], at=later(noon, minutes=1)) == []
    assert [f.id for f in store.query(bm, asset_id=machine["id"], at=later(SUNDAY, hours=1))] == [issue.id]
    history = store.query(bm, asset_id=machine["id"], history=True, at=later(noon, minutes=1))
    assert [f.id for f in history] == [done.id, issue.id]
    assert [f.status for f in history] == ["resolved", "resolved"]
    assert history[1].resolved_by == done.id and history[1].valid_to == done.valid_from
    with pytest.raises(KnowledgeError):
        store.resolve(bm, issue.id, now=later(noon, minutes=2))  # already resolved


def test_multi_anchor_fact_is_found_and_resolved_at_any_anchor(bm, store):
    first, second = machine_in(bm, "Halle A"), machine_in(bm, "Halle B")
    fact = store.add(
        bm,
        kind="issue",
        anchor={"asset_id": first["id"]},
        related=[second["space_id"], second["id"]],
        text="Druckluft schwankt",
        now=SUNDAY,
    )
    assert [f.id for f in store.query(bm, space_id=second["space_id"], at=SUNDAY)] == [fact.id]
    assert [f.id for f in store.query(bm, asset_id=second["id"], at=SUNDAY)] == [fact.id]
    [found] = store.query(bm, area="Hall B", at=SUNDAY)
    store.resolve(bm, found.id, now=later(SUNDAY, hours=1))
    assert store.query(bm, asset_id=first["id"], at=later(SUNDAY, hours=2)) == []
    assert store.query(bm, asset_id=second["id"], at=later(SUNDAY, hours=2)) == []


def test_undo_only_right_after_creating_and_undo_of_resolution_reopens(bm, store):
    room = next(iter(bm.spaces))
    fact = store.add(bm, kind="note", anchor={"space_id": room}, text="Tippfehler", now=SUNDAY)
    assert store.undo_last(bm, now=later(SUNDAY, seconds=121)) is None
    assert store.undo_last(bm, now=later(SUNDAY, seconds=30)).id == fact.id
    assert store.query(bm, history=True, at=SUNDAY) == []
    issue = store.add(bm, kind="issue", anchor={"space_id": room}, text="Licht flackert", now=SUNDAY)
    store.resolve(bm, issue.id, now=later(SUNDAY, minutes=1))
    store.undo_last(bm, now=later(SUNDAY, minutes=2))
    [back] = store.query(bm, space_id=room, at=later(SUNDAY, minutes=3))
    assert back.id == issue.id and back.valid_to is None and back.resolved_by is None


def test_persistence_survives_a_new_store(bm, store):
    room = next(iter(bm.spaces))
    fact = store.add(bm, kind="note", anchor={"space_id": room}, text="bleibt", now=SUNDAY)
    again = KnowledgeStore(store.root)
    assert [f.id for f in again.query(bm, at=SUNDAY)] == [fact.id]
    assert json.loads((store.root / building_of(bm) / "facts.json").read_text())[0]["text"] == "bleibt"


# ---------- timed closures and routing ----------


def test_timed_closure_affects_routing_only_inside_the_window(bm, store):
    lift = lift_of(bm)
    end = until_time("bis morgen", SUNDAY)
    store.add(bm, kind="closure", anchor={"element_id": lift["id"]}, text="Aufzug kaputt", valid_to=end, now=SUNDAY)
    open_edges = lift_edges(bm, lift["id"])
    assert open_edges > 0
    assert apply_timed_closures(bm, store, SUNDAY + timedelta(hours=1)) == {lift["id"]}
    assert lift["id"] in bm.closed and lift_edges(bm, lift["id"]) == 0
    assert store.active_closures(bm, SUNDAY) == {lift["id"]: end.isoformat()}
    assert apply_timed_closures(bm, store, end) == set()  # exactly at valid_to: open again
    assert lift["id"] not in bm.closed and lift_edges(bm, lift["id"]) == open_edges


def test_manual_closures_are_never_touched(bm, store):
    lift = lift_of(bm)
    door = next(iter(bm.openings))
    bm.closed.update({door, lift["id"]})  # both closed by hand before any fact
    store.add(
        bm, kind="closure", anchor={"element_id": lift["id"]}, text="x", valid_to=later(SUNDAY, hours=1), now=SUNDAY
    )
    apply_timed_closures(bm, store, SUNDAY)
    apply_timed_closures(bm, store, later(SUNDAY, hours=2))  # the fact expired
    assert {door, lift["id"]} <= bm.closed


def test_resolved_closure_reopens(bm, store):
    lift = lift_of(bm)
    fact = store.add(bm, kind="closure", anchor={"element_id": lift["id"]}, text="kaputt", now=SUNDAY)
    apply_timed_closures(bm, store, SUNDAY)
    assert lift["id"] in bm.closed
    store.resolve(bm, fact.id, now=later(SUNDAY, hours=1))
    apply_timed_closures(bm, store, later(SUNDAY, hours=1))
    assert lift["id"] not in bm.closed


# ---------- queries ----------


def test_query_filters_type_area_status_person_period(bm, store):
    a, b = machine_in(bm, "Halle A"), machine_in(bm, "Halle B")
    monday = SUNDAY - timedelta(days=6)
    old = store.add(bm, kind="issue", anchor={"asset_id": a["id"]}, text="alt", author="Techniker A", now=monday)
    store.resolve(bm, old.id, text="fixed", author="Techniker A", now=later(monday, hours=1))
    hit = store.add(bm, kind="issue", anchor={"asset_id": a["id"]}, text="tropft", author="Techniker A", now=SUNDAY)
    store.add(bm, kind="issue", anchor={"asset_id": b["id"]}, text="laut", author="Techniker B", now=SUNDAY)
    store.add(bm, kind="note", anchor={"space_id": a["space_id"]}, text="Hebel", author="Techniker A", now=SUNDAY)
    at = later(SUNDAY, minutes=5)
    found = store.query(bm, asset_type=a["type"], area="Halle A", person="techniker a", at=at)
    assert [f.id for f in found] == [hit.id]
    assert {f.text for f in store.query(bm, category="machine", at=at)} == {"tropft", "laut"}
    assert {f.text for f in store.query(bm, person="Techniker B", at=at)} == {"laut"}
    assert {f.text for f in store.query(bm, floor_id=a["floor_id"], area="H-A", at=at)} == {"tropft", "Hebel"}
    assert {f.text for f in store.query(bm, asset_id=a["id"], status="resolved", at=at)} == {"alt", "fixed"}
    week = store.query(bm, asset_id=a["id"], history=True, since=monday, at=at)
    assert [f.text for f in week] == ["tropft", "fixed", "alt"]
    today = store.query(bm, asset_id=a["id"], history=True, since=SUNDAY - timedelta(hours=1), at=at)
    assert [f.text for f in today] == ["tropft"]
    assert store.query(bm, asset_type="cnc_lathe_that_does_not_exist", at=at) == []
    assert store.persons(bm) == [
        {"person_id": "techniker-a", "name": "Techniker A", "count": 4},
        {"person_id": "techniker-b", "name": "Techniker B", "count": 1},
    ]


# ---------- validation and photos ----------


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"anchor": {"space_id": "nope"}}, "space_id"),
        ({"anchor": {"asset_id": "nope"}}, "asset_id"),
        ({"text": ""}, "text"),
        ({"text": "x" * 501}, "text"),
        ({"kind": "rumour"}, "kind"),
        ({"related": ["../../etc"]}, "related"),
        ({"valid_to": "2020-01-01T00:00:00+00:00"}, "future"),
        ({"kind": "closure"}, "element_id"),
        ({"anchor": "S1"}, "anchor"),
        ({"source": "telepathy"}, "source"),
    ],
)
def test_validation(bm, store, kwargs, message):
    room = next(iter(bm.spaces))
    args = {"kind": "note", "anchor": {"space_id": room}, "text": "ok", **kwargs}
    with pytest.raises(KnowledgeError, match=message):
        store.add(bm, now=SUNDAY, **args)


def test_point_outside_the_room_is_refused(bm, store):
    room = next(iter(bm.spaces))
    with pytest.raises(KnowledgeError, match="point"):
        store.add(bm, kind="note", anchor={"space_id": room, "point": [1e6, 1e6]}, text="x", now=SUNDAY)


def jpeg_with_gps(size=(2400, 1200)) -> bytes:
    image = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    exif[0x8825] = {1: "N", 2: (48.0, 8.0, 0.0)}  # GPS IFD
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_photo_is_resized_and_loses_exif(bm, store):
    raw = jpeg_with_gps()
    assert b"PhoneMaker" in raw
    room = next(iter(bm.spaces))
    fact = store.add(bm, kind="issue", anchor={"space_id": room}, text="Foto", photo_bytes=raw, now=SUNDAY)
    path = store.photo_path(bm, fact.id)
    data = path.read_bytes()
    assert b"PhoneMaker" not in data and b"Exif" not in data
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "JPEG" and max(image.size) == MAX_SIDE_PX
        assert not image.getexif()


@pytest.mark.parametrize(
    ("data", "status"),
    [
        (b"GIF89a" + b"\0" * 100, 415),
        (b"\x89PNG\r\n\x1a\n" + b"\0" * 100, 415),  # magic but no image
        (b"\xff\xd8\xff" + b"\0" * (8 * 1024 * 1024 + 1), 413),
    ],
)
def test_photo_type_and_size_limits(bm, store, data, status):
    room = next(iter(bm.spaces))
    with pytest.raises(KnowledgeError) as error:
        store.add(bm, kind="note", anchor={"space_id": room}, text="x", photo_bytes=data, now=SUNDAY)
    assert error.value.status == status


def test_no_path_tricks(bm, store):
    assert store.photo_path(bm, "../../etc/passwd") is None
    assert store.photo_path(bm, "f-000000000000") is None
    for bad in ("..", "../x", "a/b", ""):
        with pytest.raises(KnowledgeError):
            store.folder(bad)


# ---------- graph export ----------


def test_every_room_type_in_data_has_brick_and_rec_types():
    room_types = set()
    for path in DATA.glob("*/*/building.json"):
        room_types |= {space["room_type"] for space in json.loads(path.read_text(encoding="utf-8"))["spaces"]}
    assert room_types, "no data"
    missing = room_types - set(ROOM_TYPES)
    assert not missing
    for rec, brick in ROOM_TYPES.values():
        assert rec.startswith("rec:") and brick.startswith("brick:")


def test_jsonld_graph_has_nodes_and_edges_with_time(bm, store):
    machine = machine_in(bm, "Halle A")
    issue = store.add(
        bm, kind="issue", anchor={"asset_id": machine["id"]}, text="tropft", author="Techniker A", now=SUNDAY
    )
    done = store.resolve(bm, issue.id, author="Techniker B", now=later(SUNDAY, hours=1))
    lift = lift_of(bm)
    store.add(
        bm, kind="closure", anchor={"element_id": lift["id"]}, text="kaputt", valid_to=later(SUNDAY, days=1), now=SUNDAY
    )
    doc = graph_jsonld(bm, store, at=later(SUNDAY, hours=2))
    assert "brick" in doc["@context"] and "rec" in doc["@context"]
    nodes = {node["@id"]: node for node in doc["@graph"]}
    types = {t for node in doc["@graph"] for t in node["@type"]}
    assert {"rec:Building", "rec:Level", "rec:Elevator", "wanda:Fact", "rec:Person"} <= types
    spaces = [n for n in doc["@graph"] if "roomType" in n]
    assert len(spaces) == len(bm.spaces) and all(any(t.startswith("rec:") for t in n["@type"]) for n in spaces)
    facts = [n for n in doc["@graph"] if "wanda:Fact" in n["@type"]]
    resolved = next(n for n in facts if n["@id"].endswith(issue.id))
    assert resolved["validTo"] and resolved["resolvedBy"].endswith(done.id) and resolved["reportedBy"] in nodes
    assert next(n for n in facts if n["@id"].endswith(done.id))["resolves"].endswith(issue.id)
    assert nodes[resolved["anchoredAt"][0]]["assetType"] == machine["type"]
    lift_node = next(n for n in doc["@graph"] if n["@id"].endswith(":connector:" + lift["id"]))
    assert lift_node["closedUntil"] and len(lift_node["connects"]) == len(lift["space_ids"])
    json.dumps(doc)  # serialisable


def test_aas_export_structure(bm, store):
    machine = machine_in(bm, "Halle A")
    store.add(bm, kind="issue", anchor={"asset_id": machine["id"]}, text="tropft", now=SUNDAY)
    doc = aas_export(bm, store, at=later(SUNDAY, minutes=1))
    expected = [a for a in bm.assets.values() if a["category"] in ("machine", "equipment")]
    assert len(doc["assetAdministrationShells"]) == len(expected)
    assert len(doc["submodels"]) == 2 * len(expected)
    by_id = {sm["id"]: sm for sm in doc["submodels"]}
    shell = next(
        s for s in doc["assetAdministrationShells"] if s["assetInformation"]["globalAssetId"].endswith(machine["id"])
    )
    nameplate, issues = (by_id[ref["keys"][0]["value"]] for ref in shell["submodels"])
    assert nameplate["idShort"] == "Nameplate" and issues["idShort"] == "OpenIssues"
    values = {e["idShort"]: e.get("value") for e in nameplate["submodelElements"]}
    assert values["Name"] == machine["name"] and values["Type"] == machine["type"]
    [entry] = issues["submodelElements"]
    assert {e["idShort"]: e["value"] for e in entry["value"]}["Text"] == "tropft"


# ---------- web API ----------


@pytest.fixture
def app(tmp_path) -> App:
    return App(DATA, knowledge_root=tmp_path / "knowledge")


def test_api_create_list_history_undo_and_state(app):
    key = factory_key()
    bm = app.session(key).map
    room = next(iter(bm.spaces))
    photo = base64.b64encode(jpeg_with_gps((400, 300))).decode()
    status, payload = app.post(
        "/api/facts",
        {"building": key, "kind": "note", "anchor": {"space_id": room}, "text": "Hebel links", "author": "Techniker A",
         "photo_base64": "data:image/jpeg;base64," + photo},
    )  # fmt: skip
    assert status == 200
    fact = payload["fact"]
    assert fact["photo"] == f"/api/facts/photo?key={key.replace('/', '%2F')}&id={fact['id']}"
    assert [f["id"] for f in payload["state"]["facts"]] == [fact["id"]]
    assert payload["state"]["closed_until"] == {}
    _, listed = app.get("/api/facts", {"key": [key], "space_id": [room]})
    assert [f["id"] for f in listed["facts"]] == [fact["id"]] and listed["persons"][0]["person_id"] == "techniker-a"
    assert app.fact_photo({"key": [key], "id": [fact["id"]]})[:3] == b"\xff\xd8\xff"
    _, undone = app.post("/api/facts/undo", {"building": key})
    assert undone["undone"]["id"] == fact["id"] and undone["state"]["facts"] == []
    _, history = app.get("/api/facts", {"key": [key], "history": ["1"]})
    assert history["facts"] == []


def test_api_refuses_closures_and_bad_input(app):
    key = factory_key()
    bm = app.session(key).map
    lift = lift_of(bm)
    with pytest.raises(KnowledgeError, match="chat"):
        app.post("/api/facts", {"building": key, "kind": "closure", "anchor": {"element_id": lift["id"]}, "text": "x"})
    with pytest.raises(KnowledgeError):
        app.post("/api/facts", {"building": key, "kind": "note", "anchor": {"space_id": "x"}, "text": "x"})
    with pytest.raises(KnowledgeError):
        app.post("/api/facts", {"building": key, "kind": "note", "anchor": {"space_id": next(iter(bm.spaces))},
                                "text": "x", "photo_base64": "not base64!"})  # fmt: skip
    with pytest.raises(ValueError):
        app.get("/api/facts", {"key": ["dev/../../etc"]})


def test_state_shows_timed_closure_and_page_open_ends_it(app):
    key = factory_key()
    session = app.session(key)
    lift = lift_of(session.map)
    end = later(datetime.now(BERLIN), hours=5)
    app.knowledge.add(session.map, kind="closure", anchor={"element_id": lift["id"]}, text="kaputt", valid_to=end)
    _, view = app.get("/api/building", {"key": [key]})
    assert lift["id"] in view["state"]["closed"]
    assert view["state"]["closed_until"] == {lift["id"]: end.isoformat(timespec="seconds")}
    _, payload = app.post("/api/close", {"building": key, "element": lift["id"], "closed": False})
    assert lift["id"] not in payload["state"]["closed"] and payload["state"]["closed_until"] == {}
    _, view = app.get("/api/building", {"key": [key]})
    assert lift["id"] not in view["state"]["closed"]


def test_graph_endpoint(app):
    key = factory_key()
    _, doc = app.get("/api/graph", {"key": [key]})
    assert doc["@graph"][0]["@type"][0] == "rec:Building"
    _, aas = app.get("/api/graph", {"key": [key], "format": ["aas"]})
    assert "assetAdministrationShells" in aas


def test_http_photo_and_origin_guard(app):
    from http.server import ThreadingHTTPServer

    key = factory_key()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    except PermissionError:
        pytest.skip("local port binding is not allowed here")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    room = next(iter(app.session(key).map.spaces))
    body = {"building": key, "kind": "issue", "anchor": {"space_id": room}, "text": "tropft",
            "photo_base64": base64.b64encode(jpeg_with_gps((300, 200))).decode()}  # fmt: skip
    try:
        evil = urllib.request.Request(
            f"{base}/api/facts",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Origin": "http://evil.example"},
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(evil)
        assert error.value.code == 403
        good = urllib.request.Request(
            f"{base}/api/facts", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(good) as response:
            fact = json.loads(response.read())["fact"]
        with urllib.request.urlopen(base + fact["photo"]) as response:
            assert response.headers["Content-Type"] == "image/jpeg"
            assert response.read()[:3] == b"\xff\xd8\xff"
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f"{base}/api/facts/photo?key={key}&id=..%2F..%2Fetc")
        assert error.value.code == 404
        with urllib.request.urlopen(f"{base}/api/facts?key={key}&history=1") as response:
            assert [f["id"] for f in json.loads(response.read())["facts"]] == [fact["id"]]
    finally:
        server.shutdown()
        server.server_close()
