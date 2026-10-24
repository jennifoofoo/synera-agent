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
