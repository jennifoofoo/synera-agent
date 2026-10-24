"""The page's "I'm here" context through /api/chat and the position in state_view. Offline."""

from pathlib import Path
from types import SimpleNamespace

from building_agent.guide_tools import GuideState
from tests.test_web import multi_floor_building_with_lift
from web.server import App

DATA = Path("data")


def test_chat_validates_here_and_exposes_the_position(monkeypatch):
    app, key = App(DATA), multi_floor_building_with_lift()
    monkeypatch.setattr("web.server.chat_available", lambda: True)
    monkeypatch.setattr("web.chat.chat_available", lambda: True)
    seen: list = []

    def ask(adapter, text: str, selection=None, here=None) -> dict:
        seen.append((selection, here))
        if here is not None and here.ok:
            adapter.session = SimpleNamespace(guide=GuideState(), map=adapter.map)
            adapter.apply_here(here)
        return {"reply": "ok", "backend": "fake"}

    monkeypatch.setattr("web.chat.ChatAdapter.ask", ask)
    room = next(s for s in app.session(key).map.spaces.values() if s["type"] == "room")
    status, reply = app.post(
        "/api/chat", {"building": key, "message": "hi", "context": {"here": {"space_id": room["id"]}}}
    )
    assert status == 200 and seen[-1][0] is None and seen[-1][1].space_id == room["id"]
    assert "selection_ignored" not in reply and "here_ignored" not in reply
    assert reply["state"]["position"] == {
        "space_id": room["id"],
        "floor_id": room["floor_id"],
        "point": None,
        "source": "click",
    }
    both = {"space_id": room["id"], "here": {"space_id": room["id"]}}
    app.post("/api/chat", {"building": key, "message": "hi", "context": both})
    assert seen[-1][0].space_id == room["id"] and seen[-1][1].ok


def test_forged_here_is_ignored_with_a_reason(monkeypatch):
    app, key = App(DATA), multi_floor_building_with_lift()
    monkeypatch.setattr("web.server.chat_available", lambda: True)
    monkeypatch.setattr("web.chat.chat_available", lambda: True)
    seen: list = []

    def ask(adapter, text: str, selection=None, here=None) -> dict:
        seen.append((selection, here))
        return {"reply": "ok", "backend": "fake"}

    monkeypatch.setattr("web.chat.ChatAdapter.ask", ask)
    room = next(s for s in app.session(key).map.spaces.values() if s["type"] == "room")
    for forged in ({"space_id": "invented"}, {"space_id": room["id"], "floor_id": "invented"}, "text", 5):
        status, reply = app.post("/api/chat", {"building": key, "message": "x", "context": {"here": forged}})
        assert status == 200 and seen[-1] == (None, None) and reply["here_ignored"]
        assert "selection_ignored" not in reply
    app.post("/api/chat", {"building": key, "message": "no context"})
    assert seen[-1] == (None, None)
