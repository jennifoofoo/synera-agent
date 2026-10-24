"""The page keeps up with the agent's edits: server fields in /api/chat and /api/building after fake agent edits (no
API calls), and the renderer (web/static/edits.js plus its hooks) handles each field, also after undo."""

import json
import re
from pathlib import Path

import pytest

from building_agent import edit_ops
from starter_agent.building_map import MapError
from web.server import App

DATA = Path("data")
STATIC = Path("web/static")


@pytest.fixture
def app() -> App:
    return App(DATA)


@pytest.fixture
def key() -> str:
    keys = sorted(p.parent.relative_to(DATA).as_posix() for p in (DATA / "dev").glob("*/building.json"))
    if not keys:
        pytest.skip("no dev data")
    return keys[0]


def fake_chat(app: App, monkeypatch, during_ask) -> None:
    monkeypatch.setattr("web.server.chat_available", lambda: True)
    monkeypatch.setattr("web.chat.chat_available", lambda: True)

    def ask(adapter, text: str) -> dict:
        during_ask(adapter.map)
        return {"reply": "done", "backend": "fake"}

    monkeypatch.setattr("web.chat.ChatAdapter.ask", ask)


def edit_everything(bm) -> dict:
    """Add a chair, move an asset, remove an asset, remove one door, widen another; returns the ids touched."""
    room = next(s for s in bm.spaces.values() if s["type"] == "room")
    ids = {"added": edit_ops.add_asset(bm, "chair", room["id"], {"anchor": "NW"})["id"]}
    others = [a for a in bm.assets.values() if a["id"] != ids["added"]]
    for asset in others:
        targets = [
            s["id"]
            for s in bm.spaces.values()
            if s["type"] == "room" and s["floor_id"] == asset["floor_id"] and s["id"] != asset["space_id"]
        ]
        for target in targets:
            try:
                edit_ops.move_asset(bm, asset["id"], target)
            except MapError:
                continue
            ids["moved"] = asset["id"]
            break
        if "moved" in ids:
            break
    victim = next(a for a in bm.assets.values() if a["id"] not in ids.values())
    # no remove-asset operation exists yet: write what one will leave on the map (same shape restore_snapshot uses)
    del bm.assets[victim["id"]]
    bm.data["assets"][:] = [a for a in bm.data["assets"] if a["id"] != victim["id"]]
    bm.removed_assets = [*getattr(bm, "removed_assets", []), victim["id"]]
    ids["removed"] = victim["id"]
    doors = [o for o in bm.openings.values() if o["kind"] == "door" and not edit_ops.is_entrance(o)]
    ids["removed_opening"] = edit_ops.remove_door(bm, doors[0]["id"])["id"]
    ids["widened"] = edit_ops.widen_door(bm, doors[1]["id"], None, 1.6)["id"]
    return ids


def test_chat_reply_and_building_carry_every_edit_field(app, key, monkeypatch):
    touched = {}
    fake_chat(app, monkeypatch, lambda bm: touched.update(edit_everything(bm)))
    _, reply = app.post("/api/chat", {"building": key, "message": "rearrange"})
    for state in (reply["state"], app.get("/api/building", {"key": [key]})[1]["state"]):
        json.dumps(state)
        assert touched["added"] in state["added_assets"]
        assert state["added_assets"][touched["added"]]["type"] == "chair"
        assert touched["moved"] in state["moved_assets"]
        assert touched["removed"] in state["removed_assets"]
        assert state["removed_openings"] == [touched["removed_opening"]]
        assert state["widened_openings"] == {touched["widened"]: 1.6}


def test_undo_of_an_added_asset_lists_it_as_removed(app, key, monkeypatch):
    snapshots = {}

    def add(bm):
        room = next(s for s in bm.spaces.values() if s["type"] == "room")
        snapshots["snap"] = edit_ops.take_snapshot(bm, "add")
        snapshots["id"] = edit_ops.add_asset(bm, "chair", room["id"], {"anchor": "NW"})["id"]

    fake_chat(app, monkeypatch, add)
    _, reply = app.post("/api/chat", {"building": key, "message": "add a chair"})
    assert snapshots["id"] in reply["state"]["added_assets"]
    fake_chat(app, monkeypatch, lambda bm: edit_ops.restore_snapshot(bm, snapshots["snap"]))
    _, reply = app.post("/api/chat", {"building": key, "message": "undo"})
    assert reply["state"]["removed_assets"] == [snapshots["id"]]
    assert "added_assets" not in reply["state"]


# ---------- the renderer ----------


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_renderer_handles_each_state_field():
    edits = source("edits.js")
    for field in ("added_assets", "moved_assets", "removed_assets", "removed_openings", "widened_openings"):
        assert field in edits, field
    assert "width_label" in edits and "→" in edits  # "1.2 → 1.6 m"
    for kind in ("added", "moved", "removed", "removed-door", "widened"):
        assert f'kind: "{kind}"' in edits, kind


def test_page_wires_the_edits_into_2d_3d_and_changes_list():
    html, app_js = source("index.html"), source("app.js")
    assert html.index('src="app.js"') < html.index('src="edits.js"') < html.index('src="view3d.js"')
    assert 'id="edit-list"' in html
    assert "window.edits?.apply(state" in app_js  # every state from the server, also after undo and reset
    for hook in ("assetClass", "glide", "drawEffects", "decorateOpening", "count"):
        assert f"window.edits?.{hook}(" in app_js, hook
    view3d, scene3d = source("view3d.js"), source("scene3d.js")
    assert "window.edits.state.version" in view3d and "scene.setEditMarks(" in view3d
    assert "setEditMarks(" in scene3d and "editMarkMeshes(" in scene3d


def test_motion_respects_reduced_motion():
    css = source("style.css")
    reduced = css[css.index("@media (prefers-reduced-motion: reduce)") :]
    for cls in (".asset-glide", ".asset-ghost", ".asset-fade", ".asset-new-ring"):
        assert cls in reduced.split("}")[0], cls
    assert 'matchMedia("(prefers-reduced-motion: reduce)")' in source("edits.js")


def test_changes_rows_are_plain_words_with_the_room():
    edits = source("edits.js")
    assert re.search(r"Moved \$\{a\.name\} \$\{where\}", edits)
    assert "names.space(" in edits and "focusPoint(row.floor_id" in edits
