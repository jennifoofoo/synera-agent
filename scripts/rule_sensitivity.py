"""Which test answers depend on an ambiguous reading of the README rules (sections 3, 4 and 6)?

uv run python scripts/rule_sensitivity.py                      (prints the report)
uv run python scripts/rule_sensitivity.py --write docs/rule-sensitivity.md

Deterministic, no API calls. For every kind with an ambiguous rule it recomputes the 145 test answers under
alternative readings (production code is never changed: readings are keyword arguments of the `*_with`
functions in building_agent/kinds/ or a patched BuildingMap.graph while a reading runs). Each reading is also
scored on the labelled train and dev questions of its kind: a reading that agrees with fewer labels than the
production default is "ruled out by labels". A test answer is sensitive when some reading that is not ruled out
gives an answer our current answer would not be scored correct against."""

import argparse
import contextlib
import csv
import itertools
import json
import math
import re
import sys
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from building_agent.kinds.errand import errand
from building_agent.kinds.room_stacked import room_stacked_with
from building_agent.kinds.shared_walls_count import shared_walls_count_with
from building_agent.kinds.step_free_reachable_count import step_free_reachable_count_with
from building_agent.kinds.what_if_door import is_room, what_if_door_with
from building_agent.kinds.wide_delivery_count import wide_delivery_count_with
from building_agent.question_parser import parse_question
from starter_agent.building_map import (
    DOOR_PREFIX,
    LIFT,
    LIFT_COST_PER_FLOOR_M,
    LIFT_WAIT_COST_M,
    OUTSIDE,
    STAIRS_COST_PER_FLOOR_M,
    BuildingMap,
    MapError,
)
from tests.conftest import DATA, labelled_questions

DEFAULT_ANSWERS = Path("agent_output/full_test.csv")
CONNECTOR_TYPES = {"stair", "lift"}
UNREACHABLE = "unreachable"

# ---------- vertical cost readings (patched into BuildingMap.graph) ----------

STAIRS_READINGS = ("floor_diff", "per_stop", "per_metre")  # 12 per level difference | 12 per hop | 2 per metre
LIFT_READINGS = ("kit_every_hop", "kit_wait_once", "synera_every_hop", "synera_wait_once")
DEFAULT_STAIRS, DEFAULT_LIFT = STAIRS_READINGS[0], LIFT_READINGS[0]
SYNERA_STAIRS_M_PER_M = 2.0
SYNERA_LIFT_M_PER_M = 1.0


def _stairs_cost(mode: str, span: int, height: float) -> float:
    if mode == "per_stop":
        return STAIRS_COST_PER_FLOOR_M
    if mode == "per_metre":
        return SYNERA_STAIRS_M_PER_M * height
    return STAIRS_COST_PER_FLOOR_M * span


def _lift_ride_cost(mode: str, span: int, height: float) -> float:
    """Ride cost without the wait."""
    if mode.startswith("synera"):
        return SYNERA_LIFT_M_PER_M * height
    return LIFT_COST_PER_FLOOR_M * span


def variant_graph(
    bm: BuildingMap, step_free: bool, stairs: str, lift: str, lifts_allowed: bool = True
) -> nx.MultiGraph:
    """BuildingMap.graph with another vertical cost model. The defaults reproduce BuildingMap.graph exactly."""
    graph = nx.MultiGraph()
    anchors = {space_id: bm.anchor(space_id) for space_id in bm.spaces if space_id not in bm.closed}
    graph.add_nodes_from(anchors)
    for opening in bm.openings.values():
        if opening["id"] in bm.closed or (step_free and not opening["step_free"]):
            continue
        door = DOOR_PREFIX + opening["id"]
        for space_id in opening["space_ids"]:
            if space_id == OUTSIDE:
                graph.add_edge(OUTSIDE, door, weight=0.0, via=opening["id"])
            elif space_id in anchors:
                graph.add_edge(
                    space_id, door, weight=math.dist(anchors[space_id], opening["position"]), via=opening["id"]
                )
    levels = {floor_id: floor["level"] for floor_id, floor in bm.floors.items()}
    for connector in bm.connectors.values():
        if connector["id"] in bm.closed or (step_free and not connector["step_free"]):
            continue
        is_lift = connector["kind"] == LIFT
        if is_lift and not lifts_allowed:
            continue
        stops = sorted(zip(connector["floor_ids"], connector["space_ids"], strict=True), key=lambda s: levels[s[0]])
        wait_once = is_lift and lift.endswith("wait_once")
        ride_nodes: list[tuple] = []
        for index, ((low_floor, low_space), (high_floor, high_space)) in enumerate(itertools.pairwise(stops)):
            if low_space not in anchors or high_space not in anchors:
                continue
            span = abs(levels[high_floor] - levels[low_floor])
            height = abs(bm.floors[high_floor]["elevation_m"] - bm.floors[low_floor]["elevation_m"])
            if not is_lift:
                graph.add_edge(low_space, high_space, weight=_stairs_cost(stairs, span, height), via=connector["id"])
            elif not wait_once:
                cost = LIFT_WAIT_COST_M + _lift_ride_cost(lift, span, height)
                graph.add_edge(low_space, high_space, weight=cost, via=connector["id"])
            else:
                # wait once per ride: half the wait on entering a stop, half on leaving it, ride nodes in between
                low_node, high_node = ("ride", connector["id"], low_space), ("ride", connector["id"], high_space)
                for space_id, node in ((low_space, low_node), (high_space, high_node)):
                    graph.add_edge(space_id, node, weight=LIFT_WAIT_COST_M / 2, via=connector["id"])
                graph.add_edge(low_node, high_node, weight=_lift_ride_cost(lift, span, height), via=connector["id"])
                ride_nodes += [low_node, high_node]
    return graph


@contextlib.contextmanager
def vertical_model(stairs: str, lift: str, lifts_allowed: bool = True) -> Iterator[None]:
    """Patch BuildingMap.graph for the duration of one reading."""
    original = BuildingMap.graph

    def patched(self: BuildingMap, step_free: bool) -> nx.MultiGraph:
        return variant_graph(self, step_free, stairs, lift, lifts_allowed)

    BuildingMap.graph = patched  # type: ignore[method-assign]
    try:
        yield
    finally:
        BuildingMap.graph = original  # type: ignore[method-assign]


# ---------- readings ----------


@dataclass(frozen=True)
class Reading:
    kind: str
    name: str
    group: str  # which ambiguity this reading belongs to (recommendations are per group)
    run: Callable[[BuildingMap, dict], object]  # -> comparable value (number or space id)
    is_default: bool = False


def _vertical_reading(kind: str, fn: Callable[[BuildingMap, dict], object], stairs, lift, allowed=True) -> Reading:
    def run(bm: BuildingMap, inputs: dict) -> object:
        with vertical_model(stairs, lift, allowed):
            try:
                return fn(bm, inputs)
            except MapError:
                return UNREACHABLE  # e.g. the only way up is a lift and lifts are forbidden

    name = f"stairs={stairs}, lifts={lift if allowed else 'forbidden'}"
    is_default = (stairs, lift, allowed) == (DEFAULT_STAIRS, DEFAULT_LIFT, True)
    group = "lifts_allowed" if not allowed else "vertical_cost"
    return Reading(kind, name, group, run, is_default)


def errand_readings() -> list[Reading]:
    def length(bm: BuildingMap, inputs: dict) -> object:
        return errand(bm, **inputs)["length_m"]

    found = [
        _vertical_reading("errand", length, s, lift) for s, lift in itertools.product(STAIRS_READINGS, LIFT_READINGS)
    ]
    found += [_vertical_reading("errand", length, s, DEFAULT_LIFT, allowed=False) for s in STAIRS_READINGS]
    return found


def _is_room_or_hall(space: dict) -> bool:
    return space["type"] in ("room", "hall")


def _is_room_type(space: dict) -> bool:
    return space["type"] == "room"


def _is_non_connector(space: dict) -> bool:
    return space["type"] not in CONNECTOR_TYPES


def what_if_door_readings() -> list[Reading]:
    def count(bm: BuildingMap, inputs: dict, **readings) -> object:
        return what_if_door_with(bm, **inputs, **readings)["count"]

    found = [
        _vertical_reading("what_if_door", count, s, lift)
        for s, lift in itertools.product(STAIRS_READINGS, LIFT_READINGS)
    ]
    found += [
        Reading("what_if_door", "door=longest stretch", "door_position", lambda bm, i: count(bm, i), True),
        Reading(
            "what_if_door",
            "door=all stretches combined",
            "door_position",
            lambda bm, i: count(bm, i, door_mode="combined"),
        ),
        Reading(
            "what_if_door",
            "door=shared-wall centroid",
            "door_position",
            lambda bm, i: count(bm, i, door_mode="centroid"),
        ),
        Reading("what_if_door", "threshold=strict >1 m", "door_threshold", lambda bm, i: count(bm, i), True),
        Reading("what_if_door", "threshold=at least 1 m", "door_threshold", lambda bm, i: count(bm, i, inclusive=True)),
        Reading("what_if_door", "rooms=rooms and halls", "door_rooms", lambda bm, i: count(bm, i), True),
        Reading(
            "what_if_door", "rooms=type room only", "door_rooms", lambda bm, i: count(bm, i, counted=_is_room_type)
        ),
    ]
    assert is_room({"type": "hall", "room_type": "generic_room"}), "production counts halls; keep the label in sync"
    return found


def shared_walls_readings() -> list[Reading]:
    found = []
    for tolerance, overlap, halls in itertools.product((0.2, 0.35, 0.5), (0.9, 1.0, 1.1), (False, True)):
        excluded = frozenset({"hall"}) if halls else frozenset()

        def run(bm, inputs, tolerance=tolerance, overlap=overlap, excluded=excluded):
            return shared_walls_count_with(
                bm, **inputs, wall_thickness_m=tolerance, min_shared_m=overlap, also_excluded_types=excluded
            )["count"]

        name = f"tolerance={tolerance} m, overlap>={overlap} m, halls {'excluded' if halls else 'counted'}"
        group = "walls_halls" if halls else "walls_geometry"
        found.append(Reading("shared_walls_count", name, group, run, (tolerance, overlap, halls) == (0.35, 1.0, False)))
    return found


def wide_delivery_readings() -> list[Reading]:
    found = []
    for strict, counted, label in itertools.product((False, True), (_is_room_type, _is_non_connector), ("room", "all")):
        if (counted is _is_room_type) != (label == "room"):
            continue

        def run(bm, inputs, strict=strict, counted=counted):
            return wide_delivery_count_with(bm, **inputs, strict=strict, counted=counted)["count"]

        name = f"width={'strictly greater' if strict else 'at least'}, count={'type room only' if label == 'room' else 'all non-connector'}"
        group = "wide_threshold" if label == "room" else "wide_counted"
        found.append(Reading("wide_delivery_count", name, group, run, not strict and label == "room"))
    return found


def step_free_readings() -> list[Reading]:
    found = [
        Reading(
            "step_free_reachable_count",
            "count=type room only",
            "stepfree_counted",
            lambda bm, i: step_free_reachable_count_with(bm, **i)["count"],
            True,
        )
    ]
    for label, counted in (("rooms and halls", _is_room_or_hall), ("all non-connector", _is_non_connector)):
        found.append(
            Reading(
                "step_free_reachable_count",
                f"count={label}",
                "stepfree_counted",
                lambda bm, i, counted=counted: step_free_reachable_count_with(bm, **i, counted=counted)["count"],
            )
        )
    return found


def room_stacked_readings() -> list[Reading]:
    def run(**readings) -> Callable[[BuildingMap, dict], object]:
        return lambda bm, inputs: room_stacked_with(bm, **inputs, **readings)["space_id"]

    return [
        Reading("room_stacked", "rank=largest intersection, next existing floor", "stacked_rank", run(), True),
        Reading("room_stacked", "rank=intersection over union", "stacked_rank", run(metric="iou")),
        Reading("room_stacked", "floor=level +-1 only", "stacked_floor", run(adjacent_level_only=True)),
        Reading("room_stacked", "candidates=no outdoor", "stacked_types", run(excluded_types=frozenset({"outdoor"}))),
        Reading(
            "room_stacked",
            "candidates=rooms and halls only",
            "stacked_types",
            run(excluded_types=frozenset({"corridor", "stair", "lift", "outdoor"})),
        ),
    ]


READINGS: dict[str, list[Reading]] = {
    "errand": errand_readings(),
    "what_if_door": what_if_door_readings(),
    "shared_walls_count": shared_walls_readings(),
    "wide_delivery_count": wide_delivery_readings(),
    "step_free_reachable_count": step_free_readings(),
    "room_stacked": room_stacked_readings(),
}

# ---------- data ----------


@dataclass
class Item:
    id: str
    kind: str
    building_dir: str
    inputs: dict
    label: object = None  # labelled questions only: number or space id
    tolerance: tuple[float, float] = (0.0, 0.0)  # (absolute, relative) of the scorer
    current: object = None  # test only: the number or room in our submitted answer line


_MAPS: dict[str, BuildingMap] = {}


def load_map(building_dir: str) -> BuildingMap:
    if building_dir not in _MAPS:
        _MAPS[building_dir] = BuildingMap.load(Path(building_dir))
    return _MAPS[building_dir]


def label_of(answer: dict) -> tuple[object, tuple[float, float]]:
    if answer["type"] == "space":
        return answer["space_id"], (0.0, 0.0)
    return answer["value"], (answer.get("absolute_tolerance", 0.0), answer.get("relative_tolerance", 0.0))


def labelled_items(kind: str) -> list[Item]:
    items = []
    for building_dir, question in labelled_questions(kind):
        label, tolerance = label_of(question["answer"])
        items.append(Item(question["id"], kind, building_dir, question["inputs"], label, tolerance))
    return items


def answer_line(reply: str) -> str:
    lines = [line for line in reply.splitlines() if re.match(r"\W*Answer:", line.strip(), re.IGNORECASE)]
    return lines[-1].split(":", 1)[1].strip().strip("*").strip() if lines else ""


def current_value(kind: str, line: str, inputs: dict, bm: BuildingMap) -> object:
    if kind == "room_stacked":
        wanted = line.strip().lower()
        found = [s["id"] for s in bm.spaces.values() if wanted in (s["name"].lower(), (s.get("ref") or "").lower())]
        return found if found else line
    number = re.search(r"-?\d+(?:\.\d+)?", line)
    return float(number.group()) if number else None


def test_items(kinds: set[str], answers: dict[str, str]) -> tuple[list[Item], list[str]]:
    """Parsed test questions of the given kinds, plus ids that could not be parsed (answered by the LLM)."""
    items, unparsed = [], []
    for path in sorted((DATA / "test").glob("*/questions.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            question = json.loads(line)
            if question["kind"] not in kinds:
                continue
            bm = load_map(str(path.parent))
            parsed = parse_question(bm, question["question"])
            if parsed is None:
                unparsed.append(question["id"])
                continue
            current = current_value(question["kind"], answer_line(answers.get(question["id"], "")), parsed.inputs, bm)
            items.append(Item(question["id"], question["kind"], str(path.parent), parsed.inputs, current=current))
    return items, unparsed


def same_answer(kind: str, alternative: object, reference: object, tolerance: tuple[float, float]) -> bool:
    """Would `reference` be scored correct if `alternative` were the truth?"""
    if alternative == UNREACHABLE or reference == UNREACHABLE:
        return alternative == reference
    if isinstance(alternative, float) or isinstance(reference, float):
        if reference is None:
            return False
        return abs(float(reference) - float(alternative)) <= max(tolerance[0], tolerance[1] * float(alternative)) + 1e-9
    if isinstance(reference, list):
        return alternative in reference
    return alternative == reference


# kinds whose scorer tolerance matters on test answers: errand is within 1 % (at least 1 m)
TEST_TOLERANCE = {"errand": (1.0, 0.01)}

# ---------- evaluation ----------


@dataclass
class ReadingResult:
    reading: Reading
    label_total: int = 0
    label_agree: int = 0
    label_differs_from_default: int = 0
    test_values: dict[str, object] = field(default_factory=dict)
    test_changed: list[str] = field(default_factory=list)
    ruled_out: bool = False


def evaluate_kind(kind: str, tests: list[Item]) -> list[ReadingResult]:
    labelled = labelled_items(kind)
    readings = READINGS[kind]
    default = next(r for r in readings if r.is_default)
    default_label_values = {item.id: default.run(load_map(item.building_dir), item.inputs) for item in labelled}
    default_test_values = {item.id: default.run(load_map(item.building_dir), item.inputs) for item in tests}
    default_agree = sum(same_answer(kind, default_label_values[i.id], i.label, i.tolerance) for i in labelled)
    results = []
    for reading in readings:
        result = ReadingResult(reading, label_total=len(labelled))
        for item in labelled:
            value = reading.run(load_map(item.building_dir), item.inputs)
            result.label_agree += same_answer(kind, value, item.label, item.tolerance)
            result.label_differs_from_default += not same_answer(
                kind, value, default_label_values[item.id], item.tolerance
            )
        result.ruled_out = result.label_agree < default_agree
        tolerance = TEST_TOLERANCE.get(kind, (0.0, 0.0))
        for item in tests:
            value = reading.run(load_map(item.building_dir), item.inputs)
            result.test_values[item.id] = value
            reference = item.current if item.current is not None else default_test_values[item.id]
            if not same_answer(kind, value, reference, tolerance):
                result.test_changed.append(item.id)
        results.append(result)
    return results


# ---------- report ----------

# (title, reading groups, recommendation, one-sentence question for Synera). The recommendations are written
# against the kit labels; if the data changes, re-read the tables above before trusting them.
FRAGILE_ROWS = 15
RECOMMENDATIONS: list[tuple[str, tuple[str, ...], str, str]] = [
    (
        "Vertical cost (errand, what_if_door)",
        ("vertical_cost",),
        (
            "Keep the kit model: stairs 12 m per level difference, lifts 15 m wait plus 6 m per floor on every hop. "
            "It reproduces every labelled errand answer; 2 m per metre for stairs contradicts most labels, and "
            "waiting once per ride contradicts several. Only connectors with more than two stops tell the "
            "wait-once reading apart."
        ),
        (
            "For errand and what-if-door distances, is a lift ride from floor 0 to floor 2 charged the wait once "
            "(15 m plus 6 m per floor) or again at every intermediate stop, and do stairs cost 12 m per floor or 2 m "
            "per metre climbed?"
        ),
    ),
    (
        "Lifts in the errand (errand)",
        ("lifts_allowed",),
        "Keep lifts allowed. Stairs-only with the kit costs contradicts a label and changes no test answer.",
        (
            "When an errand question says 'I can carry it on the stairs', may the route use a lift as well, or "
            "stairs only?"
        ),
    ),
    (
        "Door position (what_if_door)",
        ("door_position",),
        "Keep the longest stretch. Labels cannot separate the three positions, but none of them changes a test answer.",
        (
            "For a what-if door, is 'the middle of the wall they share' the middle of the longest shared stretch, "
            "or the middle of all shared stretches together?"
        ),
    ),
    (
        "Threshold (what_if_door)",
        ("door_threshold",),
        "Keep strictly more than 1 m (the wording says so). No test answer changes.",
        "Does 'shorter by more than 1 m' exclude a gain of exactly 1.00 m?",
    ),
    (
        "Rooms counted (what_if_door)",
        ("door_rooms",),
        "Keep rooms plus halls. Labels cannot separate it from type room only; no test answer changes.",
        "In the what-if-door count, do halls (lobbies, large open spaces) count as rooms, or only spaces of type room?",
    ),
    (
        "Wall tolerance and overlap (shared_walls_count)",
        ("walls_geometry",),
        "Keep 0.35 m and 1.0 m. Labels cannot separate 0.2 to 0.5 m or 0.9 to 1.1 m, and no test answer changes.",
        "Is the shared-wall test 'at least 1 m of outline within 0.35 m', and is that threshold exact?",
    ),
    (
        "Halls (shared_walls_count)",
        ("walls_halls",),
        "Keep halls counted. Excluding them contradicts 19 labels.",
        (
            "Should halls count as neighbours in the shared-wall question, given that only corridors, stairwells and "
            "lifts are listed as excluded?"
        ),
    ),
    (
        "Door width and counted spaces (wide_delivery_count)",
        ("wide_threshold", "wide_counted"),
        "Keep 'at least' and type room only. Strictly greater and all non-connector spaces both contradict labels.",
        "Does a door exactly as wide as the item pass (at least, not strictly wider), and are only spaces of type room counted as delivery targets?",
    ),
    (
        "Counted spaces (step_free_reachable_count)",
        ("stepfree_counted",),
        "Keep type room only. The sensible alternatives agree with the two labels and the test has no such question.",
        "In the step-free reach count, do halls count as rooms?",
    ),
    (
        "Stacking rule (room_stacked)",
        ("stacked_rank", "stacked_floor", "stacked_types"),
        "Keep the largest intersection on the next existing floor. All alternatives agree on every label and test answer.",
        "Is 'directly above' the space with the largest overlap area, or the largest overlap share of either room?",
    ),
]


def fmt(value: object) -> str:
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def render(
    per_kind: dict[str, list[ReadingResult]],
    tests: list[Item],
    unparsed: list[str],
    answers_total: int,
    mismatches: list[str],
) -> str:
    out = ["# Rule sensitivity of the test answers", ""]
    out.append(
        "Generated by `scripts/rule_sensitivity.py` (deterministic, no API calls). Do not edit the generated tables by hand."
    )
    out.append("")
    sensitive: dict[str, list[tuple[Reading, object]]] = defaultdict(list)
    for kind, results in per_kind.items():
        for result in results:
            if result.ruled_out:
                continue
            for question_id in result.test_changed:
                sensitive[question_id].append((result.reading, result.test_values[question_id]))
    kinds_hit = sorted({item.kind for item in tests if item.id in sensitive})
    out.append(
        f"**{len(sensitive)} of {answers_total} test answers are sensitive** to a reading that the labels do not rule out."
    )
    out.append(
        f"Kinds: {', '.join(kinds_hit) or 'none'}. Not varied (README definition is precise): floor_area_total, largest_room, straight_line_3d."
    )
    out.append("")
    out.append(
        "A reading is ruled out when it agrees with fewer train/dev labels than the production default. "
        "'Label-neutral' means the labels cannot tell it apart from the default (no labelled question changes), "
        "so it is a real open question. Errand answers count as changed only outside the scorer tolerance (1 %, at least 1 m)."
    )
    if unparsed:
        out.append("")
        out.append(f"Test questions the deterministic parser does not handle (not analysed): {', '.join(unparsed)}")
    if mismatches:
        out.append("")
        out.append(f"Submitted answer differs from the production default recomputed here: {', '.join(mismatches)}")
    out.append("")
    for kind, results in per_kind.items():
        kind_tests = [item for item in tests if item.kind == kind]
        out.append(f"## {kind} ({len(kind_tests)} test questions)")
        out.append("")
        out.append("| Reading | Labels agree | Labels differing from default | Verdict | Test answers changed | Ids |")
        out.append("|---|---|---|---|---|---|")
        for result in results:
            reading = result.reading
            if reading.is_default:
                verdict = "default"
            elif result.ruled_out:
                verdict = "ruled out by labels"
            elif result.label_differs_from_default == 0:
                verdict = "label-neutral"
            else:
                verdict = "consistent with labels"
            ids = ", ".join(result.test_changed) if not reading.is_default else ""
            changed = "" if reading.is_default else str(len(result.test_changed))
            out.append(
                f"| {reading.name} | {result.label_agree}/{result.label_total} | {result.label_differs_from_default} | {verdict} | {changed} | {ids} |"
            )
        out.append("")
    by_id = {item.id: item for item in tests}
    out.append("## Sensitive test questions")
    out.append("")
    out.append("Readings not ruled out by the labels only. Current answer is what we submitted.")
    out.append("")
    if sensitive:
        out.append("| Id | Kind | Current | Alternative answers (reading) |")
        out.append("|---|---|---|---|")
        for question_id in sorted(sensitive):
            item = by_id[question_id]
            current = item.current if item.current is not None else "?"
            alternatives = "; ".join(f"{fmt(value)} ({reading.name})" for reading, value in sensitive[question_id])
            out.append(f"| {question_id} | {item.kind} | {fmt(current)} | {alternatives} |")
    else:
        out.append("None.")
    out.append("")
    out.append("## Fragile test questions (change only under readings the labels rule out)")
    out.append("")
    out.append(
        "Ranked by how many labels the best-supported contradicting reading still gets right. "
        "These are safe as long as the kit labels describe the real scoring."
    )
    out.append("")
    out.append("| Id | Kind | Current | Alternative (reading) | Labels that reading gets right |")
    out.append("|---|---|---|---|---|")
    fragile = []
    for results in per_kind.values():
        for result in results:
            if not result.ruled_out:
                continue
            for question_id in result.test_changed:
                share = result.label_agree / result.label_total if result.label_total else 0.0
                fragile.append((share, question_id, result))
    best: dict[str, tuple[float, ReadingResult]] = {}
    for share, question_id, result in fragile:
        if question_id not in best or share > best[question_id][0]:
            best[question_id] = (share, result)
    for question_id, (share, result) in sorted(best.items(), key=lambda entry: (-entry[1][0], entry[0]))[:FRAGILE_ROWS]:
        item = by_id[question_id]
        current = item.current if item.current is not None else "?"
        value = result.test_values[question_id]
        out.append(
            f"| {question_id} | {item.kind} | {fmt(current)} | {fmt(value)} ({result.reading.name}) | "
            f"{result.label_agree}/{result.label_total} |"
        )
    out.append(f"\n{len(best)} test questions change under at least one reading that is ruled out.")
    out.append("")
    out.append("## Recommendations and questions for Synera")
    out.append("")
    for title, groups, recommendation, question in RECOMMENDATIONS:
        open_changed = {
            question_id
            for results in per_kind.values()
            for result in results
            if result.reading.group in groups and not result.ruled_out
            for question_id in result.test_changed
        }
        changed = sorted(
            {
                question_id
                for results in per_kind.values()
                for result in results
                if result.reading.group in groups
                for question_id in result.test_changed
            }
        )
        out.append(f"### {title}")
        out.append("")
        out.append(f"- Recommendation: {recommendation}")
        out.append(
            f"- Test answers changing: {len(open_changed)} under readings the labels allow, "
            f"{len(changed)} under any reading including ruled out ones"
        )
        out.append(f"- Ask Synera: {question}")
        out.append("")
    return "\n".join(out)


def count_test_questions() -> int:
    paths = (DATA / "test").glob("*/questions.jsonl")
    return sum(1 for path in paths for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def load_answers(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["question_id"]: row["answer"] for row in csv.DictReader(handle)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS, help="submitted CSV (question_id,answer)")
    parser.add_argument("--write", type=Path, help="write the report here instead of printing it")
    args = parser.parse_args()
    answers = load_answers(args.answers)
    tests, unparsed = test_items(set(READINGS), answers)
    per_kind = {kind: evaluate_kind(kind, [i for i in tests if i.kind == kind]) for kind in READINGS}
    mismatches = []
    for item in tests:
        default = next(r for r in per_kind[item.kind] if r.reading.is_default).test_values[item.id]
        if item.current is not None and not same_answer(
            item.kind, default, item.current, TEST_TOLERANCE.get(item.kind, (0.0, 0.0))
        ):
            mismatches.append(item.id)
    report = render(per_kind, tests, unparsed, count_test_questions(), mismatches)
    if args.write:
        args.write.write_text(report + "\n", encoding="utf-8")
    else:
        print(report)


if __name__ == "__main__":
    main()
