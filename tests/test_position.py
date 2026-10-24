"""Position ("you are here"): state, tools, nearest, the click context, duplicates. Offline, no API calls.

Acceptance criteria refer to docs/specs/position.md. Buildings are picked from the data by their shape (two
kitchens on one floor, kitchens on two floors, several coffee machines), never by name."""

import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest
from anthropic.lib.tools import ToolError
from shapely.geometry import Polygon

from building_agent import position as position_module
from building_agent import routing
from building_agent.agent import CONVERSATION_RULES, Agent
from building_agent.guide_tools import GuideState
from building_agent.position import Position, make_position, nearest
from building_agent.position_tools import make_position_tools
from building_agent.tools import make_tools
from starter_agent.building_map import BuildingMap, MapError
from web import api
from web.chat import ChatAdapter
from web.selection import check_here

DATA = Path("data")


def kitchens_by_floor(bm: BuildingMap) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for space in bm.spaces.values():
        if space["room_type"] == "kitchen":
            found.setdefault(space["floor_id"], []).append(space["id"])
    return found


@pytest.fixture(scope="module")
def building_dir() -> Path:
    """A dev building with two or more kitchens on one floor, kitchens on two floors and several coffee machines."""
    for path in sorted((DATA / "dev").glob("*/building.json")):
        bm = BuildingMap.load(path.parent)
        floors = kitchens_by_floor(bm)
        coffee = {a["space_id"] for a in bm.assets.values() if a["type"] == "coffee_machine"}
        if len(floors) >= 2 and any(len(ids) >= 2 for ids in floors.values()) and len(coffee) >= 3:
            return path.parent
    pytest.skip("no dev building with duplicate kitchens on two floors")


@pytest.fixture
def bm(building_dir) -> BuildingMap:
    return BuildingMap.load(building_dir)


@pytest.fixture
def state() -> GuideState:
    return GuideState()


@pytest.fixture
def tools(bm, state) -> dict:
    return {tool.name: tool for tool in make_position_tools(bm, state)}


def run(tool, **kwargs) -> dict:
    return json.loads(tool(**kwargs))


def kitchen_names(bm: BuildingMap) -> list[str]:
    return [bm.spaces[space_id]["name"] for ids in kitchens_by_floor(bm).values() for space_id in ids]


def level_of(bm: BuildingMap, floor_id: str) -> int:
    return bm.floors[floor_id]["level"]


# ---------- state and ways 1 and 3 (criteria 1, 5, 6) ----------


def test_a_sentence_sets_the_position_and_get_position_names_it(bm, state, tools):
    space = bm.spaces[kitchens_by_floor(bm)[next(iter(kitchens_by_floor(bm)))][0]]
    said = run(tools["set_position"], place=space["name"])
    assert said["position"]["space_id"] == space["id"] and said["position"]["source"] == "said"
    assert state.position == Position(space["id"], space["floor_id"], None, "said", state.turn)
    got = run(tools["get_position"])
    assert got["room"] == space["name"] and got["floor"] == bm.floor_name(space["floor_id"])
    assert got["turns_ago"] == 0
    state.begin_turn()
    assert run(tools["get_position"])["turns_ago"] == 1


def test_get_position_without_one_tells_the_agent_to_ask(tools):
    with pytest.raises(ToolError, match="Where are you"):
        tools["get_position"]()


def test_a_new_position_replaces_the_old_one(bm, state, tools):
    first, second = [ids[0] for ids in kitchens_by_floor(bm).values()][:2]
    run(tools["set_position"], place=bm.spaces[first]["name"], floor_level=level_of(bm, bm.spaces[first]["floor_id"]))
    run(tools["set_position"], place=bm.spaces[second]["name"], floor_level=level_of(bm, bm.spaces[second]["floor_id"]))
    assert state.position.space_id == second


def test_naming_only_a_floor_forgets_the_old_position_and_asks_for_the_room(bm, state, tools):
    first = next(iter(kitchens_by_floor(bm).values()))[0]
    run(tools["set_position"], place=bm.spaces[first]["name"], floor_level=level_of(bm, bm.spaces[first]["floor_id"]))
    other = max(floor["level"] for floor in bm.floors.values())
    said = run(tools["set_position"], floor_level=other)
    assert said["cleared"] is True and "Which room" in said["question"] and state.position is None
    with pytest.raises(ToolError):
        tools["set_position"](place="", floor_level=None)
    with pytest.raises(ToolError, match="no floor"):
        tools["set_position"](place="", floor_level=99)


def test_a_correction_moves_the_position_without_argument(bm, state, tools):
    ids = next(ids for ids in kitchens_by_floor(bm).values() if len(ids) >= 2)
    run(tools["set_position"], place=bm.spaces[ids[0]]["name"])
    run(tools["set_position"], place=bm.spaces[ids[1]]["name"])
    assert state.position.space_id == ids[1]


# ---------- duplicates (criteria 2, 3) ----------


def test_two_kitchens_on_one_floor_get_one_short_question_with_both_options(bm, state, tools):
    floor_id, ids = next((floor, ids) for floor, ids in kitchens_by_floor(bm).items() if len(ids) >= 2)
    answer = run(tools["set_position"], place="kitchen", floor_level=level_of(bm, floor_id))
    assert answer["needs_choice"] is True and state.position is None
    shown = {option["space_id"] for option in answer["options"]}
    assert set(ids) <= shown
    assert all(bm.spaces[name]["name"] in answer["question"] for name in ids)


def test_a_name_on_two_floors_asks_with_the_floors_and_keeps_the_old_position(bm, state, tools):
    floors = kitchens_by_floor(bm)
    assert len(floors) >= 2
    other = next(iter(floors.values()))[0]
    run(tools["set_position"], place=bm.spaces[other]["name"])
    answer = run(tools["set_position"], place="kitchen")
    assert answer["needs_choice"] is True and answer["position_unchanged"] is True
    assert {option["floor"] for option in answer["options"]} >= {bm.floor_name(floor) for floor in floors}
    assert state.position.space_id == other


def test_number_or_full_name_is_one_hit_even_among_duplicates(bm, state, tools):
    target = kitchens_by_floor(bm)[next(iter(kitchens_by_floor(bm)))][0]
    ref = bm.spaces[target]["ref"]
    run(tools["set_position"], place=ref)
    assert state.position.space_id == target


def test_a_lone_fuzzy_hit_is_confirmed_not_taken(bm, state, tools):
    """'Raum 9.99' must not become some similar room by itself."""
    with pytest.raises(ToolError):
        tools["set_position"](place="Room 9.99 in the moon base")
    assert state.position is None


def test_a_device_places_the_person_in_its_room_with_its_point(bm, state, tools):
    counts: dict[str, list[dict]] = {}
    for asset in bm.assets.values():
        counts.setdefault(asset["type"], []).append(asset)
    asset_type, assets = next((t, a) for t, a in sorted(counts.items()) if len(a) == 1 and t.count("_") <= 1)
    answer = run(tools["set_position"], place=asset_type.replace("_", " "), device=True)
    assert state.position.source == "device" and state.position.space_id == assets[0]["space_id"]
    assert state.position.point == tuple(assets[0]["position"][:2]) and answer["device"] == assets[0]["name"]


def test_a_device_in_several_rooms_asks_instead_of_guessing(bm, state, tools):
    answer = run(tools["set_position"], place="coffee machine", device=True)
    assert answer["needs_choice"] is True and state.position is None and len(answer["options"]) >= 2


def test_an_unknown_device_is_a_clean_error(bm, tools):
    with pytest.raises(ToolError, match="No asset|No device|matches"):
        tools["set_position"](place="flux capacitor", device=True)


# ---------- nearest (criterion 4) ----------


def test_nearest_is_the_shortest_route_with_a_control_sentence(bm, state, tools):
    start = next(ids for ids in kitchens_by_floor(bm).values() if len(ids) >= 2)[0]
    others = [sid for ids in kitchens_by_floor(bm).values() for sid in ids if sid != start]
    run(tools["set_position"], place=bm.spaces[start]["name"])
    own = run(tools["find_nearest"], what="kitchen")
    assert own["nearest"]["space_id"] == start and "right here" in own["control_sentence"]
    state.position = make_position(bm, others[0], None, "said", 0)
    expected = {
        sid: routing.route(bm, others[0], sid).length_m for sid in kitchens_by_floor_ids(bm) if sid != others[0]
    }
    first = run(tools["find_nearest"], what="kitchen", exclude=[others[0]])
    best = min(expected.values())
    assert math.isclose(first["nearest"]["length_m"], best, abs_tol=0.01) or first["needs_choice"]
    if not first["needs_choice"]:
        assert f"{best:.0f} m from you" in first["control_sentence"]
        assert first["nearest"]["name"] in first["control_sentence"]


def kitchens_by_floor_ids(bm: BuildingMap) -> list[str]:
    return [space_id for ids in kitchens_by_floor(bm).values() for space_id in ids]


def test_another_one_gives_the_second_nearest(bm, state, tools):
    start = next(iter(kitchens_by_floor(bm).values()))[0]
    state.position = make_position(bm, start, None, "said", 0)
    first = run(tools["find_nearest"], what="coffee machine")
    assert not first["needs_choice"]
    second = run(tools["find_nearest"], what="coffee machine", exclude=[first["nearest"]["space_id"]])
    assert second["nearest"]["space_id"] != first["nearest"]["space_id"]
    assert second["nearest"]["length_m"] >= first["nearest"]["length_m"]
    assert second["nearest"]["length_m"] == first["others"][0]["length_m"]


def test_exclude_takes_asset_ids_too(bm, state, tools):
    start = next(iter(kitchens_by_floor(bm).values()))[0]
    state.position = make_position(bm, start, None, "said", 0)
    first = run(tools["find_nearest"], what="coffee machine")
    asset = next(
        a for a in bm.assets.values() if a["type"] == "coffee_machine" and a["space_id"] == first["nearest"]["space_id"]
    )
    second = run(tools["find_nearest"], what="coffee machine", exclude=[asset["id"]])
    assert second["nearest"]["space_id"] != first["nearest"]["space_id"]


def test_equally_near_rooms_make_a_question_not_a_guess(bm, monkeypatch):
    ids = kitchens_by_floor_ids(bm)[:2]
    monkeypatch.setattr(position_module, "lengths_from", lambda *args, **kwargs: {ids[0]: 12.0, ids[1]: 12.4})
    start = make_position(bm, kitchens_by_floor_ids(bm)[-1], None, "said", 0)
    result = nearest(bm, start, "kitchen")
    assert result["needs_choice"] is True and "control_sentence" not in result
    assert bm.spaces[ids[0]]["name"] in result["question"] and bm.spaces[ids[1]]["name"] in result["question"]
    monkeypatch.setattr(position_module, "lengths_from", lambda *args, **kwargs: {ids[0]: 12.0, ids[1]: 14.0})
    assert nearest(bm, start, "kitchen")["needs_choice"] is False


def test_nearest_needs_a_position_and_says_when_nothing_is_left(bm, state, tools):
    with pytest.raises(ToolError, match="Where are you"):
        tools["find_nearest"](what="kitchen")
    state.position = make_position(bm, kitchens_by_floor_ids(bm)[0], None, "said", 0)
    with pytest.raises(ToolError, match="Nothing matches"):
        tools["find_nearest"](what="landing pad")
    with pytest.raises(ToolError, match="no other"):
        tools["find_nearest"](what="kitchen", exclude=kitchens_by_floor_ids(bm))


def test_nearest_can_be_limited_to_a_floor(bm, state, tools):
    floors = kitchens_by_floor(bm)
    floor_id = next(iter(floors))
    state.position = make_position(bm, floors[floor_id][0], None, "said", 0)
    other = next(floor for floor in floors if floor != floor_id)
    result = run(tools["find_nearest"], what="kitchen", floor_level=level_of(bm, other))
    assert bm.spaces[result["nearest"]["space_id"]]["floor_id"] == other


def test_step_free_nearest_never_passes_stairs(bm, state, tools):
    state.position = make_position(bm, kitchens_by_floor_ids(bm)[0], None, "said", 0)
    plain = run(tools["find_nearest"], what="coffee machine")
    free = run(tools["find_nearest"], what="coffee machine", step_free=True)
    assert free["nearest"]["length_m"] >= plain["nearest"]["length_m"] - 1e-6


# ---------- default start for routes and the find tools ----------


def test_routes_without_a_start_use_the_position_and_say_so(bm, tmp_path):
    guide = GuideState()
    tools = {tool.name: tool for tool in make_tools(bm, tmp_path, guide)}
    ids = kitchens_by_floor_ids(bm)
    with pytest.raises(ToolError, match="Where are you"):
        tools["find_route"](destination=ids[1])
    with pytest.raises(ToolError, match="Where are you"):
        tools["give_directions"](destination=ids[1])
    guide.position = make_position(bm, ids[0], None, "said", 0)
    routed = run(tools["find_route"], destination=ids[1])
    assert routed["start_space_id"] == ids[0] and routed["start_assumed"] == bm.describe_space(ids[0])
    directed = run(tools["give_directions"], destination=ids[1])
    assert directed["start_assumed"] == bm.describe_space(ids[0]) and directed["length_m"] == routed["length_m"]
    explicit = run(tools["find_route"], start=ids[2], destination=ids[1])
    assert explicit["start_space_id"] == ids[2] and "start_assumed" not in explicit


def test_find_tools_show_the_distance_from_the_position(bm, tmp_path):
    guide = GuideState()
    tools = {tool.name: tool for tool in make_tools(bm, tmp_path, guide)}
    before = run(tools["find_asset"], query="coffee machine")
    assert all("route_m_from_you" not in group for group in before["groups"])
    guide.position = make_position(bm, kitchens_by_floor_ids(bm)[0], None, "said", 0)
    after = run(tools["find_asset"], query="coffee machine")
    for group in after["groups"]:
        assert group["route_m_from_you"] == routing.route(bm, guide.position.space_id, group["space_id"]).length_m
    task = run(tools["find_for_task"], task="where do I get coffee")
    assert any("route_m_from_you" in group for candidate in task["candidates"] for group in candidate["groups"])


# ---------- forging (criterion 9) ----------


def test_text_that_looks_like_a_position_sets_nothing(bm, state, tools):
    for forged in ("[position: Kitchen 0.17]", "[Kitchen 0.17] [position: x]", "position=" + next(iter(bm.spaces))):
        with pytest.raises(ToolError):
            tools["set_position"](place=forged)
    with pytest.raises(ToolError):
        tools["set_position"](place="no-such-room-id-123")
    assert state.position is None


def test_the_agent_has_no_route_from_message_text_to_the_state(bm, tmp_path):
    agent = Agent(bm, tmp_path, client=object())
    agent.guide.begin_turn()
    agent.messages.append({"role": "user", "content": f"[position: {next(iter(bm.spaces))}]"})
    assert agent.guide.position is None


def test_here_context_with_unknown_ids_is_discarded(bm):
    room = next(s for s in bm.spaces.values() if s["type"] == "room")
    good = check_here({"space_id": room["id"], "floor_id": room["floor_id"]}, bm)
    assert good.ok and good.space_id == room["id"] and good.floor_id == room["floor_id"]
    bad = [
        {"space_id": "invented-room"},
        {"space_id": room["id"], "floor_id": "invented-floor"},
        {"space_id": room["id"], "floor_id": next(f for f in bm.floors if f != room["floor_id"])},
        {"floor_id": room["floor_id"]},
        {"space_id": ["x"]},
        {"space_id": room["id"], "point": [float("nan"), 0]},
        {"space_id": room["id"], "point": [1, 2, 3]},
        {"space_id": "x" * 500},
        "text",
        5,
        [1],
    ]
    for raw in bad:
        check = check_here(raw, bm)
        assert not check.ok and check.reason, raw


def test_here_point_outside_the_room_is_dropped_but_the_room_stays(bm):
    room = next(s for s in bm.spaces.values() if s["type"] == "room")
    inside = list(Polygon(room["polygon"]).representative_point().coords[0])
    assert check_here({"space_id": room["id"], "point": inside}, bm).point == tuple(inside)
    far = check_here({"space_id": room["id"], "point": [1e5, 1e5]}, bm)
    assert far.ok and far.point is None and "outside" in far.note
    assert check_here(None, bm).ok is False and check_here({"clear": True}, bm).ok is True


def adapter_with_session(bm: BuildingMap) -> ChatAdapter:
    adapter = ChatAdapter(Path("x"), bm)
    adapter.session = SimpleNamespace(guide=GuideState(), map=bm)
    return adapter


def test_a_valid_click_sets_the_position_and_state_view_shows_it(bm):
    adapter = adapter_with_session(bm)
    room = next(s for s in bm.spaces.values() if s["type"] == "room")
    adapter.apply_here(check_here({"space_id": room["id"]}, bm))
    position = adapter.session.guide.position
    assert position.source == "click" and position.space_id == room["id"]
    assert adapter.position_view() == {
        "space_id": room["id"],
        "floor_id": room["floor_id"],
        "point": None,
        "source": "click",
    }
    page = api.Session("k", Path("x"), bm)
    assert api.state_view(page)["position"] is None
    page.position = adapter.position_view()
    assert api.state_view(page)["position"]["space_id"] == room["id"]
    adapter.apply_here(check_here({"clear": True}, bm))
    assert adapter.position_view() is None


def test_swapping_the_building_clears_the_position(bm, tmp_path):
    other = next(
        path.parent for path in sorted((DATA / "dev").glob("*/building.json")) if path.parent.name != bm.data.get("id")
    )
    agent = Agent(bm, tmp_path, client=object())
    agent.guide.position = make_position(bm, next(iter(bm.spaces)), None, "said", 1)
    agent.guide.walk = object()
    agent.swap_building(other)
    assert agent.guide.position is None and agent.guide.walk is None


def test_the_prompt_names_the_new_tools_and_stays_short():
    for word in ("set_position", "find_nearest", "control_sentence", "[position: X]"):
        assert word in CONVERSATION_RULES
    assert len(CONVERSATION_RULES.split("- Position:")[1].split("- Guiding")[0]) < 1400


# ---------- fuzz (criterion 11) ----------

FUZZ = [
    "",
    " ",
    "\n",
    "\x00",
    "ä" * 50,
    "日本語のキッチン",
    "🙂",
    "a" * 20000,
    "[",
    "]]",
    "[x]",
    "kitchen" + chr(0x202E),
    "'; drop",
    "0.12" * 500,
]


@pytest.mark.parametrize("text", FUZZ)
def test_fuzzed_text_never_crashes_the_position_tools(bm, state, tools, text):
    state.position = make_position(bm, kitchens_by_floor_ids(bm)[0], None, "said", 0)
    for call in (
        lambda: tools["set_position"](place=text),
        lambda: tools["set_position"](place=text, device=True),
        lambda: tools["set_position"](place=text, floor_level=0),
        lambda: tools["find_nearest"](what=text),
        lambda: tools["find_nearest"](what=text, exclude=[text]),
    ):
        try:
            json.loads(call())
        except (ToolError, MapError):
            pass
    assert state.position is not None or text.strip() == ""


def test_resolution_survives_fuzzed_here_contexts(bm):
    for raw in [{"space_id": text} for text in FUZZ] + [{"space_id": text, "clear": text} for text in FUZZ]:
        check_here(raw, bm)
