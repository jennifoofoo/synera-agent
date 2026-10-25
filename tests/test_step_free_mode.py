"""Step-free mode (docs/specs/step-free-mode.md): one session flag, applied in Python to every route. No API calls."""

import json
from functools import cache
from pathlib import Path

import pytest

from building_agent import routing
from building_agent.guide_tools import GuideState
from building_agent.tools import make_tools
from starter_agent.building_map import BuildingMap, MapError
from tests.conftest import DATA
from web import api
from web.server import App


def connector_kinds(bm: BuildingMap, space_path: list[str]) -> set[str]:
    return {c["kind"] for c in bm.connectors.values() if set(c["space_ids"]) & set(space_path)}


@cache
def stairs_case() -> tuple[Path, str, str]:
    """A dev building and two rooms on different floors: the normal route takes stairs, the step-free one a lift."""
    for path in sorted((DATA / "dev").glob("*/building.json")):
        bm = BuildingMap.load(path.parent)
        floors = sorted(bm.floors.values(), key=lambda floor: floor["level"])
        if len(floors) < 2:
            continue
        rooms = [space for space in bm.spaces.values() if space["type"] == "room"]
        for start in [room["id"] for room in rooms if room["floor_id"] == floors[0]["id"]][:6]:
            for end in [room["id"] for room in rooms if room["floor_id"] == floors[1]["id"]][:6]:
                try:
                    normal = routing.route(bm, start, end)
                    step_free = routing.route(bm, start, end, True)
                except MapError:
                    continue
                if "stairs" in connector_kinds(bm, normal.space_path) and connector_kinds(bm, step_free.space_path) == {
                    "lift"
                }:
                    return path.parent, start, end
    pytest.skip("no dev building where the step-free route swaps stairs for a lift")


def agent_tools(path: Path, tmp_path: Path):
    bm = BuildingMap.load(path)
    guide = GuideState()
    return bm, guide, {tool.name: tool for tool in make_tools(bm, tmp_path, guide)}


def test_set_step_free_only_sets_the_flag(tmp_path):
    path, _, _ = stairs_case()
    _, guide, tools = agent_tools(path, tmp_path)
    assert json.loads(tools["set_step_free"](enabled=True)) == {"step_free": True}
    assert guide.step_free is True
    assert json.loads(tools["set_step_free"](enabled=False)) == {"step_free": False}
    assert guide.step_free is False


@pytest.mark.parametrize("tool", ["find_route", "give_directions"])
def test_flag_makes_routes_step_free_even_without_the_argument(tmp_path, tool):
    path, start, end = stairs_case()
    bm, _, tools = agent_tools(path, tmp_path)
    normal = json.loads(tools[tool](start=start, destination=end))
    assert normal["step_free"] is False and "normal_route_length_m" not in normal
    assert "stairs" in connector_kinds(bm, bm.last_route.space_path)

    tools["set_step_free"](enabled=True)
    result = json.loads(tools[tool](start=start, destination=end, step_free=False))
    assert result["step_free"] is True
    kinds = connector_kinds(bm, bm.last_route.space_path)
    assert "lift" in kinds and "stairs" not in kinds
    assert result["normal_route_length_m"] == normal["length_m"]
    assert result["length_m"] >= normal["length_m"]

    tools["set_step_free"](enabled=False)
    again = json.loads(tools[tool](start=start, destination=end))
    assert again["step_free"] is False and again["length_m"] == normal["length_m"]


def test_page_route_respects_the_session_flag():
    path, start, end = stairs_case()
    session = api.Session("dev/x", path, api.RecordingMap.load(path))
    plain = api.route_view(session, start, end)
    assert plain["step_free"] is False
    session.step_free = True
    view = api.route_view(session, start, end, step_free=False)
    assert view["step_free"] is True and session.route_request["step_free"] is True
    kinds = connector_kinds(session.map, view["space_path"])
    assert "lift" in kinds and "stairs" not in kinds
    assert api.state_view(session)["step_free"] is True


def test_step_free_endpoint_and_state_view(tmp_path):
    path, start, end = stairs_case()
    app = App(DATA, knowledge_root=tmp_path / "knowledge")
    key = path.relative_to(DATA).as_posix()
    assert app.session(key) and api.state_view(app.session(key))["step_free"] is False
    _, on = app.post("/api/step_free", {"building": key, "enabled": True})
    assert on["state"]["step_free"] is True
    _, routed = app.post("/api/route", {"building": key, "start": start, "destination": end})
    assert routed["route"]["step_free"] is True
    _, off = app.post("/api/step_free", {"building": key, "enabled": False})
    assert off["state"]["step_free"] is False
    _, plain = app.post("/api/route", {"building": key, "start": start, "destination": end})
    assert plain["route"]["step_free"] is False


def test_page_flag_reaches_a_chat_agent_created_later(tmp_path):
    path, _, _ = stairs_case()
    app = App(DATA, knowledge_root=tmp_path / "knowledge")
    key = path.relative_to(DATA).as_posix()
    app.post("/api/step_free", {"building": key, "enabled": True})
    chat = app.chat(key)
    assert chat.step_free_start is True  # no agent yet: the page value waits for it
    assert chat.ensure_session().guide.step_free is True
