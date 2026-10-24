import inspect

import networkx as nx
import pytest

from building_agent.kinds.room_stacked import room_stacked, room_stacked_with
from building_agent.kinds.shared_walls_count import shared_walls_count, shared_walls_count_with
from building_agent.kinds.step_free_reachable_count import step_free_reachable_count, step_free_reachable_count_with
from building_agent.kinds.what_if_door import _gains, shared_wall_midpoint, what_if_door, what_if_door_with
from building_agent.kinds.wide_delivery_count import wide_delivery_count, wide_delivery_count_with
from building_agent.registry import load_kinds
from scripts.rule_sensitivity import (
    DEFAULT_LIFT,
    DEFAULT_STAIRS,
    LIFT_READINGS,
    READINGS,
    STAIRS_READINGS,
    UNREACHABLE,
    same_answer,
    variant_graph,
    vertical_model,
)
from starter_agent.building_map import BuildingMap
from tests.conftest import labelled_questions, load_map

PAIRS = {
    "shared_walls_count": (shared_walls_count, shared_walls_count_with),
    "wide_delivery_count": (wide_delivery_count, wide_delivery_count_with),
    "step_free_reachable_count": (step_free_reachable_count, step_free_reachable_count_with),
    "what_if_door": (what_if_door, what_if_door_with),
    "room_stacked": (room_stacked, room_stacked_with),
}


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def space(space_id, floor, polygon, type_="room", room_type="office"):
    return {
        "id": space_id,
        "floor_id": floor,
        "type": type_,
        "room_type": room_type,
        "name": space_id,
        "ref": space_id,
        "polygon": polygon,
        "synthetic": False,
    }


def tower(lift_stops=3, stairs_stops=("F0", "F2")) -> BuildingMap:
    """Three floors 3 m apart, one core space per floor, a lift through all floors and a stair skipping F1."""
    floors = [
        {"id": f"F{i}", "level": i, "name": f"Floor {i}", "elevation_m": 3.0 * i, "height_m": 3.0} for i in range(3)
    ]
    spaces = [space(f"C{i}", f"F{i}", rect(0, 0, 4, 4), "lift", "lift") for i in range(3)]
    connectors = [
        {
            "id": "V-lift",
            "kind": "lift",
            "name": "Lift",
            "floor_ids": [f"F{i}" for i in range(lift_stops)],
            "space_ids": [f"C{i}" for i in range(lift_stops)],
            "step_free": True,
        },
        {
            "id": "V-stairs",
            "kind": "stairs",
            "name": "Stairs",
            "floor_ids": list(stairs_stops),
            "space_ids": [f"C{stop[1]}" for stop in stairs_stops],
            "step_free": False,
        },
    ]
    building = {
        "building": {"id": "tower", "source": "procedural"},
        "floors": floors,
        "spaces": spaces,
        "openings": [],
        "vertical_connectors": connectors,
        "assets": [],
    }
    return BuildingMap(building)


def cost(bm: BuildingMap, stairs: str, lift: str, connector: str) -> float:
    """Cheapest C0 -> C2 cost using only `connector`."""
    keep = {"lift": "V-stairs", "stairs": "V-lift"}[connector]
    bm.closed = {keep}
    try:
        graph = variant_graph(bm, False, stairs, lift)
    finally:
        bm.closed = set()
    return nx.shortest_path_length(graph, "C0", "C2", weight="weight")


def edge_weights(graph: nx.MultiGraph) -> list:
    return sorted((tuple(sorted(map(str, edge[:2]))), round(edge[2], 6)) for edge in graph.edges(data="weight"))


# ---------- vertical readings ----------


def test_default_variant_graph_equals_building_map_graph():
    for building_dir in {case[0] for case in labelled_questions("errand")[:12]}:
        bm = load_map(building_dir)
        for step_free in (False, True):
            assert edge_weights(variant_graph(bm, step_free, DEFAULT_STAIRS, DEFAULT_LIFT)) == edge_weights(
                bm.graph(step_free)
            )


def test_stairs_readings_on_a_stair_that_skips_a_floor():
    bm = tower()
    assert cost(bm, "floor_diff", DEFAULT_LIFT, "stairs") == 24.0  # two levels apart
    assert cost(bm, "per_stop", DEFAULT_LIFT, "stairs") == 12.0  # one hop
    assert cost(bm, "per_metre", DEFAULT_LIFT, "stairs") == 12.0  # 6 m climbed, 2 m per metre


def test_lift_readings_wait_every_hop_or_once():
    bm = tower()
    assert cost(bm, DEFAULT_STAIRS, "kit_every_hop", "lift") == 2 * (15 + 6)
    assert cost(bm, DEFAULT_STAIRS, "kit_wait_once", "lift") == 15 + 2 * 6
    assert cost(bm, DEFAULT_STAIRS, "synera_every_hop", "lift") == 2 * 15 + 6
    assert cost(bm, DEFAULT_STAIRS, "synera_wait_once", "lift") == 15 + 6


def test_wait_once_equals_every_hop_for_two_stop_lift():
    bm = tower(lift_stops=2)
    bm.closed = {"V-stairs"}
    every = nx.shortest_path_length(
        variant_graph(bm, False, DEFAULT_STAIRS, "kit_every_hop"), "C0", "C1", weight="weight"
    )
    once = nx.shortest_path_length(
        variant_graph(bm, False, DEFAULT_STAIRS, "kit_wait_once"), "C0", "C1", weight="weight"
    )
    assert every == once == 21.0


def test_lifts_forbidden_drops_lift_edges():
    bm = tower()
    graph = variant_graph(bm, False, DEFAULT_STAIRS, DEFAULT_LIFT, lifts_allowed=False)
    assert {data["via"] for _, _, data in graph.edges(data=True)} == {"V-stairs"}


def test_vertical_model_patches_only_while_running():
    original = BuildingMap.graph
    bm = tower()
    with vertical_model("per_stop", DEFAULT_LIFT):
        assert BuildingMap.graph is not original
        assert bm.graph(False).has_edge("C0", "C2")
    assert BuildingMap.graph is original


def test_every_vertical_reading_name_is_unique_and_runs():
    for kind, readings in READINGS.items():
        names = [reading.name for reading in readings]
        assert len(names) == len(set(names)), kind
        assert sum(reading.is_default for reading in readings) >= 1, kind
    assert len(STAIRS_READINGS) * len(LIFT_READINGS) == 12


# ---------- defaults unchanged ----------


@pytest.mark.parametrize("kind", sorted(PAIRS))
def test_with_function_defaults_equal_registered_kind(kind):
    plain, with_readings = PAIRS[kind]
    cases = labelled_questions(kind)[:15]
    assert cases
    for building_dir, question in cases:
        bm = load_map(building_dir)
        assert with_readings(bm, **question["inputs"]) == plain(bm, **question["inputs"])


@pytest.mark.parametrize("kind", sorted(PAIRS))
def test_registered_tool_signature_has_no_reading_parameters(kind):
    plain, _ = PAIRS[kind]
    assert load_kinds()[kind].fn is plain
    names = list(inspect.signature(load_kinds()[kind].fn).parameters)
    assert not {"strict", "counted", "door_mode", "inclusive", "metric", "wall_thickness_m"} & set(names)


# ---------- reading switches ----------


def room_pair(gap: float, type_second="room") -> BuildingMap:
    spaces = [
        space("A", "F0", rect(0, 0, 4, 4)),
        space("B", "F0", rect(4 + gap, 0, 8 + gap, 4), type_second, "generic_room"),
    ]
    building = {
        "building": {"id": "pair", "source": "procedural"},
        "floors": [{"id": "F0", "level": 0, "name": "Ground floor", "elevation_m": 0.0, "height_m": 3.0}],
        "spaces": spaces,
        "openings": [],
        "vertical_connectors": [],
        "assets": [],
    }
    return BuildingMap(building)


def test_shared_walls_tolerance_and_overlap_switches():
    bm = room_pair(gap=0.3)
    assert shared_walls_count_with(bm, "A")["count"] == 1  # 0.35 m tolerance, 4 m shared
    assert shared_walls_count_with(bm, "A", wall_thickness_m=0.2)["count"] == 0
    assert shared_walls_count_with(bm, "A", wall_thickness_m=0.5)["count"] == 1
    assert shared_walls_count_with(bm, "A", min_shared_m=4.5)["count"] == 0
    assert shared_walls_count_with(bm, "A", min_shared_m=3.9)["count"] == 1


def test_shared_walls_hall_exclusion_switch():
    bm = room_pair(gap=0.1, type_second="hall")
    assert shared_walls_count_with(bm, "A")["count"] == 1
    assert shared_walls_count_with(bm, "A", also_excluded_types=frozenset({"hall"}))["count"] == 0


def two_wide_doors(width: float) -> BuildingMap:
    bm = room_pair(gap=0.0)
    bm.data["spaces"].append(space("OUT", "F0", rect(-4, 0, 0, 4), "hall", "lobby"))
    bm.spaces = {s["id"]: s for s in bm.data["spaces"]}
    opening = {
        "id": "O1",
        "floor_id": "F0",
        "space_ids": ["A", "B"],
        "kind": "door",
        "position": [4.0, 2.0],
        "width_m": width,
        "step_free": True,
    }
    entrance = {**opening, "id": "O0", "space_ids": ["outside", "A"], "position": [0.0, 2.0], "width_m": 2.0}
    bm.openings = {"O0": entrance, "O1": opening}
    return bm


def test_wide_delivery_strict_switch_at_the_exact_width():
    bm = two_wide_doors(1.1)
    assert wide_delivery_count_with(bm, "A", "F0", 1.1)["count"] == 2
    assert wide_delivery_count_with(bm, "A", "F0", 1.1, strict=True)["count"] == 1
    assert wide_delivery_count_with(bm, "A", "F0", 1.0, strict=True)["count"] == 2


def test_wide_delivery_counted_switch():
    bm = two_wide_doors(1.1)
    bm.openings["O2"] = {
        "id": "O2",
        "floor_id": "F0",
        "space_ids": ["A", "OUT"],
        "kind": "door",
        "position": [0.0, 1.0],
        "width_m": 1.2,
        "step_free": True,
    }
    assert wide_delivery_count_with(bm, "A", "F0", 1.1)["count"] == 2
    assert wide_delivery_count_with(bm, "A", "F0", 1.1, counted=lambda s: s["type"] != "lift")["count"] == 3


def test_what_if_gain_threshold_switch():
    assert not _gains(1.0, inclusive=False)
    assert _gains(1.0, inclusive=True)
    assert _gains(1.0000000001, inclusive=False)
    assert not _gains(0.99, inclusive=True)


def l_shaped_wall() -> BuildingMap:
    """A is 6 m wide; B touches it along two separate stretches (2 m near x=0 and 1 m near x=5)."""
    bm = room_pair(gap=0.0)
    bm.data["spaces"] = [
        space("A", "F0", rect(0, 0, 6, 4)),
        space("B", "F0", [[0, 4], [6, 4], [6, 6], [5, 6], [5, 5], [2, 5], [2, 6], [0, 6]]),
    ]
    bm.spaces = {s["id"]: s for s in bm.data["spaces"]}
    return bm


def test_door_position_modes_differ_on_split_wall():
    bm = l_shaped_wall()
    longest = shared_wall_midpoint(bm, "A", "B")
    assert shared_wall_midpoint(bm, "A", "B", mode="longest") == longest
    combined = shared_wall_midpoint(bm, "A", "B", mode="combined")
    centroid = shared_wall_midpoint(bm, "A", "B", mode="centroid")
    assert combined != longest or centroid != longest
    for point in (longest, combined, centroid):
        assert all(isinstance(value, float) for value in point)


def test_room_stacked_switches():
    floors = [{"id": f"F{i}", "level": i, "name": f"F{i}", "elevation_m": 3.0 * i, "height_m": 3.0} for i in (0, 2)]
    spaces = [
        space("low", "F0", rect(0, 0, 10, 10)),
        space("big", "F2", rect(0, 0, 40, 10), "room", "generic_room"),  # larger intersection? no: same, but huge union
        space("tight", "F2", rect(0, 0, 9, 10), "outdoor", "generic_room"),
    ]
    bm = BuildingMap(
        {
            "building": {"id": "stack", "source": "procedural"},
            "floors": floors,
            "spaces": spaces,
            "openings": [],
            "vertical_connectors": [],
            "assets": [],
        }
    )
    assert room_stacked_with(bm, "low", "above")["space_id"] == "big"  # 100 m2 beats 90 m2
    assert room_stacked_with(bm, "low", "above", metric="iou")["space_id"] == "tight"  # 90/100 beats 100/400
    assert room_stacked_with(bm, "low", "above", excluded_types=frozenset({"outdoor"}))["space_id"] == "big"
    with pytest.raises(ValueError):
        room_stacked_with(bm, "low", "above", adjacent_level_only=True)  # next existing floor is 2 levels up


def test_same_answer_rules():
    assert same_answer("errand", 100.0, 100.9, (1.0, 0.01))
    assert not same_answer("errand", 100.0, 102.5, (1.0, 0.01))
    assert same_answer("shared_walls_count", 3, 3, (0.0, 0.0))
    assert not same_answer("shared_walls_count", 3, 4, (0.0, 0.0))
    assert not same_answer("errand", UNREACHABLE, 50.0, (1.0, 0.01))
    assert same_answer("room_stacked", "S1", ["S1", "S2"], (0.0, 0.0))
