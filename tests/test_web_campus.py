"""Level 3 on the page: /api/campus endpoints, offline. Campuses come from the example and the three file adapters
(campus.json, links csv, geo json); the chat agent's tools must see the same campus state as the page."""

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError

from building_agent.campus import entrances, load_campus, make_example_campus, save_campus
from building_agent.campus_routing import CampusRouter
from starter_agent.building_map import MapError
from tests.conftest import DATA, load_map
from web.server import App, make_handler

IDS = ["proc-campus-dev-000", "proc-factory-dev-003", "resplan-439"]
JSON_KEY, CSV_KEY, GEO_KEY = "campuses:campus.json", "campuses:links.csv", "campuses:geo.json"


def first_room(app: App, building_id: str) -> str:
    bm = app.campus.holder.maps[building_id]
    return min(space for space, item in bm.spaces.items() if item["room_type"] != "corridor")


@pytest.fixture
def campuses(tmp_path) -> Path:
    """A campuses folder with one file per adapter format, all describing the same three buildings."""
    folder = tmp_path / "campuses"
    folder.mkdir()
    save_campus(make_example_campus(DATA), folder / "campus.json")
    pinned = {item: entrances(load_map(str(DATA / "dev" / item)))[0]["id"] for item in IDS}
    geo = [
        {"building_id": item, "lat": 48.2650 + 0.0004 * i, "lon": 11.6700 + 0.0006 * i, "entrance": pinned[item]}
        for i, item in enumerate(IDS)
    ]
    (folder / "geo.json").write_text(json.dumps({"buildings": geo}), encoding="utf-8")
    campus = make_example_campus(DATA)
    lines = ["from_building,from_entrance,to_building,to_entrance,type,length_m"]
    for link in campus.links:
        cells = [link.from_building, link.from_entrance, link.to_building, link.to_entrance, link.kind, link.length_m]
        lines.append(",".join(str(item) for item in cells))
    (folder / "links.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


@pytest.fixture
def app(tmp_path, campuses) -> App:
    return App(DATA, buildings_root=tmp_path / "buildings", campus_roots=(campuses,))


@pytest.fixture
def loaded(app) -> App:
    app.post("/api/campus/load", {"key": "example"})
    return app


def route(app: App, **extra) -> dict:
    start, destination = first_room(app, IDS[0]), first_room(app, IDS[2])
    return app.post("/api/campus/route", {"start": start, "destination": destination, **extra})[1]


# ---------- listing and loading ----------


def test_nothing_loaded_lists_the_known_campuses(app):
    status, view = app.get("/api/campus", {})
    assert status == 200 and view["loaded"] is False and view["buildings"] == [] and view["links"] == []
    assert {item["key"] for item in view["available"]} == {"example", JSON_KEY, CSV_KEY, GEO_KEY}


@pytest.mark.parametrize("key", ["example", JSON_KEY, CSV_KEY, GEO_KEY])
def test_every_adapter_loads_and_describes_the_same_campus(app, key):
    _, result = app.post("/api/campus/load", {"key": key})
    assert result["loaded"] is True and result["problems"] == 0
    view = result["campus"]
    assert [item["id"] for item in view["buildings"]] == IDS
    assert len(view["links"]) == (3 if key == GEO_KEY else 2)
    building = view["buildings"][0]
    assert building["map_loaded"] and building["floor_count"] >= 1 and building["entrances"]
    assert building["page_key"] == f"dev/{IDS[0]}"
    entrance = building["entrances"][0]
    assert {"id", "name", "room", "position", "step_free", "world_position", "floor_id"} <= set(entrance)
    link = view["links"][0]
    assert {"id", "kind", "from", "to", "level_delta", "length_m", "step_free", "closed"} <= set(link)
    assert link["from"]["building_id"] in IDS and link["from"]["entrance_id"]


def test_geo_campus_has_world_positions_and_csv_has_none(app):
    app.post("/api/campus/load", {"key": GEO_KEY})
    entrance = app.get("/api/campus", {})[1]["buildings"][0]["entrances"][0]
    assert entrance["world_position"] is not None
    app.post("/api/campus/load", {"key": CSV_KEY})
    assert app.get("/api/campus", {})[1]["buildings"][0]["entrances"][0]["world_position"] is None


@pytest.mark.parametrize(
    "key",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "campuses:../campus.json",
        "campuses:/etc/passwd",
        "data/dev/proc-campus-dev-000",
        "example/../x",
        "",
        None,
        5,
        ["example"],
        {"key": "example"},
    ],
)
def test_forged_campus_keys_are_refused(app, key):
    with pytest.raises(MapError):
        app.post("/api/campus/load", {"key": key})
    assert app.get("/api/campus", {})[1]["loaded"] is False


def test_a_campus_with_a_missing_building_folder_shows_findings(app, campuses):
    data = json.loads((campuses / "campus.json").read_text(encoding="utf-8"))
    data["buildings"][2]["path"] = "data/dev/does-not-exist"
    data["buildings"][2]["building_id"] = "ghost"
    for link in data["links"]:
        for side in ("from", "to"):
            if link[side]["building_id"] == IDS[2]:
                link[side]["building_id"] = "ghost"
    (campuses / "campus.json").write_text(json.dumps(data), encoding="utf-8")
    _, result = app.post("/api/campus/load", {"key": JSON_KEY})
    assert result["loaded"] is True and result["problems"] >= 1
    assert any(item["level"] == "error" and "ghost" in item["message"] for item in result["findings"])
    ghost = next(item for item in result["campus"]["buildings"] if item["id"] == "ghost")
    assert ghost["map_loaded"] is False and ghost["entrances"] == []
    answer = app.post("/api/campus/route", {"start": first_room(app, IDS[0]), "destination": "ghost-room"})[1]
    assert answer["ok"] is False and answer["error"]


def test_an_unreadable_campus_file_is_a_clean_error(app, campuses):
    (campuses / "broken.json").write_text("{not json", encoding="utf-8")
    key = "campuses:broken.json"
    assert key in {item["key"] for item in app.get("/api/campus", {})[1]["available"]}
    with pytest.raises(MapError):
        app.post("/api/campus/load", {"key": key})


def test_active_building_is_marked_from_the_page_key(loaded):
    key = f"dev/{IDS[1]}"
    view = loaded.get("/api/campus", {"key": [key]})[1]
    assert [item["id"] for item in view["buildings"] if item["active"]] == [IDS[1]]
    loaded.get("/api/building", {"key": [f"dev/{IDS[2]}"]})
    view = loaded.get("/api/campus", {})[1]
    assert [item["id"] for item in view["buildings"] if item["active"]] == [IDS[2]]
    view = loaded.get("/api/campus", {"key": ["dev/nope"]})[1]  # an unknown key changes nothing
    assert [item["id"] for item in view["buildings"] if item["active"]] == [IDS[2]]


# ---------- routing ----------


def test_route_matches_the_campus_router(loaded):
    holder = loaded.campus.holder
    start, destination = first_room(loaded, IDS[0]), first_room(loaded, IDS[2])
    expected = CampusRouter(holder.campus, holder.maps).route(start, destination)
    answer = route(loaded)
    assert answer["ok"] is True
    assert answer["length_m"] == expected.length_m
    assert answer["buildings"] == expected.buildings
    assert answer["links_used"] == [link.id for link in expected.links] == ["L1", "L2"]
    assert answer["steps"] == expected.steps
    assert [leg["kind"] for leg in answer["legs"]] == [leg.kind for leg in expected.legs]
    assert answer["state"]["route"]["ok"] and answer["state"]["route"]["length_m"] == expected.length_m


def test_route_legs_carry_rooms_and_polylines_in_both_coordinate_systems(loaded):
    answer = route(loaded)
    building_legs = [leg for leg in answer["legs"] if leg["kind"] == "building"]
    assert [leg["building_id"] for leg in building_legs] == IDS
    for leg in building_legs:
        assert leg["rooms"] and leg["points"] and len(leg["points"][0]) == 2
        assert leg["world_points"] is not None and len(leg["world_points"]) == len(leg["points"])
        assert leg["segments"] and leg["segments"][0]["floor_id"]
    link = next(leg for leg in answer["legs"] if leg["kind"] == "link")
    assert link["link_id"] == "L1" and link["from"]["world_point"] and link["to"]["world_point"]
    assert link["from"]["building_id"] == IDS[0] and link["to"]["building_id"] == IDS[1]


def test_route_without_positions_has_no_world_points(app):
    app.post("/api/campus/load", {"key": CSV_KEY})
    leg = route(app)["legs"][0]
    assert leg["points"] and leg["world_points"] is None


def test_same_building_route_and_step_free(loaded):
    bm = loaded.campus.holder.maps[IDS[0]]
    rooms = sorted(space for space, item in bm.spaces.items() if item["room_type"] != "corridor")
    answer = loaded.post("/api/campus/route", {"start": rooms[0], "destination": rooms[1], "step_free": True})[1]
    assert (
        answer["ok"] is True and answer["step_free"] is True and [leg["kind"] for leg in answer["legs"]] == ["building"]
    )


def test_ambiguous_name_returns_candidates(loaded):
    holder = loaded.campus.holder
    names = {}
    for building_id, bm in holder.maps.items():
        for space in bm.spaces.values():
            names.setdefault(space["name"].lower(), set()).add(building_id)
    shared = next((name for name, where in names.items() if len(where) > 1), None)
    if shared is None:
        pytest.skip("no room name occurs in two example buildings")
    answer = loaded.post("/api/campus/route", {"start": shared, "destination": first_room(loaded, IDS[0])})[1]
    assert answer["ok"] is False and answer["ambiguous"] is True and len(answer["candidates"]) >= 2
    assert {"building_id", "building", "space_id", "name", "floor"} <= set(answer["candidates"][0])


def test_unknown_place_is_a_plain_no_route_not_a_crash(loaded):
    answer = loaded.post("/api/campus/route", {"start": "no such room", "destination": first_room(loaded, IDS[0])})[1]
    assert answer["ok"] is False and answer["ambiguous"] is False and "no such room" in answer["error"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"start": 5, "destination": "x"},
        {"start": ["a"], "destination": "x"},
        {"start": "a", "destination": "x" * 500},
        {"start": "a", "destination": "b", "step_free": "yes"},
        {"start": "a", "destination": "b", "start_building": {"id": 1}},
        {"start": "a\x00", "destination": "b"},
    ],
)
def test_bad_route_input_is_refused(loaded, body):
    with pytest.raises(MapError):
        loaded.post("/api/campus/route", body)


def test_every_campus_endpoint_needs_a_loaded_campus(app):
    for path, body in (
        ("/api/campus/route", {"start": "a", "destination": "b"}),
        ("/api/campus/close", {"link_id": "L1", "closed": True}),
    ):
        with pytest.raises(MapError):
            app.post(path, body)
    for body in ([], "text", 5):
        with pytest.raises(MapError):
            app.post("/api/campus/load", body)
    assert app.post("/api/campus/other", {})[0] == 404


# ---------- closing links ----------


def test_close_and_open_round_trip_changes_the_route(loaded):
    before = route(loaded)
    assert before["ok"]
    _, closed = loaded.post("/api/campus/close", {"link_id": "L2", "closed": True})
    assert closed["link"]["closed"] is True and closed["state"]["closed_links"] == ["L2"]
    assert closed["route"]["ok"] is False and "L2" in closed["route"]["error"]
    assert closed["effect"]
    assert loaded.get("/api/campus", {})[1]["links"][1]["closed"] is True
    assert route(loaded)["ok"] is False
    _, reopened = loaded.post("/api/campus/close", {"link_id": "L2", "closed": False})
    assert reopened["state"]["closed_links"] == [] and reopened["route"]["ok"] is True
    assert reopened["route"]["length_m"] == before["length_m"]


def test_state_view_of_a_building_shows_the_campus_state(loaded):
    key = f"dev/{IDS[0]}"
    assert loaded.get("/api/building", {"key": [key]})[1]["state"]["campus"]["route"] is None
    route(loaded)
    loaded.post("/api/campus/close", {"link_id": "L1", "closed": True})
    state = loaded.get("/api/building", {"key": [key]})[1]["state"]["campus"]
    assert state["loaded"] is True and state["closed_links"] == ["L1"]
    assert state["route"]["ok"] is False and state["key"] == "example"
    loaded.post("/api/campus/close", {"link_id": "L1", "closed": False})
    state = loaded.get("/api/building", {"key": [key]})[1]["state"]["campus"]
    assert state["closed_links"] == [] and state["route"]["ok"] and state["route"]["links_used"] == ["L1", "L2"]


@pytest.mark.parametrize("link_id", ["L99", "l1", "Covered walkway", "../L1", "", None, 1, ["L1"], "L1" * 200])
def test_forged_link_ids_are_refused(loaded, link_id):
    with pytest.raises(MapError):
        loaded.post("/api/campus/close", {"link_id": link_id, "closed": True})
    assert loaded.campus.state()["closed_links"] == []


@pytest.mark.parametrize("closed", ["true", 1, 0, None, [True]])
def test_closed_must_be_a_real_boolean(loaded, closed):
    with pytest.raises(MapError):
        loaded.post("/api/campus/close", {"link_id": "L1", "closed": closed})
    assert loaded.campus.state()["closed_links"] == []


def test_closing_is_saved_only_into_a_campus_json(app, campuses):
    app.post("/api/campus/load", {"key": JSON_KEY})
    assert app.post("/api/campus/close", {"link_id": "L1", "closed": True})[1]["saved"] is True
    assert load_campus(campuses / "campus.json", root=DATA)[0].links[0].closed is True
    before = (campuses / "links.csv").read_text(encoding="utf-8")
    app.post("/api/campus/load", {"key": CSV_KEY})
    assert app.post("/api/campus/close", {"link_id": "L1", "closed": True})[1]["saved"] is False
    assert (campuses / "links.csv").read_text(encoding="utf-8") == before  # a csv is never overwritten


def test_loading_again_starts_from_the_file(app):
    app.post("/api/campus/load", {"key": "example"})
    app.post("/api/campus/close", {"link_id": "L1", "closed": True})
    app.post("/api/campus/load", {"key": "example"})
    assert app.campus.state()["closed_links"] == [] and app.campus.state()["route"] is None


def test_connect_buildings_has_no_direct_endpoint(loaded):
    assert loaded.post("/api/campus/connect", {})[0] == 404
    assert loaded.post("/api/campus/link", {})[0] == 404


# ---------- the chat agent and the page share one campus ----------


def test_chat_session_and_page_share_the_campus_state(app, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")  # no request is sent in this test
    key = f"dev/{IDS[0]}"
    session = app.chat(key).ensure_session()
    assert session.campus is None and "campus_route" not in {tool.name for tool in session.tools}

    app.post("/api/campus/load", {"key": "example"})  # the page loads a campus after the chat started
    session = app.chat(key).ensure_session()
    holder = app.campus.holder
    assert session.campus is holder
    tools = {tool.name: tool for tool in session.tools}
    assert {"campus_route", "list_buildings", "close_link"} <= set(tools)
    assert "build_from_plan" in tools  # Level 4 tools survive the rebuild

    start, destination = first_room(app, IDS[0]), first_room(app, IDS[2])
    assert json.loads(tools["campus_route"](start=start, destination=destination))["links_used"]
    app.post("/api/campus/close", {"link_id": "L2", "closed": True})  # closed on the page ...
    listing = json.loads(tools["list_buildings"]())
    assert [link["closed"] for link in listing["links"]] == [False, True]  # ... visible to the agent
    with pytest.raises(ToolError, match="L2"):
        tools["campus_route"](start=start, destination=destination)
    app.post("/api/campus/close", {"link_id": "L2", "closed": False})
    assert json.loads(tools["campus_route"](start=start, destination=destination))["links_used"]


def test_chat_closed_link_shows_on_the_page(app, monkeypatch):
    """The other direction: the holder the agent changes is the one the page reads."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")
    app.post("/api/campus/load", {"key": "example"})
    session = app.chat(f"dev/{IDS[0]}").ensure_session()
    app.campus.holder.campus.links[0].closed = True  # what confirm_campus_change does after a clear yes
    assert session.campus.campus.links[0].closed is True
    assert app.get("/api/campus", {})[1]["links"][0]["closed"] is True
    assert app.campus.state()["closed_links"] == ["L1"]


# ---------- over HTTP ----------


def test_http_round_trip(app):
    from http.server import ThreadingHTTPServer

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    except PermissionError:
        pytest.skip("local port binding is not allowed here")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path: str, body: dict | list | None = None) -> tuple[int, dict]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    try:
        assert call("/api/campus")[1]["loaded"] is False
        assert call("/api/campus/load", {"key": "example"})[1]["loaded"] is True
        assert call("/api/campus/load", {"key": "../../etc/passwd"})[0] == 400
        assert call("/api/campus/close", ["not", "an", "object"])[0] == 400
        assert call("/api/campus/close", {"link_id": "L1", "closed": True})[1]["state"]["closed_links"] == ["L1"]
        assert call("/api/campus")[1]["links"][0]["closed"] is True
    finally:
        server.shutdown()
        server.server_close()
