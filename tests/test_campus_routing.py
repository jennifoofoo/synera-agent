"""Routes across buildings: validity step by step, lengths, step-free, closures, tours, ambiguity, fuzz, sweep."""

import copy
import itertools
import math
import random
import time

import pytest

from building_agent import routing
from building_agent.campus import (
    Campus,
    CampusBuilding,
    Link,
    entrances,
    load_maps,
    make_example_campus,
)
from building_agent.campus_routing import AmbiguousReference, CampusRouter, campus_directions
from building_agent.directions import DirectionsSession
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError
from tests.conftest import DATA
from tests.test_routing import cases, run_route

CAMPUS_A, FACTORY, RESPLAN = "proc-campus-dev-000", "proc-factory-dev-003", "resplan-439"


def fresh():
    campus = make_example_campus(DATA)
    maps, _ = load_maps(campus)
    return campus, maps, CampusRouter(campus, maps)


def pick_space(bm: BuildingMap, index: int = 0) -> str:
    return sorted(space_id for space_id, space in bm.spaces.items() if space["room_type"] != "corridor")[index]


def entrance_space(bm: BuildingMap, entrance_id: str) -> str:
    return next(item["space_id"] for item in entrances(bm) if item["id"] == entrance_id)


def joined(bm: BuildingMap, first: str, second: str, step_free: bool) -> bool:
    for opening in bm.openings.values():
        if (
            set(opening["space_ids"]) == {first, second}
            and opening["id"] not in bm.closed
            and not (step_free and not opening["step_free"])
        ):
            return True
    for connector in bm.connectors.values():
        if connector["id"] in bm.closed or (step_free and not connector["step_free"]):
            continue
        if first in connector["space_ids"] and second in connector["space_ids"]:
            return True
    return False


def assert_valid(route, maps, step_free: bool = False) -> None:
    """Every step is an open door or connector inside a building, or a link between two entrances."""
    previous = None
    for leg in route.legs:
        if leg.kind == "building":
            bm = maps[leg.building_id]
            path = leg.route.space_path
            assert OUTSIDE not in path
            assert not set(path) & bm.closed
            for first, second in itertools.pairwise(path):
                assert joined(bm, first, second, step_free), f"no door between {first} and {second}"
            if previous is not None and previous.kind == "link":
                assert path[0] == entrance_space(bm, previous.to_entrance)
            elif previous is not None:  # a stop between two stages
                assert previous.end == "stop" and previous.building_id == leg.building_id
                assert path[0] == previous.route.space_path[-1]
        else:
            assert previous is None or previous.kind == "building"
            assert not leg.link.closed and (leg.link.step_free or not step_free)
            if previous is not None:
                bm = maps[leg.from_building]
                assert previous.route.space_path[-1] == entrance_space(bm, leg.from_entrance)
            for building_id, entrance_id in (
                (leg.from_building, leg.from_entrance),
                (leg.to_building, leg.to_entrance),
            ):
                opening = maps[building_id].openings[entrance_id]
                assert OUTSIDE in opening["space_ids"] and (opening["step_free"] or not step_free)
        previous = leg
    assert previous.kind == "building"
    link_total = sum(leg.length_m for leg in route.legs if leg.kind == "link")
    walk_total = sum(leg.route.length_m for leg in route.legs if leg.kind == "building")
    assert route.length_m == pytest.approx(link_total + walk_total, abs=0.02)
    assert route.space_path[0] == route.legs[0].route.space_path[0]


def test_route_across_two_buildings_is_valid():
    _campus, maps, router = fresh()
    start, destination = pick_space(maps[CAMPUS_A]), pick_space(maps[FACTORY], 3)
    route = router.route(start, destination)
    assert route.buildings == [CAMPUS_A, FACTORY]
    assert [leg.kind for leg in route.legs] == ["building", "link", "building"]
    assert route.space_path[0] == start and route.space_path[-1] == destination
    assert route.legs[1].link.id == "L1" and route.legs[1].length_m == 85.0
    assert_valid(route, maps)
    assert len(route.steps) >= 3
    assert any("85 m" in step for step in route.steps)


def test_route_across_three_buildings_and_back():
    _campus, maps, router = fresh()
    start, destination = pick_space(maps[CAMPUS_A]), pick_space(maps[RESPLAN])
    route = router.route(start, destination)
    assert route.buildings == [CAMPUS_A, FACTORY, RESPLAN]
    assert [leg.id for leg in route.legs if leg.kind == "link"] == ["L1", "L2"]
    assert_valid(route, maps)
    back = router.route(destination, start)
    assert_valid(back, maps)
    assert back.length_m == pytest.approx(route.length_m, abs=0.02)
    assert back.buildings == route.buildings[::-1]


def test_step_free_blocks_a_link_with_steps_and_takes_the_alternative():
    campus, maps, router = fresh()
    plain = next(item for item in entrances(maps[CAMPUS_A]) if item["step_free"])
    steps = next(item for item in entrances(maps[CAMPUS_A]) if not item["step_free"])
    factory = entrances(maps[FACTORY])[0]["id"]
    campus.links = [
        Link(id="L1", from_building=CAMPUS_A, from_entrance=steps["id"], to_building=FACTORY, to_entrance=factory,
             length_m=5.0, step_free=False),
        Link(id="L2", from_building=CAMPUS_A, from_entrance=plain["id"], to_building=FACTORY, to_entrance=factory,
             length_m=90.0),
    ]  # fmt: skip
    start, destination = pick_space(maps[CAMPUS_A]), pick_space(maps[FACTORY], 2)
    normal = router.route(start, destination)
    assert normal.links[0].id == "L1"
    wheel = router.route(start, destination, step_free=True)
    assert [link.id for link in wheel.links] == ["L2"]
    assert_valid(wheel, maps, step_free=True)
    assert wheel.length_m >= normal.length_m
    campus.links.pop()
    with pytest.raises(MapError, match="No step-free route"):
        router.route(start, destination, step_free=True)


def test_closed_link_disconnects_and_the_message_names_it():
    campus, maps, router = fresh()
    campus.links[0].closed = True
    start, destination = pick_space(maps[CAMPUS_A]), pick_space(maps[FACTORY])
    with pytest.raises(MapError, match=r"walkway L1 is closed"):
        router.route(start, destination)
    campus.links[0].closed = False
    router.route(start, destination)


def test_no_link_is_a_clear_error_and_outside_is_no_shortcut():
    campus, maps, router = fresh()
    campus.links = [campus.links[0]]
    start, destination = pick_space(maps[CAMPUS_A]), pick_space(maps[RESPLAN])
    with pytest.raises(MapError, match="There is no link between .* and Residence 439"):
        router.route(start, destination)


def test_closed_space_inside_a_building_blocks_the_route():
    _campus, maps, router = fresh()
    start, destination = pick_space(maps[CAMPUS_A]), pick_space(maps[FACTORY])
    maps[FACTORY].closed.add(destination)
    with pytest.raises(MapError):
        router.route(start, destination)


def test_closed_entrance_is_not_used():
    campus, maps, router = fresh()
    link = campus.links[0]
    maps[CAMPUS_A].closed.add(link.from_entrance)
    with pytest.raises(MapError):
        router.route(pick_space(maps[CAMPUS_A]), pick_space(maps[FACTORY]))


def test_tour_across_three_buildings_visits_stops_in_order():
    _campus, maps, router = fresh()
    a, b, c = pick_space(maps[CAMPUS_A]), pick_space(maps[FACTORY], 4), pick_space(maps[RESPLAN])
    route = router.route(a, c, via=[b])
    assert_valid(route, maps)
    position = 0
    for stop in (a, b, c):
        position = route.space_path.index(stop, position)
    assert route.buildings == [CAMPUS_A, FACTORY, RESPLAN]
    back = router.route(a, a, via=[c, b])
    assert_valid(back, maps)
    assert back.space_path[0] == back.space_path[-1] == a


def test_tour_with_a_stop_in_the_start_building_after_leaving():
    _campus, maps, router = fresh()
    a1, a2, b = pick_space(maps[CAMPUS_A], 0), pick_space(maps[CAMPUS_A], 2), pick_space(maps[FACTORY], 1)
    route = router.route(a1, a2, via=[b])
    assert_valid(route, maps)
    assert route.buildings[0] == CAMPUS_A and FACTORY in route.buildings
    assert route.space_path.index(b) > route.space_path.index(a1)


def test_same_building_uses_routing_unchanged(tmp_path):
    pairs = [case for case in cases() if case["reachable"]]
    assert len(pairs) >= 300
    done = 0
    for case in pairs:
        bm, expected = run_route(case)
        building_id = case["building"]
        campus = Campus("single", "Single", [CampusBuilding(building_id, None)], [])
        router = CampusRouter(campus, {building_id: bm})
        closed_before = set(bm.closed)
        if case.get("closed"):
            bm.closed.add(case["closed"])
        try:
            got = router.route(case["start"], case["end"], case.get("step_free", False))
        finally:
            bm.closed = closed_before
        assert got.space_path == expected.space_path
        assert got.length_m == expected.length_m
        assert len(got.legs) == 1 and got.buildings == [building_id]
        done += 1
    assert done >= 300


def test_cheaper_total_decides_between_two_links():
    campus, maps, router = fresh()
    first_a, second_a = (item["id"] for item in entrances(maps[CAMPUS_A]))
    first_b, second_b = (item["id"] for item in entrances(maps[FACTORY])[:2])
    campus.links = [
        Link(id="L1", from_building=CAMPUS_A, from_entrance=first_a, to_building=FACTORY, to_entrance=first_b,
             length_m=60.0),
        Link(id="L2", from_building=CAMPUS_A, from_entrance=second_a, to_building=FACTORY, to_entrance=second_b,
             length_m=60.0),
    ]  # fmt: skip
    start, destination = pick_space(maps[CAMPUS_A], 1), pick_space(maps[FACTORY], 5)

    def expected(link: Link) -> float:
        total = link.length_m
        for building_id, first, second in (
            (CAMPUS_A, start, entrance_space(maps[CAMPUS_A], link.from_entrance)),
            (FACTORY, entrance_space(maps[FACTORY], link.to_entrance), destination),
        ):
            view = copy.copy(maps[building_id])
            view.closed = set(maps[building_id].closed) | {OUTSIDE}
            total += routing.route(view, first, second).length_m
        return total

    for cheap, dear in (("L1", "L2"), ("L2", "L1")):
        for link in campus.links:
            link.length_m = 60.0
        by_id = {link.id: link for link in campus.links}
        by_id[dear].length_m = 400.0
        route = router.route(start, destination)
        assert [link.id for link in route.links] == [cheap]
        assert route.length_m == pytest.approx(expected(by_id[cheap]), abs=0.02)
    # equal link lengths: the building walks alone decide, and the winner is the cheaper of the two totals
    for link in campus.links:
        link.length_m = 60.0
    route = router.route(start, destination)
    assert route.length_m == pytest.approx(min(expected(link) for link in campus.links), abs=0.02)


def test_resolve_by_building_and_ambiguity():
    _campus, maps, router = fresh()
    assert router.resolve(pick_space(maps[FACTORY]), FACTORY)[0] == FACTORY
    name = maps[CAMPUS_A].spaces[pick_space(maps[CAMPUS_A])]["name"]
    assert router.resolve(name, "Hörsaalzentrum") == (CAMPUS_A, pick_space(maps[CAMPUS_A]))
    # the same room name in two buildings
    twin = maps[FACTORY].spaces[pick_space(maps[FACTORY])]
    twin["name"] = name
    with pytest.raises(AmbiguousReference) as error:
        router.resolve(name)
    assert {item["building"] for item in error.value.candidates} >= {"Hörsaalzentrum 024", "Fertigung Ost 27"}
    assert router.resolve(name, "Fertigung")[0] == FACTORY
    with pytest.raises(AmbiguousReference):
        router.route(name, pick_space(maps[RESPLAN]))
    route = router.route((name, "Fertigung"), pick_space(maps[RESPLAN]))
    assert route.buildings[0] == FACTORY


def test_resolve_errors_are_plain():
    _campus, maps, router = fresh()
    with pytest.raises(MapError, match="No room matches 'zzz'"):
        router.resolve("zzz")
    with pytest.raises(MapError, match="No building matches 'Atlantis'"):
        router.resolve("x", "Atlantis")
    assert router.resolve(f"Name [{pick_space(maps[FACTORY])}]")[0] == FACTORY


def test_directions_name_the_building_change_and_chunk_in_threes():
    _campus, maps, router = fresh()
    route = router.route(pick_space(maps[CAMPUS_A]), pick_space(maps[RESPLAN]))
    steps = campus_directions(route)
    assert steps == route.steps
    change = [step for step in steps if step.startswith("Leave ") and "enter " in step]
    assert len(change) == 2
    assert "covered walkway" in change[0] and "(85 m)" in change[0] and "Fertigung Ost 27" in change[0]
    assert "glass bridge" in change[1] and "(40 m)" in change[1]
    assert "entrance" in change[0]
    session = DirectionsSession(steps)
    handed = []
    while chunk := session.next():
        assert len(chunk) <= 3
        handed += chunk
    assert handed == steps


def test_link_effect_sentences():
    campus, _maps, router = fresh()
    sentence = router.link_effect(campus.links[1], True)[0]
    assert "no longer connected" in sentence and "Residence 439" in sentence
    assert "already" in router.link_effect(campus.links[1], False)[0]
    campus.links.append(
        Link(id="L3", from_building=CAMPUS_A, from_entrance=campus.links[0].from_entrance, to_building=RESPLAN,
             to_entrance=campus.links[1].to_entrance, length_m=300.0)
    )  # fmt: skip
    assert "no building loses" in router.link_effect(campus.links[1], True)[0]


def test_fuzz_missing_maps_bad_entrances_and_nan_lengths():
    campus, maps, router = fresh()
    start, destination = pick_space(maps[CAMPUS_A]), pick_space(maps[RESPLAN])
    campus.links[1].to_entrance = "no-such-entrance"
    with pytest.raises(MapError):
        router.route(start, destination)
    campus.links[1].to_entrance = entrances(maps[RESPLAN])[0]["id"]
    for bad in (math.nan, math.inf, -3.0, 0.0, None):
        campus.links[0].length_m = bad
        with pytest.raises(MapError, match="no link between"):
            router.route(start, pick_space(maps[FACTORY]))
    campus.links[0].length_m = 85.0
    maps[FACTORY] = None  # the map of the middle building is missing
    with pytest.raises(MapError):
        router.route(start, destination)
    with pytest.raises(MapError, match="not loaded"):
        router.route(start, ("anything", FACTORY))
    with pytest.raises(MapError, match="The map of .* is not loaded"):
        router.route(start, "no such room")
    with pytest.raises(MapError):
        router.route("", destination)
    campus.links.append(Link(id="L9", from_building="ghost", from_entrance="x", to_building=CAMPUS_A, to_entrance="y"))
    maps[FACTORY] = BuildingMap.load(DATA / "dev" / FACTORY)
    router.route(start, pick_space(maps[FACTORY]))  # a dangling link does not break routing


def reachable(router, maps, building_id: str, entrance_id: str) -> list[str]:
    gate = entrance_space(maps[building_id], entrance_id)
    return [
        space
        for space in sorted(maps[building_id].spaces)
        if router._leg_cost(building_id, gate, space, False) is not None
    ]


def test_sweep_random_building_pairs():
    started = time.perf_counter()
    rng = random.Random(11)
    folders = sorted(path for path in (DATA / "dev").iterdir() if (path / "building.json").is_file())
    loaded = {}
    for path in folders:
        bm = BuildingMap.load(path)
        if len(bm.spaces) <= 400 and entrances(bm):
            loaded[path.name] = (path, bm)
    names = sorted(loaded)
    routes = 0
    for pair in range(40):
        first, second = rng.sample(names, 2)
        campus = Campus(
            f"sweep-{pair}",
            "Sweep",
            [CampusBuilding(first, loaded[first][0]), CampusBuilding(second, loaded[second][0])],
            [],
        )
        maps = {first: copy.copy(loaded[first][1]), second: copy.copy(loaded[second][1])}
        for building_id in (first, second):
            maps[building_id].closed = set()
        links = [
            Link(
                id="L1",
                from_building=first,
                from_entrance=entrances(maps[first])[0]["id"],
                to_building=second,
                to_entrance=entrances(maps[second])[0]["id"],
                length_m=round(rng.uniform(20, 300), 1),
                step_free=False,
            )
        ]
        campus.links = links
        router = CampusRouter(campus, maps)
        link = links[0]

        for _ in range(5):
            start = rng.choice(reachable(router, maps, first, link.from_entrance))
            destination = rng.choice(reachable(router, maps, second, link.to_entrance))
            route = router.route(start, destination)
            assert_valid(route, maps)
            assert route.space_path[0] == start and route.space_path[-1] == destination
            assert route.steps
            routes += 1
    assert routes == 200
    assert time.perf_counter() - started < 40


def test_campus_without_buildings_in_the_route_is_a_plain_error():
    campus = Campus("empty", "Empty", [], [])
    with pytest.raises(MapError):
        CampusRouter(campus, {}).route("a", "b")
