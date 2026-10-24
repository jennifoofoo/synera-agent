"""Optional SVG reader: offline checks on a tiny svg and recall on real Swiss floors (skipped without data/)."""

import pytest

from building_agent.level4.svg_read import read_svg
from tests.level4_helpers import DATA_DEV, load_building

TINY = """<svg width="100pt" height="50pt" viewBox="0 0 100 50">
 <g id="patch_2"><path d="M 0 0 L 40 0 L 40 40 L 0 40 z" style="fill: #f3efe6; stroke: #333333; stroke-width: 0.6"/></g>
 <g id="patch_3"><path d="M 40 0 L 80 0 L 80 40 L 40 40 z" style="fill: #dcdcdc; stroke: #333333; stroke-width: 0.6"/></g>
 <g id="patch_4"><path d="M 10 10 L 20 10 L 20 20 L 10 20 z" style="fill: #4f81bd; opacity: 0.75"/></g>
 <g id="line2d_1"><path d="M 40 20 " style="fill: none; stroke: #8b4513"/></g>
 <g id="line2d_2"><path d="M 0 20 " style="fill: none; stroke: #d32f2f"/></g>
</svg>"""


def test_tiny_svg_gives_rooms_and_doors(tmp_path):
    path = tmp_path / "plan.svg"
    path.write_text(TINY, encoding="utf-8")
    result = read_svg(path)
    assert [room.type for room in result.rooms] == ["room", "corridor"]  # furniture is not a room
    assert [(d.kind, set(d.rooms)) for d in result.doors] == [("door", {"r0", "r1"}), ("entrance", {"r0", "outside"})]


@pytest.mark.parametrize("content", ["", "not svg", "<svg width='1pt' height='1pt'></svg>"])
def test_not_a_plan_gives_none(tmp_path, content):
    path = tmp_path / "x.svg"
    path.write_text(content, encoding="utf-8")
    assert read_svg(path) is None


def test_missing_file_gives_none(tmp_path):
    assert read_svg(tmp_path / "none.svg") is None


@pytest.mark.parametrize("building_id", ["swiss-31", "swiss-203", "swiss-1785"])
def test_real_swiss_floors_give_every_true_door(building_id):
    if not (DATA_DEV / building_id).exists():
        pytest.skip("kit data missing (run scripts/get_data.sh)")
    building = load_building(building_id)
    for floor in building["floors"]:
        spaces = [s for s in building["spaces"] if s["floor_id"] == floor["id"]]
        result = read_svg(DATA_DEV / building_id / f"floor_{floor['level']}.svg")
        assert len(result.rooms) == len(spaces)
        ids = {f"r{index}": space["id"] for index, space in enumerate(spaces)}
        found = {frozenset(ids.get(end, end) for end in door.rooms) for door in result.doors}
        truth = {frozenset(o["space_ids"]) for o in building["openings"] if o["floor_id"] == floor["id"]}
        assert len(found & truth) >= 0.99 * len(truth)
