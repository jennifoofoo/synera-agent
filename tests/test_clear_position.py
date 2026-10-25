"""clear_position: the agent forgets the person's position (the page's dot goes away), like context.here clear."""

import json
from pathlib import Path

from building_agent.agent import CONVERSATION_RULES
from building_agent.guide_tools import GuideState
from building_agent.tools import make_tools
from starter_agent.building_map import BuildingMap
from tests.conftest import DATA


def unique_room(bm: BuildingMap) -> dict:
    names = [space["name"] for space in bm.spaces.values()]
    return next(s for s in bm.spaces.values() if s["type"] == "room" and names.count(s["name"]) == 1)


def setup(tmp_path: Path):
    path = min((DATA / "dev").glob("proc-*/building.json")).parent
    bm = BuildingMap.load(path)
    guide = GuideState()
    return bm, guide, {tool.name: tool for tool in make_tools(bm, tmp_path, guide)}


def test_clear_position_forgets_position_and_walk(tmp_path):
    bm, guide, tools = setup(tmp_path)
    room = unique_room(bm)
    assert json.loads(tools["set_position"](place=room["name"]))["position"]["space_id"] == room["id"]
    assert guide.position is not None
    result = json.loads(tools["clear_position"]())
    assert result["cleared"] is True and "Where are you now?" in result["question"]
    assert guide.position is None and guide.walk is None and guide.session is None
    assert json.loads(tools["clear_position"]())["cleared"] is False  # nothing to forget: still fine


def test_chat_position_view_is_empty_after_clear(tmp_path):
    from web.chat import ChatAdapter

    bm, _, _ = setup(tmp_path)
    chat = ChatAdapter(Path(bm.data.get("id", "x")), bm)
    session = chat.ensure_session()
    tools = {tool.name: tool for tool in session.tools}
    tools["set_position"](place=unique_room(bm)["name"])
    assert chat.position_view() is not None
    tools["clear_position"]()
    assert chat.position_view() is None  # the server copies this into state.position: the dot disappears


def test_prompt_forbids_talking_about_tools():
    assert "never talk about your tools" in CONVERSATION_RULES
    assert "clear_position" in CONVERSATION_RULES
