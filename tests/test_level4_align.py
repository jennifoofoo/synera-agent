"""Offline tests of the floor alignment and the storey height of a building built from plans (Level 4)."""

from building_agent.level4.align import align_floors
from building_agent.level4.floor_height import guess_floor_height
from building_agent.level4.scale_source import find_floor_heights


def box(x: float, y: float, w: float = 2.0, h: float = 3.0) -> list[list[float]]:
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def space(floor: str, number: int, kind: str, polygon: list[list[float]]) -> dict:
    return {"id": f"{floor}-S{number}", "floor_id": floor, "type": kind, "polygon": polygon}


def building(upper_shift: tuple[float, float], upper_connectors: list[str] | None = None) -> dict:
    """Two floors; floor 1 is the same layout as floor 0 moved by `upper_shift` (a crop of its own)."""
    dx, dy = upper_shift
    kinds = upper_connectors if upper_connectors is not None else ["stair", "lift"]
    lower = [("stair", box(0, 0)), ("lift", box(10, 0)), ("room", box(4, 0, 5, 5))]
    upper = [(k, box(10 * i + dx, dy)) for i, k in enumerate(kinds)] + [("room", box(4 + dx, dy, 5, 5))]
    spaces = [space("F0", i, k, p) for i, (k, p) in enumerate(lower)]
    spaces += [space("F1", i, k, p) for i, (k, p) in enumerate(upper)]
    return {
        "floors": [{"id": "F0", "level": 0}, {"id": "F1", "level": 1}],
        "spaces": spaces,
        "openings": [{"id": "O1", "floor_id": "F1", "position": [5.0 + dx, 1.0 + dy]}],
    }


def test_upper_floor_is_moved_onto_the_floor_below():
    data = building((-7.5, 3.25))
    offsets, skipped = align_floors(data)
    assert offsets[0] == (0.0, 0.0)
    assert offsets[1] == (7.5, -3.25)
    assert not skipped
    stair = next(s for s in data["spaces"] if s["floor_id"] == "F1" and s["type"] == "stair")
    assert stair["polygon"][0] == [0.0, 0.0]
    assert data["openings"][0]["position"] == [5.0, 1.0]  # doors move with their floor


def test_floors_with_the_same_frame_stay_put():
    offsets, skipped = align_floors(building((0.0, 0.0)))
    assert offsets[1] == (0.0, 0.0)
    assert not skipped


def test_one_connector_is_not_enough_to_move_a_floor():
    data = building((-7.5, 3.25), upper_connectors=["stair"])
    before = [s["polygon"] for s in data["spaces"]]
    offsets, skipped = align_floors(data)
    assert offsets[1] == (0.0, 0.0)
    assert 1 in skipped
    assert [s["polygon"] for s in data["spaces"]] == before


def test_floor_without_connectors_is_left_alone_and_reported():
    data = building((-7.5, 3.25), upper_connectors=[])
    offsets, skipped = align_floors(data)
    assert offsets[1] == (0.0, 0.0)
    assert "no stairs or lifts" in skipped[1]


def test_floor_heights_from_a_building_json_under_any_parent():
    plain = {
        "floors": [{"level": 0, "elevation_m": 0.0, "height_m": 3.8}, {"level": 1, "elevation_m": 3.8, "height_m": 3.8}]
    }
    nested = {"building": {"floors": [{"level": 1, "height_m": "3.5"}]}}
    assert find_floor_heights(plain) == {0: (0.0, 3.8), 1: (3.8, 3.8)}
    assert find_floor_heights(nested) == {1: (None, 3.5)}
    assert find_floor_heights({"floors": [{"level": 0, "height_m": 99}]}) == {}


def test_default_height_by_family():
    assert guess_floor_height(["H-A1", "0.01"])[0] == 3.5
    assert guess_floor_height(["0.01", "0.02"], "Lehrgebaeude 030")[0] == 3.8
    assert guess_floor_height(["0.01", "0.02"], "Residential building 2211")[0] == 3.0
    assert guess_floor_height(["N0317", "0.02"], "N3")[0] == 3.0
    assert guess_floor_height([])[0] == 3.0
