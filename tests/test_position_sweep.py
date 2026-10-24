"""'Nearest X' on every train/dev/test building: each room type and device type resolves or says why not. No API."""

import math
from pathlib import Path

import pytest

from building_agent.position import make_position, nearest
from starter_agent.building_map import OUTSIDE, MapError
from tests.conftest import load_map

BUILDINGS = sorted(str(path.parent) for path in Path("data").glob("*/*/building.json"))


def start_positions(bm) -> list:
    """The first and the last room by id, so both ends of a building are tried."""
    rooms = sorted(space_id for space_id in bm.spaces if space_id != OUTSIDE)
    return [make_position(bm, rooms[0], None, "said", 0), make_position(bm, rooms[-1], None, "said", 0)]


@pytest.mark.parametrize("building_dir", BUILDINGS, ids=[Path(path).name for path in BUILDINGS])
def test_nearest_resolves_every_type_or_gives_a_clean_message(building_dir):
    bm = load_map(building_dir)
    room_types = {space["room_type"] for space in bm.spaces.values() if space["id"] != OUTSIDE}
    asset_types = {asset["type"] for asset in bm.assets.values()}
    for position in start_positions(bm):
        for wanted in sorted(room_types | asset_types):
            try:
                result = nearest(bm, position, wanted.replace("_", " "))
            except MapError as error:
                assert str(error).strip(), f"{wanted}: empty message"
                continue
            first = result["nearest"]
            assert first["space_id"] in bm.spaces and math.isfinite(first["length_m"]) and first["length_m"] >= 0
            assert result["needs_choice"] or result["control_sentence"].endswith("different one?")
            ranked = [first["length_m"], *(item["length_m"] for item in result["others"])]
            assert ranked == sorted(ranked), f"{wanted}: not sorted by route length"


@pytest.mark.parametrize("building_dir", BUILDINGS, ids=[Path(path).name for path in BUILDINGS])
def test_walking_a_route_step_by_step_works_on_every_building(building_dir):
    """Overview, every step to the arrival, the page's leg, and the metres left, on routes between real rooms."""
    from building_agent import routing
    from building_agent import walk as walking
    from building_agent.guide_tools import GuideState

    bm = load_map(building_dir)
    rooms = sorted(space_id for space_id in bm.spaces if space_id != OUTSIDE)
    pairs = [(rooms[0], rooms[-1]), (rooms[len(rooms) // 2], rooms[0])]
    for start, end in pairs:
        kept = bm.last_route  # the map is shared with other tests: leave it as it was
        try:
            route = routing.route(bm, start, end)
        except MapError:
            continue
        finally:
            bm.last_route = kept
        state = GuideState()
        walk = walking.remember_route(bm, state, route)
        assert len(walk.steps) == len(walk.rooms) and walk.rooms[-1] == []
        if len(walk.steps) >= walking.MIN_STEPS_FOR_OVERVIEW:
            overview = walking.overview_payload(bm, walk)
            assert 2 <= len(overview["landmarks"]) <= walking.MAX_LANDMARKS and "[" not in "".join(
                overview["landmarks"]
            )
        walk.mode = "guided"
        for _ in range(len(walk.steps)):
            step = walking.step_payload(bm, state.walk)
            assert step["step"] and "[" not in step["step"] and 1 <= step["step_number"] <= step["of"]
            info = walking.guide_info(state.walk)
            assert (info is None) == step["arrived"]
            walking.apply(bm, state, "next")
        assert state.walk.index == len(walk.steps) - 1
        assert walking.step_payload(bm, state.walk)["arrived"] is True
