"""Comparison logic for the parameter-reading eval (scripts/eval_params.py). No API access here."""

from building_agent.find_space import find_space
from starter_agent.building_map import BuildingMap, MapError

MISSING = "<missing>"


def resolve_space(bm: BuildingMap, value: str) -> str | None:
    """Space id for a value the model passed (an id, or a room name/number). None if it is not unique."""
    if value in bm.spaces:
        return value
    try:
        result = find_space(bm, value)
    except MapError:
        return None
    return result["match"]["id"] if "match" in result else None


def param_matches(bm: BuildingMap, expected: object, got: object) -> bool:
    if isinstance(expected, str) and expected in bm.spaces:
        return isinstance(got, str) and resolve_space(bm, got) == expected
    if isinstance(expected, str) and expected in bm.floors:
        return got == expected
    if isinstance(expected, str) and isinstance(got, str):
        return expected.strip().lower() == got.strip().lower()
    return expected == got


def compare_params(bm: BuildingMap, expected: dict, got: dict) -> list[tuple[str, object, object]]:
    """Mismatches as (parameter, expected, got); empty when every parameter is right."""
    return [
        (key, expected.get(key, MISSING), got.get(key, MISSING))
        for key in sorted(set(expected) | set(got))
        if key not in expected or key not in got or not param_matches(bm, expected[key], got[key])
    ]
