"""Smoke test for the 2D page's JSON API (web/). No API calls; the chat is only checked without a key."""

import itertools
import json
import threading
import urllib.request
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from web.server import App, make_handler

DATA = Path("data")


def multi_floor_building_with_lift() -> str:
    """First dev building with a step-free lift serving two or more floors (chosen from data, not hard-coded)."""
    for path in sorted((DATA / "dev").glob("*/building.json")):
        building = json.loads(path.read_text(encoding="utf-8"))
        if any(
            c["kind"] == "lift" and c["step_free"] and len(c["floor_ids"]) >= 2 for c in building["vertical_connectors"]
        ):
            return path.parent.relative_to(DATA).as_posix()
    pytest.skip("no dev building with a lift")


@pytest.fixture
def app() -> App:
    return App(DATA)


@pytest.fixture
def key() -> str:
    return multi_floor_building_with_lift()


def rooms_on_lift_floors(app: App, key: str) -> tuple[str, str]:
    bm = app.session(key).map
    lift = next(c for c in bm.connectors.values() if c["kind"] == "lift" and c["step_free"])
    low, high = lift["floor_ids"][0], lift["floor_ids"][-1]
    start = next(s["id"] for s in bm.spaces.values() if s["floor_id"] == low and s["type"] == "room")
    end = next(s["id"] for s in bm.spaces.values() if s["floor_id"] == high and s["type"] == "room")
    return start, end


def test_building_list_and_unknown_keys_are_refused(app, key):
    status, payload = app.get("/api/buildings", {})
    assert status == 200
    assert key in {b["key"] for b in payload["buildings"]}
    for bad in ("../..", "dev/../../etc", "dev/does-not-exist"):
        with pytest.raises(ValueError):
            app.get("/api/building", {"key": [bad]})


def test_building_view_has_everything_the_page_draws(app, key):
    status, view = app.get("/api/building", {"key": [key]})
    assert status == 200
    bm = app.session(key).map
    assert [f["level"] for f in view["floors"]] == sorted(f["level"] for f in bm.floors.values())
    assert len(view["spaces"]) == len(bm.spaces)
    assert all(len(s["polygon"]) >= 3 and len(s["anchor"]) == 2 for s in view["spaces"])
    assert len(view["openings"]) == len(bm.openings)
    assert {c["id"] for c in view["connectors"]} == set(bm.connectors)
    assert view["state"] == {"closed": [], "added_doors": [], "route": None}


def test_step_free_route_across_floors_then_lift_closure_reroutes(app, key):
    start, end = rooms_on_lift_floors(app, key)
    _, payload = app.post("/api/route", {"building": key, "start": start, "destination": end, "step_free": True})
    route = payload["route"]
    assert route["ok"], route
    expected = app.session(key).map.route(start, end, step_free=True).length_m
    assert route["length_m"] == expected
    assert route["space_path"][0] == start and route["space_path"][-1] == end
    assert route["floor_changes"], "a route between floors must change floor"
    assert all(change["kind"] == "lift" for change in route["floor_changes"])
    assert {segment["floor_id"] for segment in route["segments"]} == set(route["floors"])
    assert route["floors"][0] != route["floors"][-1]

    used_lift = route["floor_changes"][0]["connector_id"]
    _, closed = app.post("/api/close", {"building": key, "element": used_lift, "closed": True})
    assert closed["state"]["closed"] == [used_lift]
    after = closed["state"]["route"]
    if after["ok"]:
        assert used_lift not in {change["connector_id"] for change in after["floor_changes"]}
        assert after["length_m"] >= route["length_m"]
    else:
        assert "No step-free route" in after["error"]

    _, reopened = app.post("/api/close", {"building": key, "element": used_lift, "closed": False})
    assert reopened["state"]["route"]["length_m"] == route["length_m"]


def test_unknown_place_returns_a_readable_error(app, key):
    _, payload = app.post("/api/route", {"building": key, "start": "no such room 9.99", "destination": "x"})
    assert payload["route"]["ok"] is False
    assert payload["route"]["error"]


def neighbours_without_door(app: App, key: str) -> tuple[str, str]:
    bm = app.session(key).map
    joined = {frozenset(o["space_ids"]) for o in bm.openings.values()}
    rooms = [s for s in bm.spaces.values() if s["type"] == "room"]
    for first, second in itertools.combinations(rooms, 2):
        if first["floor_id"] != second["floor_id"] or frozenset((first["id"], second["id"])) in joined:
            continue
        if Polygon(first["polygon"]).distance(Polygon(second["polygon"])) <= 0.1:
            return first["id"], second["id"]
    pytest.skip("no neighbouring rooms without a door")


def test_added_door_is_drawn_and_used_then_reset_clears_everything(app, key):
    first, second = neighbours_without_door(app, key)
    _, before = app.post("/api/route", {"building": key, "start": first, "destination": second})
    _, added = app.post("/api/door", {"building": key, "first": first, "second": second})
    door = added["door"]
    assert set(door["space_ids"]) == {first, second}
    assert [d["id"] for d in added["state"]["added_doors"]] == [door["id"]]
    after = added["state"]["route"]
    assert after["ok"] and after["length_m"] <= before["route"]["length_m"]
    assert after["space_path"] == [first, second]

    _, view = app.get("/api/building", {"key": [key]})
    assert any(o["id"] == door["id"] and o["added"] for o in view["openings"])

    _, reset = app.post("/api/reset", {"building": key})
    assert reset["state"] == {"closed": [], "added_doors": [], "route": None}
    assert all(not o["added"] for o in reset["openings"])


def test_chat_without_key_explains_instead_of_failing(app, key, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _, status = app.get("/api/status", {})
    assert status["chat_available"] is False
    _, reply = app.post("/api/chat", {"building": key, "message": "where is the toilet?"})
    assert reply["error"] == "no_api_key"
    assert "ANTHROPIC_API_KEY" in reply["reply"]


def test_http_round_trip(app, key):
    from http.server import ThreadingHTTPServer

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    except PermissionError:
        pytest.skip("local port binding is not allowed here")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/") as response:
            assert b"Talk to Your Building" in response.read()
        with urllib.request.urlopen(f"{base}/api/building?key={key}") as response:
            assert json.loads(response.read())["key"] == key
        start, end = rooms_on_lift_floors(app, key)
        request = urllib.request.Request(
            f"{base}/api/route",
            data=json.dumps({"building": key, "start": start, "destination": end}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            assert json.loads(response.read())["route"]["ok"]
    finally:
        server.shutdown()
        server.server_close()


# ---------- chat and page at the same time (fake agent, no API) ----------


def fake_chat(app: App, key: str, monkeypatch, during_ask) -> None:
    """Chat on with a fake agent: ask() runs `during_ask(map)` the way the real agent would use the shared map."""
    monkeypatch.setattr("web.server.chat_available", lambda: True)
    monkeypatch.setattr("web.chat.chat_available", lambda: True)

    def ask(adapter, text: str) -> dict:
        during_ask(adapter.map)
        return {"reply": "done", "backend": "fake"}

    monkeypatch.setattr("web.chat.ChatAdapter.ask", ask)


def test_agent_route_is_drawn_with_its_via_stops(app, key, monkeypatch):
    start, end = rooms_on_lift_floors(app, key)
    bm = app.session(key).map
    via = next(
        s["id"] for s in bm.spaces.values() if s["floor_id"] == bm.spaces[start]["floor_id"] and s["id"] != start
    )
    fake_chat(app, key, monkeypatch, lambda m: m.route(start, end, False, [via]))
    _, reply = app.post("/api/chat", {"building": key, "message": "take me there via the other room"})
    route = reply["state"]["route"]
    assert route["ok"] and route["via"] == [via] and via in route["space_path"]


def test_page_route_asked_during_chat_wins_over_the_agent_route(app, key, monkeypatch):
    start, end = rooms_on_lift_floors(app, key)

    def agent_then_page(m):
        m.route(start, end, False, None)  # the agent routes first ...
        app.post("/api/route", {"building": key, "start": end, "destination": start})  # ... the page asks later

    fake_chat(app, key, monkeypatch, agent_then_page)
    _, reply = app.post("/api/chat", {"building": key, "message": "route me"})
    assert (reply["state"]["route"]["start"], reply["state"]["route"]["destination"]) == (end, start)


def test_page_routing_leaves_the_agent_route_slot_alone(app, key):
    start, end = rooms_on_lift_floors(app, key)
    bm = app.session(key).map
    agent_route = bm.route(start, end)
    app.post("/api/route", {"building": key, "start": end, "destination": start})
    app.get("/api/building", {"key": [key]})  # redraws the page route
    assert bm.last_route is agent_route


def test_reset_during_chat_returns_the_fresh_building(app, key, monkeypatch):
    start, end = rooms_on_lift_floors(app, key)

    def agent_closes_then_page_resets(m):
        lift = next(c["id"] for c in m.connectors.values() if c["kind"] == "lift")
        m.set_closed(lift, True)
        m.route(start, end, False, None)
        app.post("/api/reset", {"building": key})

    fake_chat(app, key, monkeypatch, agent_closes_then_page_resets)
    _, reply = app.post("/api/chat", {"building": key, "message": "close the lift"})
    assert reply["stale"] is True
    assert reply["state"] == {"closed": [], "added_doors": [], "route": None}
