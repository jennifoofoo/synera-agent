"""Comparison logic for the parameter-reading eval (scripts/eval_params.py). No API access here."""

from building_agent.find_space import find_space
from building_agent.tools import snake_case
from starter_agent.building_map import BuildingMap, MapError

MISSING = "<missing>"

# claude-haiku-5-5, USD per million tokens, prompts up to 100K tokens (claude-api skill model table, cached 2026-10-06).
PRICE_INPUT_PER_MTOK = 0.10
PRICE_OUTPUT_PER_MTOK = 0.50


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * PRICE_INPUT_PER_MTOK + output_tokens * PRICE_OUTPUT_PER_MTOK) / 1_000_000


def resolve_space(bm: BuildingMap, value: str) -> str | None:
    """Space id for a value the model passed (an id, or a room name/number). None if it is not unique."""
    if value in bm.spaces:
        return value
    try:
        result = find_space(bm, value)
    except MapError:
        return None
    return result["match"]["id"] if "match" in result else None


def param_matches(bm: BuildingMap, expected: object, got: object, key: str = "") -> bool:
    expected, got = snake_case(key, expected), snake_case(key, got)
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
        if key not in expected or key not in got or not param_matches(bm, expected[key], got[key], key)
    ]


def classify_mismatch(bm: BuildingMap, key: str, expected: object, got: object) -> str:
    """Short pattern label for one mismatch, used to group recurring errors."""
    if key == "TOOL":
        return "wrong tool" if got else "no tool call"
    if got == MISSING:
        return "parameter missing"
    if expected == MISSING:
        return "unexpected extra parameter"
    if isinstance(expected, str) and expected in bm.floors:
        return "wrong floor id"
    if isinstance(expected, str) and expected in bm.spaces:
        if not isinstance(got, str):
            return "room: not a string"
        if got in bm.spaces:
            return "room: wrong id"
        resolved = resolve_space(bm, got)
        if resolved is None:
            return "room: name not unique or unknown"
        return "room: name resolves to other room"
    if key.endswith("_type"):
        return "wrong *_type value"
    if isinstance(expected, (int, float)) and isinstance(got, (int, float)):
        return "wrong number"
    if type(expected) is not type(got):
        return "wrong value type"
    return "other value"


def group_mismatches(bm_for: dict, mismatches: list[tuple[str, str, str, object, object]]) -> dict[str, list]:
    """Group (kind, question_id, parameter, expected, got) by pattern; bm_for maps question_id to its BuildingMap."""
    groups: dict[str, list] = {}
    for kind, question_id, key, expected, got in mismatches:
        label = classify_mismatch(bm_for[question_id], key, expected, got)
        groups.setdefault(label, []).append((kind, question_id, key, expected, got))
    return dict(sorted(groups.items(), key=lambda item: -len(item[1])))

