"""W-L2a: the page draws the agent's route (people model, building_agent.routing), not the kit model's."""

import itertools
import json
from collections import defaultdict
from functools import cache
from pathlib import Path

import pytest

from building_agent import routing
from building_agent.guide_tools import GuideState, make_guide_tools
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError
from tests.conftest import DATA, LABELLED_SPLITS
from web import api, route_draw

ROUTE_KINDS = ("route", "route_step_free", "route_with_closure", "tour")
PER_SOURCE_AND_KIND = 3


@cache
def sample() -> tuple[tuple[str, str, dict], ...]:
    """(building dir, kind, answer) for the first few warm-up route questions per source and kind."""
    picked: dict[tuple[str, str], list] = defaultdict(list)
    for split in LABELLED_SPLITS:
        for path in sorted((DATA / split).glob("*/questions_basic.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                question = json.loads(line)
                kind, answer = question["kind"], question["answer"]
                bucket = picked[(question["building_id"].split("-")[0], kind)]
                if kind in ROUTE_KINDS and answer.get("reachable") is not False and len(bucket) < PER_SOURCE_AND_KIND:
                    bucket.append((str(path.parent), kind, answer))
    return tuple(case for bucket in picked.values() for case in bucket)


def case_request(kind: str, answer: dict) -> tuple[str, str, bool, list[str]]:
    if kind == "tour":
        stops = answer["stops"]
        return stops[0], stops[-1], False, stops[1:-1]
    return answer["from_space_id"], answer["to_space_id"], kind == "route_step_free", []


def session_for(building_dir: str) -> api.Session:
    return api.Session("test", Path(building_dir), api.RecordingMap.load(Path(building_dir)))


@pytest.mark.parametrize(
    "building_dir,kind,answer", sample(), ids=[f"{Path(d).name}-{k}-{i}" for i, (d, k, _) in enumerate(sample())]
)
def test_page_route_has_the_agents_space_path(building_dir, kind, answer, tmp_path):
    start, end, step_free, via = case_request(kind, answer)
    session = session_for(building_dir)
    bm = session.map
    if answer.get("closed_element_id"):
        bm.set_closed(answer["closed_element_id"], True)
    page = api.route_view(session, start, end, step_free, via)
    assert page["ok"] and page["model"] == api.PEOPLE_MODEL
    agent = routing.route(bm, start, end, step_free, via)
    assert page["space_path"] == agent.space_path
    assert page["length_m"] == agent.length_m
    kit = BuildingMap.route(bm, start, end, step_free, via)
    assert page["kit"] == {"space_path": kit.space_path, "length_m": kit.length_m}
    assert page["differs_from_kit"] == (kit.space_path != agent.space_path)
    stops = [page["start"], *page["via"], page["destination"]]
    assert api.route_legs(bm, stops, step_free, page["space_path"]) is not None, "line fell back to room anchors"
    # give_directions (the voice guide) reads its route from the same function.
    tools = {tool.name: tool for tool in make_guide_tools(bm, tmp_path, GuideState())}
    tools["give_directions"](start=start, destination=end, step_free=step_free, via=via or None)
    assert bm.last_route.space_path == page["space_path"]
    assert_line_follows_the_doors(bm, page)


def assert_line_follows_the_doors(bm, page: dict) -> None:
    """Starts and ends at the room anchors (moved off furniture) or, for big halls, at their door; every door on
    the way is a point of the line, floor changes join up."""
    points = [(segment["floor_id"], tuple(point)) for segment in page["segments"] for point in segment["points"]]
    start, end = page["space_path"][0], page["space_path"][-1]

    def room_end(space_id: str) -> set:
        floor_id = bm.spaces[space_id]["floor_id"]
        doors = {
            (o["floor_id"], tuple(api.rounded(o["position"])))
            for o in bm.openings.values()
            if space_id in o["space_ids"]
        }
        return {(floor_id, tuple(api.rounded(route_draw.drawn_anchor(bm, space_id)))), *doors}

    assert points[0] in room_end(start)
    if start != end:
        assert points[-1] in room_end(end)
    for first, second in itertools.pairwise(page["space_path"]):
        door = next(
            (o for o in bm.openings.values() if set(o["space_ids"]) == {first, second} and o["id"] not in bm.closed),
            None,
        )
        if door is not None and OUTSIDE not in (first, second):
            on_line = [p for f, p in points if f == door["floor_id"]]
            # Parallel doors: the line passes one of them.
            assert any(
                set(o["space_ids"]) == {first, second} and tuple(api.rounded(o["position"])) in on_line
                for o in bm.openings.values()
            ), (first, second)
    for change in page["floor_changes"]:
        assert (change["from_floor"], tuple(change["from_point"])) in points
        assert (change["to_floor"], tuple(change["to_point"])) in points


def test_page_redraw_keeps_the_agents_route_and_via_stops(tmp_path):
    building_dir, _, answer = next(case for case in sample() if case[1] == "tour" and len(case[2]["stops"]) >= 3)
    start, end, _, via = case_request("tour", answer)
    session = session_for(building_dir)
    bm = session.map
    before, version = bm.last_route, session.route_version
    # The agent routes with via stops, then a step-free comparison runs and restores the earlier result.
    tools = {tool.name: tool for tool in make_guide_tools(bm, tmp_path, GuideState())}
    tools["give_directions"](start=start, destination=end, step_free=False, via=via)
    agent_route = bm.last_route
    assert session.adopt_agent_route(before, version)
    assert session.route_request["via"] == via
    api.route_view(session, end, start)  # the page asks for something else ...
    api.state_view(session)  # ... and redraws, more than once
    api.set_closed(session, next(iter(bm.openings)), True)
    assert bm.last_route is agent_route
    assert not session.adopt_agent_route(agent_route, session.route_version)


def test_adopted_tour_is_drawn_with_its_via_stops():
    building_dir, _, answer = next(case for case in sample() if case[1] == "tour")
    start, end, _, via = case_request("tour", answer)
    session = session_for(building_dir)
    before, version = session.map.last_route, session.route_version
    agent_route = routing.route(session.map, start, end, False, via)  # what find_route does
    routing.route(session.map, start, end, True)  # a helper routes again ...
    session.map.last_route = agent_route  # ... and puts the agent's route back
    assert session.adopt_agent_route(before, version)
    drawn = api.state_view(session)["route"]
    assert drawn["via"] == via and drawn["space_path"] == agent_route.space_path


def test_closure_redraw_uses_the_people_model():
    building_dir, _, answer = next(case for case in sample() if case[1] == "route_with_closure")
    session = session_for(building_dir)
    start, end = answer["from_space_id"], answer["to_space_id"]
    api.route_view(session, start, end)
    closed = api.set_closed(session, answer["closed_element_id"], True)["state"]["route"]
    assert closed["ok"] and closed["model"] == api.PEOPLE_MODEL
    assert answer["closed_element_id"] not in {c["connector_id"] for c in closed["floor_changes"]}
    assert closed["space_path"] == routing.route(session.map, start, end).space_path


def test_unreachable_page_route_explains_why():
    building_dir, _, answer = next(case for case in sample() if case[1] == "route")
    session = session_for(building_dir)
    start, end = answer["from_space_id"], answer["to_space_id"]
    session.map.set_closed(end, True)
    with pytest.raises(MapError):
        api.route_view(session, start, end)
    assert api.current_route(session)["ok"] is False


def test_page_route_never_differs_from_the_kit_model():
    """One model: the people route and the kit route are the same trip, so the page never flags a difference."""
    checked = 0
    for building_dir in sorted(str(p.parent) for p in (DATA / "dev").glob("proc-*/building.json")):
        session = session_for(building_dir)
        bm = session.map
        rooms = sorted(s["id"] for s in bm.spaces.values() if s["type"] == "room")
        for start, end in itertools.islice(itertools.combinations(rooms, 2), 0, None, 7):
            try:
                page = api.route_view(session, start, end)
            except MapError:
                continue
            assert page["differs_from_kit"] is False
            assert page["kit"]["space_path"] == page["space_path"] == routing.route(bm, start, end).space_path
            assert page["model"] == api.PEOPLE_MODEL
            checked += 1
    assert checked > 20
