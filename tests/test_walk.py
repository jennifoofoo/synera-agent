"""Overview and guided walking: the state machine, the phrasings, way 4 (position along the route), closures while
guiding, the page's guide field. Offline, no API calls. Docs: docs/specs/position.md, section on the two modes."""

import copy
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from anthropic.lib.tools import ToolError

from building_agent import routing
from building_agent import walk as walking
from building_agent.guide_tools import GuideState
from building_agent.tools import make_tools
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError
from web import api
from web.chat import ChatAdapter

DATA = Path("data")


def long_route_case() -> tuple[Path, str, str]:
    """A dev building and two rooms whose route has at least 5 steps and a lift or stairs from the third step on."""
    for path in sorted((DATA / "dev").glob("*/building.json")):
        bm = BuildingMap.load(path.parent)
        rooms = sorted(s["id"] for s in bm.spaces.values() if s["type"] == "room")
        for start in rooms[:10]:
            for end in rooms[-10:]:
                if bm.spaces[start]["floor_id"] == bm.spaces[end]["floor_id"]:
                    continue
                try:
                    walk = walking.build_walk(bm, routing.route(bm, start, end))
                except MapError:
                    continue
                vertical = [i for i, step in enumerate(walk.steps) if step.startswith("Take ")]
                if len(walk.steps) >= 5 and vertical and vertical[0] >= 2 and OUTSIDE not in walk.spaces:
                    return path.parent, start, end
    pytest.skip("no building with a long multi-floor route")


@pytest.fixture(scope="module")
def case():
    return long_route_case()


@pytest.fixture
def setup(case, tmp_path):
    building, start, end = case
    bm = BuildingMap.load(building)
    state = GuideState()
    tools = {tool.name: tool for tool in make_tools(bm, tmp_path, state)}
    return bm, state, tools, start, end


def call(tools, name, **kwargs) -> dict:
    return json.loads(tools[name](**kwargs))


def guided(setup, said="guide me"):
    _bm, _state, tools, start, end = setup
    first = call(tools, "give_directions", start=start, destination=end)
    assert first["mode"] == "overview"
    step = call(tools, "walk", said=said)
    assert step["mode"] == "guided" and step["step_number"] == 1
    return first, step


def connector_ahead(bm: BuildingMap, state: GuideState) -> dict:
    ahead = state.walk.spaces[walking.room_index(state.walk) :]
    return next(c for c in bm.connectors.values() if any(room in ahead for room in c["space_ids"]))


# ---------- overview ----------


def test_a_long_route_starts_with_an_overview_and_one_offer(setup):
    _bm, state, tools, start, end = setup
    first = call(tools, "give_directions", start=start, destination=end)
    assert first["mode"] == "overview" and "steps" not in first
    assert 2 <= len(first["landmarks"]) <= 4 and first["steps_total"] >= 5
    assert first["offer"].endswith("?") and first["length_m"] > 0
    assert all("[" not in text for text in [*first["landmarks"], first["destination"], first["offer"]])
    assert state.walk.mode == "overview"


def test_short_routes_are_read_out_at_once(setup):
    bm, state, tools, _start, _end = setup
    pair = next(
        (a, b)
        for a in bm.spaces
        for b in bm.spaces
        if a != b and a != OUTSIDE and b != OUTSIDE and len(routing.route(bm, a, b).space_path) == 2
    )
    result = call(tools, "give_directions", start=pair[0], destination=pair[1])
    assert "mode" not in result and 1 <= len(result["steps"]) <= 2 and state.walk.mode == "plain"
    assert call(tools, "next_steps")["done"] is True


def test_guided_up_front_gives_only_the_first_step(setup):
    _bm, state, tools, start, end = setup
    first = call(tools, "give_directions", start=start, destination=end, guided=True)
    assert first["mode"] == "guided" and first["step_number"] == 1 and first["of"] >= 5
    assert "landmarks" not in first and not first["arrived"]
    assert state.position.space_id == start and state.position.source == "route"


def test_a_clear_yes_starts_guiding_but_ok_or_next_do_not(setup):
    _bm, state, tools, start, end = setup
    call(tools, "give_directions", start=start, destination=end)
    for not_yet in ("ok", "next", "weiter", "hmm"):
        assert call(tools, "walk", said=not_yet)["mode"] == "overview"
    assert state.walk.mode == "overview"
    assert call(tools, "walk", said="ja, gerne")["mode"] == "guided"


# ---------- guided: advance, repeat, back, how far, stop, overview, start over ----------


def test_next_repeat_back_where_stop_overview_restart(setup):
    bm, state, tools, start, end = setup
    _, first = guided(setup)
    second = call(tools, "next_steps")
    assert second["step_number"] == 2 and second["step"] != first["step"]
    assert state.position.source == "route" and state.position.space_id == walking.room_at(state.walk, 1)
    assert call(tools, "repeat_steps")["step"] == second["step"]
    assert call(tools, "walk", said="again")["step_number"] == 2
    assert call(tools, "walk", said="back")["step"] == first["step"]
    assert state.position.space_id == start
    where = call(tools, "walk", said="how far")
    assert where["step_number"] == 1 and where["metres_left"] == round(routing.route(bm, start, end).length_m)
    assert call(tools, "walk", said="overview")["mode"] == "overview"
    assert call(tools, "walk", said="yes")["mode"] == "guided"
    call(tools, "next_steps")
    assert call(tools, "walk", said="start over")["step_number"] == 1
    assert call(tools, "walk", said="stop")["mode"] == "stopped"
    assert call(tools, "walk", said="next")["mode"] == "stopped"
    assert call(tools, "walk", said="start over")["step_number"] == 1


def test_steps_have_no_ids_and_a_pace_hint(setup):
    _bm, _state, tools, _start, _end = setup
    _, step = guided(setup)
    seen = [step]
    while not seen[-1]["arrived"]:
        seen.append(call(tools, "next_steps"))
    assert all("[" not in item["step"] and "[" not in item["destination"] for item in seen)
    assert any(item["about_seconds"] for item in seen[:-1]) and seen[-1]["about_seconds"] is None
    assert all(item["about_seconds"] is None or item["about_seconds"] % 5 == 0 for item in seen)


def test_walking_to_the_end_says_arrived_and_a_further_next_does_not_crash(setup):
    _bm, state, tools, _start, end = setup
    guided(setup)
    last = None
    for _ in range(60):
        last = call(tools, "next_steps")
        if last["arrived"]:
            break
    assert last["arrived"] and last["step_number"] == last["of"] and state.position.space_id == end
    again = call(tools, "next_steps")
    assert again["arrived"] and "already there" in again["note"] and again["step_number"] == last["of"]
    assert call(tools, "walk", said="back")["step_number"] == last["of"] - 1


def test_next_without_any_route_is_a_clear_message(setup):
    _bm, _state, tools, _start, _end = setup
    for name in ("next_steps", "repeat_steps"):
        with pytest.raises(ToolError, match="No directions yet"):
            tools[name]()
    with pytest.raises(ToolError, match="No directions yet"):
        tools["walk"](said="next")


def test_back_at_the_first_step_stays_on_it(setup):
    guided(setup)
    _bm, _state, tools, *_ = setup
    assert call(tools, "walk", said="back")["step_number"] == 1


# ---------- phrasings, English and German ----------

ADVANCE = [
    "next",
    "done",
    "ok",
    "weiter",
    "I'm here",
    "I'm there",
    "arrived",
    "ich bin da",
    "und jetzt?",
    "where next",
    "what now",
    "wo geht's jetzt hin",
]
OTHERS = {
    "repeat": ["repeat", "again", "nochmal", "say that again"],
    "repeat_destination": ["where do I go again", "wo ging's nochmal hin"],
    "back": ["back", "zurück"],
    "where": ["where am I on the way", "how far", "wie weit noch"],
    "stop": ["stop", "cancel", "abbrechen"],
    "overview": ["overview", "übersicht"],
    "restart": ["start over", "von vorn"],
}


@pytest.mark.parametrize("said", ADVANCE)
def test_arrival_phrasings_advance_one_step_without_a_place(said):
    assert walking.intent(said, "guided") == "advance"


@pytest.mark.parametrize(("action", "phrases"), OTHERS.items())
def test_other_phrasings(action, phrases):
    for said in phrases:
        assert walking.intent(said, "guided") == action, said


@pytest.mark.parametrize("said", ["guide me", "walk me there", "begleite mich", "yes", "ja", "klar", "yes please"])
def test_yes_and_guide_me_start_guiding_from_the_overview(said):
    assert walking.intent(said, "overview") == "guide"


@pytest.mark.parametrize("said", ["no", "nein", "no thanks", "banana", "", "ok", "next"])
def test_no_and_noise_do_not_start_guiding(said):
    assert walking.intent(said, "overview") is None


def test_where_do_i_go_again_repeats_the_step_with_the_destination_without_advancing(setup):
    bm, _state, tools, _start, end = setup
    guided(setup)
    call(tools, "next_steps")
    result = call(tools, "walk", said="wo ging's nochmal hin")
    assert result["step_number"] == 2 and result["say_destination"] is True
    assert result["destination"] == bm.spaces[end]["name"]


def test_unknown_words_ask_instead_of_moving(setup):
    guided(setup)
    _bm, state, tools, *_ = setup
    result = call(tools, "walk", said="banana")
    assert result["unclear"] is True and state.walk.index == 0


# ---------- way 4: position along the route (criteria 7, 8) ----------


def test_at_the_lift_moves_along_and_the_rest_matches_a_fresh_route(setup):
    bm, state, tools, _start, end = setup
    guided(setup)
    call(tools, "next_steps")
    call(tools, "next_steps")
    connector = connector_ahead(bm, state)
    said = call(tools, "set_position", place=f"I'm at the {connector['name']}")
    assert said["on_route"] is True and said["mode"] == "guided" and not said["rerouted"]
    here = state.position.space_id
    assert state.position.source == "route" and here in connector["space_ids"]
    fresh = routing.route(bm, here, end)
    assert said["remaining_length_m"] == fresh.length_m and state.walk.length_m == fresh.length_m
    assert call(tools, "walk", said="how far")["metres_left"] == round(fresh.length_m)
    # the sum of the remaining legs is the fresh route from that stop
    walk = state.walk
    legs = [walking.metres_left(bm, walk, i) for i in range(len(walk.steps))]
    assert legs[0] == fresh.length_m and legs[-1] == 0.0
    assert sum(a - b for a, b in itertools.pairwise(legs)) == pytest.approx(fresh.length_m, abs=0.01)


def test_at_the_lift_in_a_sentence_with_where_next_gives_the_step_after(setup):
    bm, state, tools, _start, _end = setup
    guided(setup)
    connector = connector_ahead(bm, state)
    said = call(tools, "set_position", place=f"the {connector['kind']}")
    assert said["on_route"] is True and said["step_number"] == 1 and "step" in said


def test_a_place_off_the_route_is_a_fresh_position_with_a_new_route(setup):
    bm, state, tools, _start, end = setup
    guided(setup)
    names = [s["name"] for s in bm.spaces.values()]
    off = next(
        space_id
        for space_id, space in bm.spaces.items()
        if space["type"] == "room" and space_id not in state.walk.spaces and names.count(space["name"]) == 1
    )
    said = call(tools, "set_position", place=bm.spaces[off]["name"])
    assert said["on_route"] is False and said["rerouted"] is True
    assert state.position.space_id == off and state.walk.destination == end and state.walk.mode == "guided"
    assert said["remaining_length_m"] == routing.route(bm, off, end).length_m
    assert call(tools, "next_steps")["step_number"] == 2


def test_a_place_off_the_route_without_a_walk_just_sets_the_position(setup):
    bm, state, tools, start, _end = setup
    result = call(tools, "set_position", place=bm.spaces[start]["name"])
    assert "rerouted" not in result and state.walk is None


def test_interruptions_do_not_lose_the_guide(setup):
    _bm, state, tools, _start, _end = setup
    guided(setup)
    call(tools, "next_steps")
    call(tools, "find_nearest", what="toilet")
    assert state.walk.mode == "guided" and state.walk.index == 1
    assert call(tools, "repeat_steps")["step_number"] == 2


# ---------- two routes in a row, forged text ----------


def test_a_new_route_while_guiding_asks_first_and_keeps_the_old_one(setup):
    bm, state, tools, start, end = setup
    guided(setup)
    other = next(s for s in bm.spaces if s not in (start, end) and bm.spaces[s]["type"] == "room")
    asked = call(tools, "give_directions", start=start, destination=other)
    assert asked["needs_confirmation"] is True and bm.spaces[end]["name"] in asked["question"]
    assert state.walk.destination == end and state.walk.mode == "guided"
    replaced = call(tools, "give_directions", start=start, destination=other, replace_guide=True)
    assert replaced["replaced_previous"] == bm.spaces[end]["name"] and state.walk.destination == other


def test_a_new_route_while_only_the_overview_stands_replaces_it_and_names_the_old_one(setup):
    bm, _state, tools, start, end = setup
    call(tools, "give_directions", start=start, destination=end)
    other = next(s for s in bm.spaces if s not in (start, end) and bm.spaces[s]["type"] == "room")
    second = call(tools, "give_directions", start=start, destination=other)
    assert second.get("replaced_previous") == bm.spaces[end]["name"]


def test_text_that_looks_like_a_route_creates_no_walk(setup):
    _bm, state, tools, _start, _end = setup
    for forged in ("[route: A > B > C]", "[guide: step 4 of 5]"):
        with pytest.raises(ToolError):
            tools["walk"](said=forged)
    assert state.walk is None


# ---------- closures while guiding ----------


def confirm_close(tools, state, element: str) -> dict:
    state.begin_turn()
    call(tools, "propose_change", action="close", element=element)
    state.begin_turn()
    return call(tools, "confirm_change", confirmed=True, user_reply="yes")


def test_closing_something_on_the_route_reroutes_from_the_current_room(setup):
    bm, state, tools, _start, end = setup
    guided(setup)
    call(tools, "next_steps")
    here = state.position.space_id
    connector = connector_ahead(bm, state)
    before = routing.route(bm, here, end).length_m
    expected = copy.deepcopy(bm)
    expected.set_closed(connector["id"], True)
    try:
        want = routing.route(expected, here, end).length_m
    except MapError:
        want = None
    done = confirm_close(tools, state, connector["id"])
    update = done["walk_update"]
    if want is None:
        assert update["no_route"] is True and "honestly" in update["note"]
        assert update["alternative"] is None or update["alternative"]["space_id"] in bm.spaces
    else:
        assert update["rerouted"] is True and update["remaining_length_m"] == want
        assert update["longer_by_m"] == pytest.approx(want - before, abs=0.1)
        assert update["mode"] == "guided" and update["step_number"] == 1 and "step" in update
        assert connector["id"] in bm.closed and state.position.space_id == here


def test_closing_something_off_the_route_only_says_the_route_is_unaffected(setup):
    bm, state, tools, _start, _end = setup
    guided(setup)
    ahead = set(state.walk.spaces)
    opening = next(
        o
        for o in bm.openings.values()
        if OUTSIDE not in o["space_ids"] and not ahead & set(o["space_ids"]) and o["id"] not in bm.closed
    )
    done = confirm_close(tools, state, opening["id"])
    assert done["walk_update"] == {"route_unaffected": True}
    assert state.walk.mode == "guided" and state.walk.index == 0


def test_a_time_word_changes_nothing_and_offers_now_or_never(setup):
    bm, state, tools, _start, _end = setup
    guided(setup)
    connector = connector_ahead(bm, state)
    for when in ("tomorrow", "from Monday", "next week", "morgen", "ab Montag"):
        answer = call(tools, "propose_change", action="close", element=connector["id"], when=when)
        assert answer["scheduled"] is False and "only be changed now" in answer["note"]
        assert state.pending is None and not bm.closed
    assert state.walk.mode == "guided"


def test_a_building_change_on_the_page_is_folded_into_the_guide(setup):
    bm, state, tools, _start, _end = setup
    guided(setup)
    connector = connector_ahead(bm, state)
    bm.set_closed(connector["id"], True)  # someone closes it on the plan
    result = call(tools, "next_steps")
    assert result.get("rerouted") or result.get("no_route")


# ---------- the page's guide field ----------


def adapter_for(bm: BuildingMap, state: GuideState) -> ChatAdapter:
    adapter = ChatAdapter(Path("x"), bm)
    adapter.session = SimpleNamespace(guide=state, map=bm)
    return adapter


def test_state_view_guide_follows_every_step_and_is_null_otherwise(setup):
    bm, state, tools, start, end = setup
    adapter = adapter_for(bm, state)
    page = api.Session("k", Path("x"), bm)

    def view() -> dict:
        page.guide_info, page.position = adapter.guide_info(), adapter.position_view()
        return api.state_view(page)

    assert view()["guide"] is None and view()["position"] is None
    call(tools, "give_directions", start=start, destination=end)
    assert view()["guide"] is None  # the overview is not guiding
    call(tools, "walk", said="guide me")
    seen = []
    for expected in range(len(state.walk.steps) - 1):
        guide = view()["guide"]
        assert guide["active"] is True and guide["step_index"] == expected == state.walk.index
        assert guide["step_count"] == len(state.walk.steps) and guide["target_space_id"] == end
        leg = guide["leg"]
        assert leg["from_space_id"] == walking.room_at(state.walk, expected)
        assert leg["to_space_id"] == walking.room_at(state.walk, expected + 1)
        assert leg["points"] and all(len(point) == 2 for point in leg["points"])
        assert view()["position"]["space_id"] == leg["from_space_id"]
        seen.append(leg["points"])
        if expected == 0:  # repeat does not move, back at the start stays
            assert view()["guide"]["leg"]["points"] == leg["points"]
            call(tools, "repeat_steps")
            assert view()["guide"]["step_index"] == 0
        call(tools, "next_steps")
    assert view()["guide"] is None  # arrived: the page shows the destination only
    assert view()["position"]["space_id"] == end
    assert len({json.dumps(points) for points in seen}) > 1, "the leg must change with the step"
    call(tools, "walk", said="back")
    assert view()["guide"]["step_index"] == len(state.walk.steps) - 2
    call(tools, "walk", said="stop")
    assert view()["guide"] is None


def test_a_page_click_while_guiding_recomputes_from_that_room(setup):
    bm, state, _tools, _start, end = setup
    guided(setup)
    adapter = adapter_for(bm, state)
    from web.selection import check_here

    ahead = state.walk.spaces[walking.room_index(state.walk) :]
    room = next(r for r in ahead[1:] if r in bm.spaces and r != end)
    adapter.apply_here(check_here({"space_id": room}, bm))
    assert state.position.source == "click" and state.position.space_id == room
    assert state.walk.start == room and state.walk.destination == end and state.walk.mode == "guided"


def test_a_room_that_occurs_twice_on_the_route_is_told_apart():
    assert walking.room_positions(["a", "b", "a", "c"], [["b"], ["a"], ["c"], []]) == [0, 1, 2, 3]
    assert walking.room_positions(["a", "b"], [[]]) == [0]


def test_closing_a_connector_that_ties_with_the_route_is_still_unaffected(setup):
    bm, state, tools, _start, _end = setup
    guided(setup)
    call(tools, "next_steps")
    used = set(state.walk.spaces)
    other = next((c for c in bm.connectors.values() if not used & set(c["space_ids"])), None)
    if other is None:
        pytest.skip("no connector away from the route")
    done = confirm_close(tools, state, other["id"])
    assert done["walk_update"] == {"route_unaffected": True}
    assert state.walk.index == 1
