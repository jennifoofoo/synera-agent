"""Robustness sweep over every train/dev/test building. No API calls.

Each registered kind runs on inputs derived from the building's own data. Allowed outcomes: a dict or MapError."""

import inspect
import math
import time
import traceback
from pathlib import Path

import pytest

from building_agent.registry import load_kinds
from starter_agent.building_map import MapError
from tests.conftest import load_map
from tests.sweep_inputs import GENERATORS, Pools, build_inputs, known_params

BUILDINGS = sorted(str(path.parent) for path in Path("data").glob("*/*/building.json"))
KINDS = load_kinds()
TIMING_LIMIT_S = 10.0
SPACE_KEYS = {"space_id", "via", "target"}
COORDINATE_KEYS = {"door_position", "first", "second"}

def _name(path: str) -> str:
    return Path(path).name


def _check_numbers(value, path: str, problems: list[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(value) or value < 0:
            problems.append(f"{path}={value}")
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in COORDINATE_KEYS:
                _check_numbers(item, f"{path}.{key}", problems)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _check_numbers(item, f"{path}[{index}]", problems)


def _check_space_ids(result: dict, bm, problems: list[str]) -> None:
    for key, value in result.items():
        if key in SPACE_KEYS and isinstance(value, str) and value not in bm.spaces:
            problems.append(f"unknown space {key}={value}")
        if key == "space_ids":
            problems.extend(f"unknown space in space_ids: {item}" for item in value if item not in bm.spaces)


def _run(kind_name: str, building_dir: str, inputs: dict) -> str | None:
    bm = load_map(building_dir)
    label = f"{kind_name} on {_name(building_dir)} with {inputs}"
    try:
        result = KINDS[kind_name].fn(bm, **inputs)
    except MapError:
        return None
    except Exception:  # noqa: BLE001
        tail = "".join(traceback.format_exc().splitlines(keepends=True)[-4:])
        return f"{label} crashed:\n{tail}"
    if not isinstance(result, dict):
        return f"{label} returned {type(result).__name__}"
    problems: list[str] = []
    _check_numbers(result, "result", problems)
    _check_space_ids(result, bm, problems)
    return f"{label} implausible: {problems}" if problems else None


def test_every_kind_has_a_generator():
    missing = set(KINDS) - set(GENERATORS)
    assert not missing, f"Add an input generator in tests/sweep_inputs.py for new kinds: {sorted(missing)}"


@pytest.mark.parametrize("kind_name", sorted(KINDS))
def test_generator_covers_every_parameter(kind_name):
    assert kind_name in GENERATORS, f"No generator for kind {kind_name}"
    inputs = build_inputs(kind_name, Pools(load_map(BUILDINGS[0]), "probe"))
    provided = set().union(*(set(item) for item in inputs))
    assert provided == known_params(KINDS[kind_name].fn), (
        f"Generator for {kind_name} does not match signature {inspect.signature(KINDS[kind_name].fn)}"
    )


@pytest.mark.parametrize("building_dir", BUILDINGS, ids=_name)
def test_sweep_building(building_dir):
    pools = Pools(load_map(building_dir), _name(building_dir))
    failures = []
    for kind_name in sorted(KINDS):
        for inputs in build_inputs(kind_name, pools):
            message = _run(kind_name, building_dir, inputs)
            if message:
                failures.append(message)
    assert not failures, "\n".join(failures)


def test_largest_building_is_fast():
    largest = max(BUILDINGS, key=lambda path: len(load_map(path).spaces))
    pools = Pools(load_map(largest), "timing")
    timings = {}
    for kind_name in sorted(KINDS):
        inputs = build_inputs(kind_name, pools)[0]
        start = time.perf_counter()
        _run(kind_name, largest, inputs)
        timings[kind_name] = time.perf_counter() - start
    slowest = max(timings, key=timings.get)
    assert timings[slowest] < TIMING_LIMIT_S, (
        f"{slowest} took {timings[slowest]:.1f}s on {_name(largest)} ({len(load_map(largest).spaces)} spaces)"
    )
