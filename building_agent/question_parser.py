"""Deterministic fast path: parse a benchmark sentence into kind inputs, answer without an LLM.

The published questions come from a few fixed sentence templates. A parse is only returned when the whole
sentence matches a template and every name, type and floor resolves uniquely in the building's own data.
Anything else returns None so the LLM agent can answer."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from building_agent.registry import load_kinds
from starter_agent.building_map import BuildingMap

MAX_TEXT_LENGTH = 1500

FLOOR = r"(?:ground floor|floor -?\d+|basement \d+)"
ROOM = rf"(?P<{{n}}>.+?) \((?P<{{f}}>{FLOOR})\)"
ON_FLOOR = rf"on the (?P<{{f}}>{FLOOR})"
TYPE = r"(?P<{n}>[a-z][a-z ]*?)"


def _room(n: str, f: str) -> str:
    return ROOM.format(n=n, f=f)


def _tail(answer: str) -> str:
    return rf" Finish with a line 'Answer: {answer}'\."


NUMBER_TAIL = _tail("<number>")
NAME_TAIL = _tail("<room name or number>")
LARGEST_TAIL = _tail("<room name or number>, <area> m²")
FLOOR_ON = ON_FLOOR.format(f="floor")

TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "largest_room": [
        (
            rf"Which is the largest {TYPE.format(n='type')} {FLOOR_ON}, and how big is it in m²\?" + LARGEST_TAIL,
            "largest_room",
        )
    ],
    "floor_area_total": [
        (
            rf"Facilities want the total floor area of every {TYPE.format(n='type')} {FLOOR_ON} added together\. "
            rf"How many square metres is that\?" + NUMBER_TAIL,
            "floor_area_total",
        )
    ],
    "errand": [
        (
            rf"I'm in {_room('start', 'start_floor')}\. I need to grab an? (?P<asset>[a-z][a-z ]*?) from the room "
            rf"that has one closest to me, then carry it to the largest {TYPE.format(n='type')} {FLOOR_ON}\. "
            rf"I can carry it on the stairs\. How far will I walk in total, in metres\?" + NUMBER_TAIL,
            "errand",
        )
    ],
    "wide_delivery_count": [
        (
            r"I'm moving an? (?P<w1>\d+(?:\.\d+)?) m wide (?P<item>[a-z][a-z ]*?)\. It can't go on stairs or steps "
            r"\(lifts are fine\), and every door it passes through must be at least (?P<w2>\d+(?:\.\d+)?) m wide\. "
            rf"It arrives through the entrance into {_room('start', 'start_floor')}\. "
            rf"Into how many rooms {FLOOR_ON} can it be delivered\?" + NUMBER_TAIL,
            "wide_delivery_count",
        )
    ],
    "step_free_reachable_count": [
        (
            r"(?P<closed>[A-Za-z][\w ]*?) is out of service\. A wheelchair user comes in through the entrance into "
            rf"{_room('start', 'start_floor')}\. How many rooms {FLOOR_ON} can they still reach\?" + NUMBER_TAIL,
            "step_free_reachable_count",
        )
    ],
    "room_stacked": [
        (
            rf"There's water dripping from the ceiling in {_room('start', 'start_floor')}\. "
            rf"Which room is directly above it\?" + NAME_TAIL,
            "above",
        ),
        (
            rf"A washing machine is leaking onto the floor of {_room('start', 'start_floor')}\. "
            rf"Which room directly below it will the water reach\?" + NAME_TAIL,
            "below",
        ),
    ],
    "shared_walls_count": [
        (
            rf"We're soundproofing {_room('start', 'start_floor')}\. How many other rooms on that floor share a wall "
            r"with it\? Count every room whose wall runs along it for at least 1 m, with or without a door between "
            r"them; corridors, stairwells and lifts don't count\." + NUMBER_TAIL,
            "shared_walls_count",
        )
    ],
    "straight_line_3d": [
        (
            rf"We're planning a wireless sensor link between {_room('first', 'first_floor')} and "
            rf"{_room('second', 'second_floor')}\. What is the straight-line distance in metres between the centres "
            r"of the two rooms \(each room's floor-plan centroid, at its floor's elevation\)\?" + NUMBER_TAIL,
            "straight_line_3d",
        )
    ],
    "what_if_door": [
        (
            rf"What if we add a door between {_room('first', 'first_floor')} and {_room('second', 'second_floor')}, "
            rf"in the middle of the wall they share\? How many rooms {FLOOR_ON} would then have a shorter walk out "
            r"of the building, to their nearest entrance, by more than 1 m\?" + NUMBER_TAIL,
            "what_if_door",
        )
    ],
}
COMPILED = [
    (kind, re.compile(pattern, re.IGNORECASE), tag) for kind, items in TEMPLATES.items() for pattern, tag in items
]


@dataclass
class ParsedQuestion:
    kind: str
    inputs: dict
    confidence: str = "exact"
    notes: list[str] = field(default_factory=list)


class ParseFailure(Exception):
    """The sentence is not safely understood; the message says why."""


def _floor_id(bm: BuildingMap, text: str) -> str:
    wanted = text.strip().lower()
    found = [floor["id"] for floor in bm.floors.values() if floor["name"].lower() == wanted]
    if len(found) != 1:
        raise ParseFailure(f"floor {text!r} not found" if not found else f"floor {text!r} is ambiguous")
    return found[0]


def _space_id(bm: BuildingMap, name: str, floor_text: str) -> str:
    floor_id = _floor_id(bm, floor_text)
    wanted = name.strip().lower()
    found = {
        space["id"]
        for space in bm.spaces.values()
        if space["floor_id"] == floor_id and wanted in (space["name"].lower(), (space.get("ref") or "").lower())
    }
    if len(found) != 1:
        raise ParseFailure(f"room {name!r} on {floor_text!r}: " + ("unknown" if not found else "ambiguous"))
    return next(iter(found))


def _type(values: set[str], phrase: str, what: str) -> str:
    snake = phrase.strip().lower().replace(" ", "_")
    for candidate in (snake, snake.removesuffix("s")):
        if candidate in values:
            return candidate
    raise ParseFailure(f"unknown {what} {phrase!r}")


def _connector_id(bm: BuildingMap, name: str) -> str:
    found = [c["id"] for c in bm.connectors.values() if c["name"].lower() == name.strip().lower()]
    if len(found) != 1:
        raise ParseFailure(f"element {name!r} " + ("unknown" if not found else "ambiguous"))
    return found[0]


def _inputs(bm: BuildingMap, kind: str, tag: str, g: dict) -> dict:
    room_types = {space["room_type"] for space in bm.spaces.values()}
    asset_types = {asset["type"] for asset in bm.assets.values()}
    if kind in ("largest_room", "floor_area_total"):
        return {"floor_id": _floor_id(bm, g["floor"]), "room_type": _type(room_types, g["type"], "room type")}
    if kind == "errand":
        return {
            "start": _space_id(bm, g["start"], g["start_floor"]),
            "asset_type": _type(asset_types, g["asset"], "asset type"),
            "floor_id": _floor_id(bm, g["floor"]),
            "room_type": _type(room_types, g["type"], "room type"),
        }
    if kind == "wide_delivery_count":
        if float(g["w1"]) != float(g["w2"]):
            raise ParseFailure("the two widths differ")
        return {
            "start": _space_id(bm, g["start"], g["start_floor"]),
            "floor_id": _floor_id(bm, g["floor"]),
            "min_width": float(g["w1"]),
        }
    if kind == "step_free_reachable_count":
        return {
            "closed": _connector_id(bm, g["closed"]),
            "start": _space_id(bm, g["start"], g["start_floor"]),
            "floor_id": _floor_id(bm, g["floor"]),
        }
    if kind == "room_stacked":
        return {"start": _space_id(bm, g["start"], g["start_floor"]), "direction": tag}
    if kind == "shared_walls_count":
        return {"start": _space_id(bm, g["start"], g["start_floor"])}
    if kind == "straight_line_3d":
        return {
            "first": _space_id(bm, g["first"], g["first_floor"]),
            "second": _space_id(bm, g["second"], g["second_floor"]),
        }
    if kind == "what_if_door":
        if g["first_floor"].lower() != g["second_floor"].lower():
            raise ParseFailure("the two rooms are on different floors")
        return {
            "first": _space_id(bm, g["first"], g["first_floor"]),
            "second": _space_id(bm, g["second"], g["second_floor"]),
            "door_floor_id": _floor_id(bm, g["first_floor"]),
            "floor_id": _floor_id(bm, g["floor"]),
        }
    raise ParseFailure(f"no parser for {kind}")


def parse_or_reason(bm: BuildingMap, text: str) -> ParsedQuestion | str:
    """The parse, or the reason there is none."""
    if not isinstance(text, str) or not text.strip():
        return "empty text"
    if len(text) > MAX_TEXT_LENGTH:
        return "text too long"
    normalised = " ".join(text.split())
    for kind, pattern, tag in COMPILED:
        match = pattern.fullmatch(normalised)
        if match:
            try:
                return ParsedQuestion(kind, _inputs(bm, kind, tag, match.groupdict()))
            except ParseFailure as failure:
                return f"{kind}: {failure}"
    return "no template matches"


def parse_question(bm: BuildingMap, text: str) -> ParsedQuestion | None:
    parsed = parse_or_reason(bm, text)
    return parsed if isinstance(parsed, ParsedQuestion) else None


def _format_reply(bm: BuildingMap, parsed: ParsedQuestion, result: dict) -> str:
    kind = parsed.kind
    if kind == "largest_room":
        return (
            f"The largest one is {result['name']} with {result['area_m2']:.2f} square metres.\n"
            f"Answer: {result['name']}, {result['area_m2']:.2f} m²"
        )
    if kind == "room_stacked":
        where = "above" if parsed.inputs["direction"] == "above" else "below"
        return f"The room directly {where} is {result['name']}.\nAnswer: {result['name']}"
    if kind == "floor_area_total":
        return f"Together that is {result['total_m2']:.2f} square metres.\nAnswer: {result['total_m2']:.2f}"
    if kind == "errand":
        return f"The walk is {result['length_m']:.2f} metres in total.\nAnswer: {result['length_m']:.2f}"
    if kind == "straight_line_3d":
        return f"The straight-line distance is {result['distance_m']:.2f} metres.\nAnswer: {result['distance_m']:.2f}"
    return f"That makes {result['count']} rooms.\nAnswer: {int(result['count'])}"


def answer_for_map(bm: BuildingMap, text: str) -> str | None:
    """Reply from the kind function, or None when the parser is unsure or the kind reports an error."""
    parsed = parse_question(bm, text)
    if parsed is None:
        return None
    try:
        result = load_kinds()[parsed.kind].fn(bm, **parsed.inputs)
        return _format_reply(bm, parsed, result)
    except Exception:  # noqa: BLE001  fast path must never raise; MapError and routing errors go to the LLM
        return None


def answer_deterministic(building_directory: Path, text: str) -> str | None:
    try:
        bm = BuildingMap.load(Path(building_directory))
    except (OSError, ValueError, KeyError):
        return None
    return answer_for_map(bm, text)
