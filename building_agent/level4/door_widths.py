"""Estimated door widths for buildings built from plans.

The plan (SVG or PNG) draws every door as a marker of the same size, so it carries no door width: the marker size,
checked on the kit plans, is a constant. Widths are therefore an ESTIMATE from what the plan does show, the kind of
the opening and the rooms on both sides. Two layers, the more specific one wins:

1. `room_types`: a table of median widths per (opening kind, room types of both sides), fitted on the labelled
   train buildings (scripts/fit_door_widths.py writes door_width_table.json). Used only when both sides have a
   specific room type (a vision reading or a name gave one); `generic_room` counts as unknown.
2. `class`: a small rule on what a plan shows in colour: an `opening` (a gap without a door leaf) is wide, a door to
   a stair, lift or hall is wide, anything else stays at the default.

Everything else (unknown kind, missing sides) gets the default of 0.9 m. A width that the plan really gave is never
passed here, see `apply_estimates`. Pure functions, no I/O except the one table file."""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DEFAULT_WIDTH_M = 0.9
OPENING_WIDTH_M = 2.0  # an opening is a gap in the wall; the kit's are 1.2 m and far wider
WIDE_DOOR_WIDTH_M = 1.2  # doors to stairs, lifts and halls
WIDE_CLASSES = {"stair", "lift", "hall"}
CLASS_TYPES = {"corridor", "hall", "stair", "lift", "outdoor"}
UNKNOWN_ROOM_TYPE = "generic_room"
OUTSIDE_LABEL = "outside"
MIN_TABLE_COUNT = 10
TABLE_PATH = Path(__file__).with_name("door_width_table.json")

RULE_ROOM_TYPES = "room_types"
RULE_CLASS = "class"
RULE_DEFAULT = "default"


@dataclass(frozen=True)
class WidthEstimate:
    width_m: float
    rule: str  # room_types, class or default
    note: str  # one plain sentence on why


def side_labels(space: dict | None) -> tuple[str, str | None]:
    """(coarse class, specific room type or None) of one side of an opening; None space = outside."""
    if space is None:
        return OUTSIDE_LABEL, OUTSIDE_LABEL
    kind = space.get("type")
    coarse = kind if kind in CLASS_TYPES else "room"
    room_type = space.get("room_type")
    if kind in ("room", "outdoor"):
        specific = room_type if isinstance(room_type, str) and room_type != UNKNOWN_ROOM_TYPE else None
    else:
        specific = kind if kind in CLASS_TYPES else None
    return coarse, specific


def table_key(kind: str, fine_a: str, fine_b: str) -> str:
    first, second = sorted((fine_a, fine_b))
    return f"{kind}|{first}+{second}"


@cache
def load_table(path: Path = TABLE_PATH) -> dict[str, float]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): float(value) for key, value in raw["widths"].items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def estimate(kind: object, sides: Sequence[dict | None], table: dict[str, float] | None = None) -> WidthEstimate:
    """Estimated width of an opening of `kind` between `sides` (space dicts, None for outside)."""
    if kind not in ("door", "opening") or len(sides) != 2:
        return WidthEstimate(DEFAULT_WIDTH_M, RULE_DEFAULT, "No evidence for this kind of opening, default width.")
    labels = [side_labels(side) for side in sides]
    fine = [label[1] for label in labels]
    widths = load_table() if table is None else table
    if fine[0] and fine[1]:
        known = widths.get(table_key(str(kind), fine[0], fine[1]))
        if known is not None:
            note = f"Typical {kind} between {fine[0]} and {fine[1]} in the training buildings."
            return WidthEstimate(known, RULE_ROOM_TYPES, note)
    coarse = {label[0] for label in labels}
    if kind == "opening":
        return WidthEstimate(OPENING_WIDTH_M, RULE_CLASS, "An opening without a door leaf is wide.")
    if coarse & WIDE_CLASSES:
        return WidthEstimate(WIDE_DOOR_WIDTH_M, RULE_CLASS, "Doors to stairs, lifts and halls are wider.")
    return WidthEstimate(DEFAULT_WIDTH_M, RULE_DEFAULT, "No evidence for a different width, default.")


def apply_estimates(
    openings: list[dict],
    spaces: list[dict],
    estimated_ids: set[str],
    note: Callable[[str, str], None],
) -> None:
    """Replace `width_m` of the openings in `estimated_ids` (the plan gave no width) by the estimate.

    `note(code, item)` is called once per rule that changed at least one width, so the card can say so."""
    by_id = {space["id"]: space for space in spaces}
    used: dict[str, int] = {}
    for opening in openings:
        if opening.get("id") not in estimated_ids:
            continue
        sides = [by_id.get(space_id) for space_id in opening.get("space_ids", [])]
        result = estimate(opening.get("kind"), sides)
        if result.rule == RULE_DEFAULT:
            continue
        opening["width_m"] = result.width_m
        used[result.rule] = used.get(result.rule, 0) + 1
    for rule, count in sorted(used.items()):
        note("door_widths_estimated", f"{count} by rule {rule}")
