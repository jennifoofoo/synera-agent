"""Smoke test for the 2D page's JSON API (web/). No API calls; the chat is only checked without a key."""

import itertools
import json
import threading
import urllib.request
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from building_agent import routing
from building_agent.round_tools import plan_round
from web.server import App, make_handler

DATA = Path("data")
NO_CAMPUS_STATE = {
    "campus": {"loaded": False, "key": None, "name": None, "route": None, "closed_links": []},
    "facts": [],  # place knowledge (docs/specs/place-knowledge.md): none in a fresh tmp store
    "closed_until": {},
}


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
def app(tmp_path) -> App:
    return App(DATA, knowledge_root=tmp_path / "knowledge")


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
    assert view["state"] == {
        "closed": [],
        "added_doors": [],
        "route": None,
        "position": None,
        "guide": None,
        "campus": {"loaded": False, "key": None, "name": None, "route": None, "closed_links": []},
        "facts": [],
        "closed_until": {},
    }


def test_step_free_route_across_floors_then_lift_closure_reroutes(app, key):
    start, end = rooms_on_lift_floors(app, key)
    _, payload = app.post("/api/route", {"building": key, "start": start, "destination": end, "step_free": True})
    route = payload["route"]
    assert route["ok"], route
    expected = routing.route(app.session(key).map, start, end, step_free=True).length_m
    assert route["length_m"] == expected and route["model"] == "people"
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
    assert reset["state"] == {
        **NO_CAMPUS_STATE,
        "closed": [],
        "added_doors": [],
        "route": None,
        "position": None,
        "guide": None,
    }
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
        from web.server import STATIC

        if (STATIC / "index.html").is_file():  # the page is the twin's build (cd twin && npm run build)
            with urllib.request.urlopen(f"{base}/") as response:
                assert b"Building Twin" in response.read()
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
    fake_chat(app, key, monkeypatch, lambda m: routing.route(m, start, end, False, [via]))
    _, reply = app.post("/api/chat", {"building": key, "message": "take me there via the other room"})
    route = reply["state"]["route"]
    assert route["ok"] and route["via"] == [via] and via in route["space_path"]


def test_agent_round_carries_its_stops_for_the_page(app, monkeypatch):
    """plan_round's route reaches the page with route.round (stops in order), so the page guides it stop by stop;
    the page's own next route has no round."""
    key = "dev/proc-factory-dev-003"
    bm = app.session(key).map
    start = next(s["id"] for s in bm.spaces.values() if s["name"] == "Main aisle H-B5")
    planned = {}
    fake_chat(app, key, monkeypatch, lambda m: planned.update(plan_round(m, "fire extinguisher", start, floor_level=0)))
    _, reply = app.post("/api/chat", {"building": key, "message": "inspection round fire extinguishers ground floor"})
    route = reply["state"]["route"]
    stops = [stop["space_id"] for stop in route["round"]["stops"]]
    assert stops == [stop["space_id"] for stop in planned["stops"]]
    assert route["round"]["start"] == start and route["via"] == stops[:-1] and route["destination"] == stops[-1]
    assert all(route["round"]["stops"][0]["asset_ids"])
    _, page = app.post("/api/route", {"building": key, "start": stops[0], "destination": stops[1]})
    assert "round" not in page["state"]["route"]


def test_round_endpoint_plans_like_the_agent_and_draws_the_round(app):
    """POST /api/round runs plan_round (same order and metres as the chat) and draws it with route.round."""
    key = "dev/proc-factory-dev-003"
    bm = app.session(key).map
    start = next(s["id"] for s in bm.spaces.values() if s["name"] == "Main aisle H-B5")
    expected = plan_round(bm, "fire extinguisher", start, floor_level=0)
    _, reply = app.post(
        "/api/round", {"building": key, "type": "fire extinguisher", "area": "Ground floor", "start": start}
    )
    planned = reply["round"]
    assert planned["ok"] and [s["space_id"] for s in planned["stops"]] == [s["space_id"] for s in expected["stops"]]
    assert planned["total_m"] == expected["total_m"]
    route = reply["state"]["route"]
    stops = [stop["space_id"] for stop in route["round"]["stops"]]
    assert route["start"] == start and route["via"] == stops[:-1] and route["destination"] == stops[-1]
    _, bad = app.post("/api/round", {"building": key, "type": "unicorn", "start": start})
    assert bad["round"]["ok"] is False and bad["round"]["error"]


def test_page_route_asked_during_chat_wins_over_the_agent_route(app, key, monkeypatch):
    start, end = rooms_on_lift_floors(app, key)

    def agent_then_page(m):
        routing.route(m, start, end, False, None)  # the agent routes first ...
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
    assert reply["state"] == {
        **NO_CAMPUS_STATE,
        "closed": [],
        "added_doors": [],
        "route": None,
        "position": None,
        "guide": None,
    }


# ---------- click selection through /api/chat ----------


def selection_probe(monkeypatch) -> list:
    """Fake chat that records the selection each turn sees."""
    monkeypatch.setattr("web.server.chat_available", lambda: True)
    monkeypatch.setattr("web.chat.chat_available", lambda: True)
    seen: list = []

    def ask(adapter, text: str, selection=None) -> dict:
        seen.append(selection)
        return {"reply": "ok", "backend": "fake"}

    monkeypatch.setattr("web.chat.ChatAdapter.ask", ask)
    return seen


def test_chat_passes_a_validated_selection_and_drops_an_invalid_one(app, key, monkeypatch):
    seen = selection_probe(monkeypatch)
    room = next(s for s in app.session(key).map.spaces.values() if s["type"] == "room")
    body = {"building": key, "message": "move it here", "context": {"space_id": room["id"]}}
    status, reply = app.post("/api/chat", body)
    assert status == 200 and seen[-1].space_id == room["id"] and "selection_ignored" not in reply
    status, reply = app.post("/api/chat", {"building": key, "message": "x", "context": {"space_id": "nope"}})
    assert status == 200 and seen[-1] is None and reply["selection_ignored"] == "unknown space"
    for junk in ("text", 5, [1], {"point": float("nan")}):
        status, _ = app.post("/api/chat", {"building": key, "message": "x", "context": junk})
        assert status == 200 and seen[-1] is None
    app.post("/api/chat", {"building": key, "message": "no context"})
    assert seen[-1] is None


def test_page_shaped_selection_contexts_reach_the_agent(app, key, monkeypatch):
    """The three shapes web/static/app.js builds (selectionContext): room, thing, spot."""
    seen = selection_probe(monkeypatch)
    bm = app.session(key).map
    asset = next(iter(bm.assets.values()))
    space = bm.spaces[asset["space_id"]]
    spot = list(
        __import__("shapely.geometry", fromlist=["Polygon"]).Polygon(space["polygon"]).representative_point().coords[0]
    )
    shapes = [
        ({"floor_id": space["floor_id"], "space_id": space["id"]}, (space["id"], None, None)),
        (
            {"floor_id": space["floor_id"], "space_id": space["id"], "asset_id": asset["id"]},
            (space["id"], asset["id"], None),
        ),
        ({"floor_id": space["floor_id"], "space_id": space["id"], "point": spot}, (space["id"], None, tuple(spot))),
    ]
    for context, (space_id, asset_id, point) in shapes:
        status, reply = app.post(
            "/api/chat", {"building": key, "message": "move this next to the door", "context": context}
        )
        assert status == 200 and "selection_ignored" not in reply
        got = seen[-1]
        assert (got.space_id, got.asset_id, got.point, got.floor_id) == (space_id, asset_id, point, space["floor_id"])
    status, reply = app.post(
        "/api/chat", {"building": key, "message": "x", "context": {"floor_id": "f1", "space_id": "gone"}}
    )
    assert reply["selection_ignored"] == "unknown space"  # the page shows this and keeps its chip


def test_selection_is_cleared_after_the_turn(app, key, monkeypatch):
    from types import SimpleNamespace

    from web.selection import Selection

    monkeypatch.setattr("web.chat.chat_available", lambda: True)
    monkeypatch.setattr("web.chat.backend_name", lambda: "building_agent")
    during = []
    guide = SimpleNamespace(selection="unset")

    def ask(text: str) -> str:
        during.append(guide.selection)
        return "ok"

    adapter = app.chat(key)
    adapter.session = SimpleNamespace(guide=guide, ask=ask, tools=[])
    adapter.level4 = None
    selection = Selection(space_id="s")
    adapter.ask("here", selection=selection)
    adapter.ask("again")
    assert during == [selection, None] and guide.selection is None
    adapter.session.ask = lambda text: (_ for _ in ()).throw(RuntimeError("boom"))
    assert adapter.ask("fail", selection=selection)["error"] == "agent" and guide.selection is None


# ---------- finds and saved buildings in the chat reply (fake agent, no API) ----------


def test_chat_reply_carries_what_the_agent_located(app, key, monkeypatch):
    bm = app.session(key).map
    asset = next(iter(bm.assets.values()))

    def agent_finds(m):
        m.located_asset_ids = [asset["id"]]

    fake_chat(app, key, monkeypatch, agent_finds)
    _, reply = app.post("/api/chat", {"building": key, "message": "where is it?"})
    assert [entry["asset_id"] for entry in reply["located"]] == [asset["id"]]
    assert reply["located"][0]["space_id"] == asset["space_id"]
    fake_chat(app, key, monkeypatch, lambda m: None)
    _, again = app.post("/api/chat", {"building": key, "message": "and the weather?"})  # nothing found this turn
    assert again["located"] == []


def test_agent_saving_a_building_in_the_chat_opens_it_on_the_page(tmp_path, key, monkeypatch):
    from starter_agent.building_map import BuildingMap

    app = App(DATA, tmp_path / "uploads", tmp_path / "buildings")
    source = DATA / key / "building.json"
    monkeypatch.setattr("web.server.chat_available", lambda: True)
    monkeypatch.setattr("web.chat.chat_available", lambda: True)
    monkeypatch.setattr("web.chat.backend_name", lambda: "building_agent")

    class FakeSession:
        """What building_agent.agent.Session does on save_building: write the file, call swap_building(path)."""

        def __init__(self, building_map, output_directory, **options):
            """options: campus and knowledge (the page's shared fact store), passed through since place knowledge."""
            from types import SimpleNamespace

            self.map, self.tools = building_map, []
            self.guide = SimpleNamespace(selection=None)  # the click selection slot the adapter sets per turn

        def install_building(self, building_map):
            self.map = building_map

        def swap_building(self, path):
            self.install_building(BuildingMap.load(Path(path)))

        def ask(self, text):
            target = tmp_path / "buildings" / "drawn-1" / "building.json"
            target.parent.mkdir(parents=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            self.swap_building(target)
            return "Saved."

    monkeypatch.setattr("building_agent.agent.Session", FakeSession)
    _, reply = app.post("/api/chat", {"building": key, "message": "save it"})
    assert reply["opened"] == "user/drawn-1" and "saved_path" not in reply
    status, view = app.get("/api/building", {"key": [reply["opened"]]})
    assert status == 200 and view["spaces"]
    chat = app.chats[reply["opened"]]
    assert chat.map is app.session(reply["opened"]).map and chat.session.map is chat.map  # one map for page and chat
    assert key not in app.chats or app.chats[key].session is None
    bm = chat.map
    rooms = [s["id"] for s in bm.spaces.values() if s["type"] == "room"]
    status, routed = app.post("/api/route", {"building": reply["opened"], "start": rooms[0], "destination": rooms[-1]})
    assert status == 200 and "route" in routed


def test_short_walks_fold_into_the_next_walk():
    from web.api import merge_short_walks

    steps = [
        "Start in Office 1.01 on Floor 1.",
        "Walk about 1 m through the door into Corridor 1.02.",
        "Walk about 2 m through the opening into Landing 0.07.",
        "Walk about 11 m through the door into Kitchen 1.06.",
        "Walk about 3 m. You have arrived at Kitchen 1.06.",
    ]
    assert merge_short_walks(steps) == [
        "Start in Office 1.01 on Floor 1.",
        "Walk about 14 m via Corridor 1.02, Landing 0.07 into Kitchen 1.06.",
        "Walk about 3 m. You have arrived at Kitchen 1.06.",
    ]


def test_a_short_walk_before_a_stair_stays_its_own_line():
    from web.api import merge_short_walks

    steps = ["Start in A.", "Walk about 1 m through the door into Stairwell 1.", "Take Stairs 1 (stairs) to Floor 2."]
    assert merge_short_walks(steps) == [
        "Start in A.",
        "Walk about 1 m into Stairwell 1.",
        "Take Stairs 1 (stairs) to Floor 2.",
    ]


def test_no_route_message_for_the_page_names_closures_without_ids():
    from pathlib import Path

    from starter_agent.building_map import BuildingMap
    from web.api import readable_error

    bm = BuildingMap.load(Path("data/dev/proc-factory-dev-012"))
    text = (
        "No route from Warehouse zone H-B3 [proc-factory-dev-012-F0-S009] on Ground floor to Kitchen 2.21 "
        "[proc-factory-dev-012-F2-S021] on Floor 2 with the current closures ['proc-factory-dev-012-V01']. "
        "There is no way round the outside of the building."
    )
    message = readable_error(bm, text)
    assert "[" not in message and "proc-factory" not in message
    assert "because of closures: Office staircase" in message


def test_tunnel_origin_is_allowed_only_when_switched_on_and_same_origin(monkeypatch):
    from web import server

    monkeypatch.setattr(server, "TUNNEL_SUFFIXES", ())
    assert not server.tunnel_origin("https://a-b.trycloudflare.com", "a-b.trycloudflare.com")
    monkeypatch.setattr(server, "TUNNEL_SUFFIXES", (".trycloudflare.com",))
    assert server.tunnel_origin("https://a-b.trycloudflare.com", "a-b.trycloudflare.com")
    assert not server.tunnel_origin("https://a-b.trycloudflare.com", "evil.example.com")
    assert not server.tunnel_origin("http://a-b.trycloudflare.com", "a-b.trycloudflare.com")
    assert not server.tunnel_origin("https://evil.example.com", "evil.example.com")
