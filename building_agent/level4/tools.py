"""Level 4 step 2: conversation tools that build a building from floor plan images.

Flow: build_from_plan (draft, never the active map) -> fix_draft -> preview_draft (the understanding card)
-> save_building after a clear yes in the NEXT message. The confirmation rules are the ones of confirm_change."""

import copy
import json
import os
import re
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from anthropic import beta_tool
from anthropic.lib.tools import ToolError
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

from building_agent.guide_tools import NO, YES, GuideState
from building_agent.level4.convert import (
    CONNECTOR_KIND,
    MANUAL_ID_MARK,
    ConvertError,
    FloorInput,
    convert_floors_with_findings,
    exterior_wall,
    pixel_to_metres,
    point_on_wall,
    relink_connectors,
    scale_from_bar,
    scale_from_known_length,
    tag_fills,
)
from building_agent.level4.extract import DEFAULT_ALLOWED_ROOT, ExtractError, ExtractResult, extract_floor
from building_agent.level4.markers import detect_markers, merge_markers
from building_agent.level4.schema import OUTSIDE, Extraction, Findings, Scale
from building_agent.level4.segment import match_to_extraction, segment_rooms
from building_agent.level4.suggest import apply_suggestions, describe_suggestions, suggest_doors
from building_agent.level4.validate import Collector, describe, validate
from starter_agent.building_map import NEW_DOOR_WIDTH_M, BuildingMap, MapError
from starter_agent.tools import as_json

BUILDINGS_ROOT = Path("agent_output") / "buildings"
ALONG = ("building_width", "room", "door")
FIX_ACTIONS = (
    "add_door",
    "remove_door",
    "add_entrance",
    "set_room_type",
    "set_scale",
    "accept_suggestions",
    "link_floors",
)
STAIR_TYPES = {"stairwell", "stair", "stairs", "staircase"}
LIFT_TYPES = {"lift", "elevator"}
LINK_KINDS = {"stairs": "stair", "stair": "stair", "lift": "lift", "elevator": "lift"}
CONNECTOR_CODES = {"connector_single_floor", "connector_linked_by_order", "connector_aligned_by_centre"}
MAX_STAIR_HALL_M2 = 60.0
SIDES = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}
MAX_CANDIDATES = 5
ENTRANCE_ROOM_TYPES = {"lobby", "hall"}
ACCEPT = re.compile(r"\b(trotzdem|anyway|nevertheless|dennoch|accept|akzeptiere|mit den problemen)\b", re.IGNORECASE)
ROOM_TYPE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
ASK_SCALE = (
    "The plan has no printed scale bar and no known length was given. Ask the person for ONE length they know in "
    "metres (the width of the whole building, the width of one room, or a door width), then call build_from_plan "
    "again with known_length_m (and along). The image is already read, so this costs nothing extra."
)


@dataclass
class BMHolder:
    """The active BuildingMap of the session; save_building replaces `bm`."""

    bm: BuildingMap


@dataclass
class FloorSource:
    extraction: Extraction
    scale: Scale
    scale_args: dict


@dataclass
class Level4Draft:
    floors: dict[int, FloorSource] = field(default_factory=dict)
    fixes: list[tuple] = field(default_factory=list)
    building: dict | None = None
    findings: Findings = field(default_factory=Findings)
    convert_items: list = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    marker_notes: list[str] = field(default_factory=list)
    building_id: str = field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:8]}")
    name: str = "Uploaded building"
    version: int = 0
    card_turn: int | None = None
    card_version: int = -1
    card_blocked: bool = False
    cache: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    last_level: int = 0


# ---------- pure helpers ----------


def _label(space: dict) -> str:
    return space.get("ref") or space.get("name") or space["id"]


def resolve_ref(building: dict, reference: str, level: int | None = None) -> dict:
    """One space by ref, name or id (case-insensitive). Raises ToolError with candidates when unclear."""
    wanted = str(reference).strip().lower()
    floor_level = {floor["id"]: floor["level"] for floor in building["floors"]}
    found = [
        space
        for space in building["spaces"]
        if (level is None or floor_level[space["floor_id"]] == level)
        and wanted in {str(space["id"]).lower(), str(space.get("ref") or "").lower(), str(space["name"]).lower()}
    ]
    if not found:
        raise ToolError(f"No room '{reference}' in the draft. Use a room number as shown in the card.")
    if len(found) > 1:
        floors = ", ".join(sorted({str(floor_level[space["floor_id"]]) for space in found}))
        raise ToolError(f"'{reference}' is ambiguous (floors {floors}). Say which floor with level.")
    return found[0]


def _unique_opening_id(building: dict, opening: dict) -> None:
    """Give `opening` an id that no other opening of the building uses."""
    taken = {other["id"] for other in building["openings"] if other is not opening}
    base, number = opening["id"], 1
    while opening["id"] in taken:
        number += 1
        opening["id"] = f"{base}-{number}"


def _straight_pieces(lines: list[LineString]) -> list[LineString]:
    return [LineString(pair) for line in lines for pair in zip(line.coords[:-1], line.coords[1:], strict=True)]


def _floor_polygons(building: dict, floor_id: str) -> dict[str, Polygon]:
    return {s["id"]: Polygon(s["polygon"]) for s in building["spaces"] if s["floor_id"] == floor_id}


def _exterior_stretches(building: dict, space: dict) -> list[LineString]:
    polygons = _floor_polygons(building, space["floor_id"])
    others = [shape for space_id, shape in polygons.items() if space_id != space["id"]]
    return exterior_wall(polygons[space["id"]], others)


def _add_entrance(building: dict, fix: tuple, to_metres) -> str:
    _, reference, level, side, point_px, step_free = fix
    space = resolve_ref(building, reference, level)
    if any(OUTSIDE in o["space_ids"] and space["id"] in o["space_ids"] for o in building["openings"]):
        raise ToolError(f"{_label(space)} already has an entrance.")
    stretches = _exterior_stretches(building, space)
    if not stretches:
        raise ToolError(
            f"{_label(space)} has no outside wall (other rooms touch it on every side), so it cannot have an "
            "entrance. Ask which room is next to the outside."
        )
    pieces = _straight_pieces(stretches)
    width = NEW_DOOR_WIDTH_M
    if point_px is not None:
        floor_level = next(f["level"] for f in building["floors"] if f["id"] == space["floor_id"])
        if to_metres is None:
            raise ToolError("A point on the image cannot be used here.")
        spot = point_on_wall(pieces, Point(*to_metres(floor_level, *point_px)), width)
    elif side is not None:
        centre = Polygon(space["polygon"]).centroid
        direction = SIDES[side]
        scored = [
            (((m.x - centre.x) * direction[0] + (m.y - centre.y) * direction[1]), piece)
            for piece in pieces
            for m in [piece.interpolate(0.5, normalized=True)]
        ]
        best = max(scored, key=lambda item: item[0])
        if best[0] <= 0:
            raise ToolError(f"{_label(space)} has no outside wall on the {side} side.")
        spot = best[1].interpolate(0.5, normalized=True)
    else:
        spot = max(pieces, key=lambda piece: piece.length).interpolate(0.5, normalized=True)
    numbers = len(building["openings"]) + 1
    opening = {
        "id": f"{space['floor_id']}-O-new{numbers}",
        "floor_id": space["floor_id"],
        "space_ids": [space["id"], OUTSIDE],
        "kind": "entrance",
        "position": [round(spot.x, 3), round(spot.y, 3)],
        "width_m": width,
        "step_free": step_free,
        "synthetic": False,
    }
    building["openings"].append(opening)
    _unique_opening_id(building, opening)
    return f"Entrance added to {_label(space)}" + ("" if step_free else " (with steps)") + "."


def apply_fix(building: dict, fix: tuple, to_metres=None) -> str:
    """Apply one deterministic fix to `building` in place and return what was done. Raises ToolError."""
    action = fix[0]
    if action == "accept_suggestions":
        suggestions = suggest_doors(building)
        if not suggestions:
            raise ToolError("There are no door suggestions for this draft.")
        updated = apply_suggestions(building, suggestions)
        building.clear()
        building.update(updated)
        return f"{len(suggestions)} suggested door(s) added."
    if action == "add_entrance":
        return _add_entrance(building, fix, to_metres)
    if action == "set_room_type":
        _, reference, room_type, level = fix
        space = resolve_ref(building, reference, level)
        space["room_type"] = room_type
        if room_type in STAIR_TYPES | LIFT_TYPES:
            kind = "stair" if room_type in STAIR_TYPES else "lift"
            space["type"], space["room_type"] = kind, "stairwell" if kind == "stair" else "lift"
        elif space.get("type") in CONNECTOR_KIND:
            space["type"] = "room"
        before = len(building["vertical_connectors"])
        relink_connectors(building, Collector())
        done = f"{_label(space)} is now a {space['room_type'].replace('_', ' ')}."
        if space["type"] in CONNECTOR_KIND or before != len(building["vertical_connectors"]):
            done += f" Stairs and lifts linked between the floors: {len(building['vertical_connectors'])}."
        return done
    if action == "link_floors":
        return _link_floors(building, fix)
    first, second = resolve_ref(building, fix[1], fix[3]), resolve_ref(building, fix[2], fix[3])
    pair = {first["id"], second["id"]}
    if first["id"] == second["id"]:
        raise ToolError("A door needs two different rooms.")
    if action == "add_door":
        if any(set(opening["space_ids"]) == pair for opening in building["openings"]):
            raise ToolError("These two rooms already have a door between them.")
        try:
            opening = BuildingMap(building).add_door(first["id"], second["id"])
        except MapError as error:
            raise ToolError(str(error)) from error
        opening["synthetic"] = False
        _unique_opening_id(building, opening)
        return f"Door added between {_label(first)} and {_label(second)}."
    before = len(building["openings"])
    building["openings"] = [o for o in building["openings"] if set(o["space_ids"]) != pair]
    if len(building["openings"]) == before:
        raise ToolError(f"There is no door between {_label(first)} and {_label(second)}.")
    return f"Door removed between {_label(first)} and {_label(second)}."


def _link_floors(building: dict, fix: tuple) -> str:
    _, reference, other_reference, kind_word, level, other_level = fix
    kind = LINK_KINDS.get(str(kind_word).strip().lower())
    if kind is None:
        raise ToolError("kind must be 'stairs' or 'lift'.")
    first, second = resolve_ref(building, reference, level), resolve_ref(building, other_reference, other_level)
    levels = {floor["id"]: floor["level"] for floor in building["floors"]}
    if first["floor_id"] == second["floor_id"]:
        raise ToolError("The two rooms are on the same floor. A stair or lift joins two different floors.")
    ordered = sorted(levels.values())
    low, high = sorted((levels[first["floor_id"]], levels[second["floor_id"]]))
    if ordered.index(high) - ordered.index(low) != 1:
        raise ToolError(f"Floors {low} and {high} are not neighbours. Link each pair of neighbouring floors.")
    first, second = (first, second) if levels[first["floor_id"]] < levels[second["floor_id"]] else (second, first)
    word = CONNECTOR_KIND[kind]
    pair = {first["id"], second["id"]}
    if any(c["kind"] == word and pair <= set(c["space_ids"]) for c in building["vertical_connectors"]):
        raise ToolError(f"{_label(first)} and {_label(second)} are already linked as {word}.")
    for space in (first, second):
        if space.get("type") not in CONNECTOR_KIND:  # a stair hall that also holds a lift keeps its type
            space["type"], space["room_type"] = kind, "stairwell" if kind == "stair" else "lift"
    building_id = building["building"]["id"]
    number = 1 + sum(MANUAL_ID_MARK in str(c["id"]) for c in building["vertical_connectors"])
    building["vertical_connectors"].append(
        {
            "id": f"{building_id}{MANUAL_ID_MARK}{number:02d}",
            "kind": word,
            "name": first["name"],
            "floor_ids": [first["floor_id"], second["floor_id"]],
            "space_ids": [first["id"], second["id"]],
            "step_free": kind == "lift",
            "synthetic": False,
        }
    )
    relink_connectors(building, Collector())
    return f"{_label(first)} (floor {low}) and {_label(second)} (floor {high}) are now linked by a {word.replace('stairs', 'stair')}."


def _relinked(building: dict, items: list) -> list:
    """The conversion findings with the stair and lift findings replaced by the ones of a fresh linking."""
    found = Collector()
    relink_connectors(building, found)
    return [item for item in items if item.code not in CONNECTOR_CODES] + found.findings()


def connector_candidates(building: dict) -> dict[int, list[str]]:
    """Per floor up to 5 rooms that may be stairs or lifts: unlinked ones typed so, then small halls and corridors."""
    levels = {floor["id"]: floor["level"] for floor in building["floors"]}
    linked = {sid for c in building["vertical_connectors"] for sid in c["space_ids"]}
    ranked: dict[int, list[tuple]] = {level: [] for level in levels.values()}
    for space in building["spaces"]:
        try:
            size = Polygon(space["polygon"]).area
        except (TypeError, ValueError):
            continue
        if space.get("type") in CONNECTOR_KIND and space["id"] not in linked:
            ranked[levels[space["floor_id"]]].append((0, -size, _label(space)))
        elif space.get("type") in ("hall", "corridor") and size <= MAX_STAIR_HALL_M2:
            ranked[levels[space["floor_id"]]].append((1 if space["type"] == "hall" else 2, -size, _label(space)))
    return {level: [label for _, _, label in sorted(items)[:MAX_CANDIDATES]] for level, items in ranked.items()}


def connector_question(building: dict) -> str | None:
    """A plain question when the draft has several floors but no stairs or lifts (or no lift), else None."""
    if len(building["floors"]) < 2:
        return None
    connectors = building["vertical_connectors"]
    if connectors:
        if any(c["kind"] == "lift" for c in connectors):
            return None
        return (
            "lift_not_found: no lift was found between the floors, so there is no step-free way up. Ask whether the "
            "building has a lift and which rooms it is, then call fix_draft with action link_floors and kind lift."
        )
    text = (
        f"The plan has {len(building['floors'])} floors but no stairs or lifts between them were found. Ask the "
        "person which rooms are the stairs and lifts, then call fix_draft with set_room_type (stairwell or lift) for "
        "each room, or action link_floors (ref, other_ref, kind stairs or lift, level, other_level) when the numbers "
        "differ per floor."
    )
    candidates = {level: labels for level, labels in connector_candidates(building).items() if labels}
    if candidates:
        text += (
            " Possible rooms: "
            + "; ".join(f"floor {level}: {', '.join(l)}" for level, l in sorted(candidates.items()))
            + "."
        )
    return text


def questions(building: dict) -> str | None:
    found = [text for text in (entrance_question(building), connector_question(building)) if text]
    return " ".join(found) or None


def entrance_candidates(building: dict) -> list[str]:
    """Up to 5 room refs on the lowest floor for 'which room has the entrance': lobbies and halls first, then
    rooms with the longest outside wall."""
    lowest = min(building["floors"], key=lambda floor: floor["level"])
    spaces = [space for space in building["spaces"] if space["floor_id"] == lowest["id"]]
    polygons = _floor_polygons(building, lowest["id"])
    ids = list(polygons)
    tree = STRtree([polygons[i] for i in ids])
    ranked = []
    for space in spaces:
        shape = polygons[space["id"]]
        nearby = [polygons[ids[j]] for j in tree.query(shape.buffer(0.3)) if ids[j] != space["id"]]
        outside = sum(line.length for line in exterior_wall(shape, nearby))
        first = space.get("room_type") in ENTRANCE_ROOM_TYPES or space.get("type") in ENTRANCE_ROOM_TYPES
        if outside > 0:
            ranked.append((not first, -outside, _label(space)))
    return [label for _, _, label in sorted(ranked)[:MAX_CANDIDATES]]


def entrance_question(building: dict) -> str | None:
    """A plain question when no room of the draft has an entrance, else None."""
    if any(OUTSIDE in opening["space_ids"] for opening in building["openings"]):
        return None
    candidates = entrance_candidates(building)
    text = "The plan shows no entrance. Ask the person which room the entrance is in, then call fix_draft with action add_entrance."
    if candidates:
        text += " Likely rooms: " + ", ".join(candidates) + "."
    return text


def counts(building: dict, level: int | None = None) -> dict:
    floor_ids = {floor["id"] for floor in building["floors"] if level is None or floor["level"] == level}
    spaces = [s for s in building["spaces"] if s["floor_id"] in floor_ids]
    openings = [o for o in building["openings"] if o["floor_id"] in floor_ids]
    entrances = [o for o in openings if OUTSIDE in o["space_ids"]]
    return {"rooms": len(spaces), "doors": len(openings) - len(entrances), "entrances": len(entrances)}


def write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` so that readers see the old file or the whole new one, never a part."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".building-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _to_metres(draft: "Level4Draft"):
    def convert(level: int, x: float, y: float) -> tuple[float, float]:
        source = draft.floors[level]
        return pixel_to_metres(source.extraction, source.scale.metres_per_px)(x, y)

    return convert


def _trusted_scale(draft: Level4Draft) -> bool:
    """True when every floor got its scale from a length the person gave (not a printed bar or a door width)."""
    return all(
        src.scale.source == "known_length" and src.scale_args.get("along", "building_width") != "door"
        for src in draft.floors.values()
    )


def _rebuild(draft: Level4Draft) -> None:
    """Convert all stored floors, replay the fixes, validate. Raises ToolError when nothing usable results."""
    inputs = [FloorInput(level, src.extraction, src.scale) for level, src in sorted(draft.floors.items())]
    try:
        building, converted = convert_floors_with_findings(inputs, draft.name, draft.building_id)
        notes = []
        for fix in draft.fixes:
            try:
                apply_fix(building, fix, _to_metres(draft))
            except ToolError as error:
                notes.append(f"An earlier fix ({fix[0]}) no longer applies: {error}")
        converted.items = _relinked(building, converted.items)
        checked = validate(building, _trusted_scale(draft))
    except ConvertError as error:
        raise ToolError(str(error)) from error
    except (ValueError, ArithmeticError, TypeError, KeyError, IndexError):
        raise ToolError(
            "This plan could not be converted (odd numbers or shapes). Try another image or scale."
        ) from None
    draft.building = building
    draft.convert_items = converted.items
    draft.findings = Findings(converted.items + checked.items)
    draft.notes = notes
    draft.version += 1
    draft.card_turn = None


# ---------- tools ----------


def make_level4_tools(
    bm_holder: BMHolder,
    output_directory: Path,
    state: GuideState,
    on_saved: Callable[[Path], None] | None = None,
    uploads_root: Path = DEFAULT_ALLOWED_ROOT,
    buildings_root: Path = BUILDINGS_ROOT,
) -> list:
    draft = getattr(state, "level4", None)
    if draft is None:
        draft = state.level4 = Level4Draft()

    def need_draft() -> dict:
        if draft.building is None:
            raise ToolError("There is no draft yet. Call build_from_plan with an image first.")
        return draft.building

    @beta_tool
    def build_from_plan(
        image_path: str, level: int = 0, known_length_m: float | None = None, along: str = "building_width"
    ) -> str:
        """Read ONE floor plan image from the upload folder and build a DRAFT building (not saved, not active).
        Needs the floor (level) and, unless the plan has a printed scale bar, ONE length the person knows.
        If this returns an error asking for the scale, ask the person and call it again with known_length_m.
        Call it once per floor; then show the card with preview_draft.

        Args:
            image_path: Path of the PNG or JPG inside agent_output/uploads (or just the file name).
            level: Floor of this image (0 = ground floor, 1 = first floor, -1 = basement).
            known_length_m: A length in metres the person knows, e.g. the width of the whole building.
            along: What that length is: "building_width", "room" (its shorter side) or "door".
        """
        if along not in ALONG:
            raise ToolError(f"along must be one of {ALONG}.")
        path = Path(image_path)
        if not path.is_absolute() and len(path.parts) == 1:
            path = Path(uploads_root) / path
        try:
            stamp = path.stat()
            key = (str(path), stamp.st_mtime_ns, stamp.st_size)
        except OSError:
            key = (str(path), None, None)
        result: ExtractResult | None = draft.cache.get(key)
        fresh = result is None
        if fresh:
            try:
                result = extract_floor(path, allowed_root=uploads_root)
            except ExtractError as error:
                raise ToolError(str(error)) from error
            draft.cache[key] = result
            draft.cost_usd += result.cost_usd
        extraction = result.extraction
        seg_warnings: list[str] = []
        try:  # room outlines from the flat colour regions of the plan; a failed read keeps the model polygons
            found_segments = segment_rooms(path)
            extraction, seg_warnings = match_to_extraction(extraction, found_segments)
            draft.marker_notes = seg_warnings[:10]
            extraction = tag_fills(extraction, found_segments)
        except Exception as error:  # noqa: BLE001 - optional step, the model result stays valid
            draft.marker_notes = [f"Room outline detection was skipped ({type(error).__name__})."]
        try:  # door, opening and entrance markers found by colour; a failed read keeps the model-only result
            extraction, marker_warnings = merge_markers(extraction, detect_markers(path))
            draft.marker_notes = (seg_warnings + marker_warnings)[:10]
        except Exception as error:  # noqa: BLE001 - optional step, the model result stays valid
            draft.marker_notes = (
                draft.marker_notes + [f"Door marker detection was skipped ({type(error).__name__})."]
            )[:10]
        try:
            if known_length_m is not None:
                scale = scale_from_known_length(extraction, known_length_m, along)
            else:
                scale = scale_from_bar(extraction)
        except ConvertError as error:
            raise ToolError(str(error)) from error
        if scale is None:
            raise ToolError(ASK_SCALE)
        previous = draft.floors.get(level)
        draft.floors[level] = FloorSource(extraction, scale, {"known_length_m": known_length_m, "along": along})
        try:
            _rebuild(draft)
        except ToolError:
            if previous is None:
                del draft.floors[level]
            else:
                draft.floors[level] = previous
            raise
        draft.last_level = level
        summary = {
            "floor": level,
            **counts(draft.building, level),
            "scale": scale.note,
            "scale_source": scale.source,
            "problems": describe(draft.findings),
            "next": "Draft only, nothing saved. Call preview_draft to show the person the card.",
        }
        question = questions(draft.building)
        if question:
            summary["question"] = question
        if fresh:
            summary["seconds"] = round(result.seconds, 1)
            summary["cost_usd"] = round(result.cost_usd, 4)
        if result.warnings:
            summary["warnings"] = result.warnings
        return as_json(summary)

    @beta_tool
    def fix_draft(
        action: str,
        ref: str | None = None,
        other_ref: str | None = None,
        room_type: str | None = None,
        known_length_m: float | None = None,
        along: str = "building_width",
        level: int | None = None,
        side: str | None = None,
        point_px: list[float] | None = None,
        steps: bool = False,
        kind: str | None = None,
        other_level: int | None = None,
    ) -> str:
        """Correct the draft deterministically, then show the card again with preview_draft.
        If the plan shows no entrance, ask which room it is in and call fix_draft add_entrance.

        Args:
            action: "add_door" (ref, other_ref), "remove_door" (ref, other_ref), "add_entrance" (ref, optional
                side or point_px, optional steps), "set_room_type" (ref, room_type) or "set_scale"
                (known_length_m, along, optional level) or "accept_suggestions" (no other arguments: add the
                doors proposed in the last card; only after the person said yes to the proposal) or "link_floors"
                (ref on one floor, other_ref on the neighbouring floor, kind "stairs" or "lift", and level and
                other_level when the room numbers are not unique). set_room_type with stairwell or lift also
                makes the room a stair or lift and links it to the same stair or lift on the next floor.
            side: For add_entrance: "north", "south", "east" or "west" wall of the room (default: its longest
                outside wall).
            point_px: For add_entrance: [x, y] in image pixels, the entrance goes to the outside wall nearest to it.
            steps: For add_entrance: True only if the person says the entrance has steps.
            ref: Room number, name or id of the (first) room.
            other_ref: Second room of the door.
            room_type: New type as snake_case identifier, e.g. "stairwell", "kitchen", "toilet", "office".
            known_length_m: For set_scale, a length in metres the person knows.
            along: For set_scale: "building_width", "room" (ref is that room) or "door".
            level: Floor to disambiguate a room number, or the floor whose scale is set (default: last built).
            kind: For link_floors: "stairs" or "lift".
            other_level: For link_floors: the floor of other_ref.
        """
        building = need_draft()
        if action not in FIX_ACTIONS:
            raise ToolError(f"action must be one of {FIX_ACTIONS}.")
        if action == "set_scale":
            if known_length_m is None:
                raise ToolError("set_scale needs known_length_m.")
            if along not in ALONG:
                raise ToolError(f"along must be one of {ALONG}.")
            target = level if level is not None else draft.last_level
            if target not in draft.floors:
                raise ToolError(f"There is no floor {target} in the draft.")
            source = draft.floors[target]
            try:
                scale = scale_from_known_length(source.extraction, known_length_m, along, ref)
            except ConvertError as error:
                raise ToolError(str(error)) from error
            old = draft.floors[target]
            draft.floors[target] = FloorSource(
                source.extraction, scale, {"known_length_m": known_length_m, "along": along}
            )
            try:
                _rebuild(draft)
            except ToolError:
                draft.floors[target] = old
                raise
            return as_json({"done": f"Scale of floor {target}: {scale.note}.", "problems": describe(draft.findings)})
        if action == "accept_suggestions":
            fix = ("accept_suggestions",)
        elif action == "add_entrance":
            if not ref:
                raise ToolError("add_entrance needs ref (the room with the entrance).")
            if side is not None:
                side = side.strip().lower()
                if side not in SIDES:
                    raise ToolError("side must be north, south, east or west (or give point_px instead).")
            point = None
            if point_px is not None:
                try:
                    point = (float(point_px[0]), float(point_px[1]))
                except (TypeError, ValueError, IndexError):
                    raise ToolError("point_px must be [x, y] in image pixels.") from None
            fix = ("add_entrance", ref, level, side, point, not steps)
        elif action == "link_floors":
            if not ref or not other_ref or not kind:
                raise ToolError("link_floors needs ref, other_ref (rooms on neighbouring floors) and kind.")
            fix = ("link_floors", ref, other_ref, kind, level, other_level)
        elif action == "set_room_type":
            normal = (room_type or "").strip().lower().replace(" ", "_")
            if not ref or not ROOM_TYPE.match(normal):
                raise ToolError("set_room_type needs ref and a room_type like 'kitchen' or 'stairwell'.")
            fix = ("set_room_type", ref, normal, level)
        else:
            if not ref or not other_ref:
                raise ToolError(f"{action} needs ref and other_ref (two room numbers).")
            fix = (action, ref, other_ref, level)
        candidate = copy.deepcopy(building)
        done = apply_fix(candidate, fix, _to_metres(draft))
        draft.fixes.append(fix)
        draft.building = candidate
        draft.convert_items = _relinked(candidate, draft.convert_items)
        draft.findings = Findings(draft.convert_items + validate(candidate, _trusted_scale(draft)).items)
        draft.version += 1
        draft.card_turn = None
        reply = {"done": done, "problems": describe(draft.findings)}
        question = questions(candidate)
        if question:
            reply["question"] = question
        return as_json(reply)

    @beta_tool
    def preview_draft() -> str:
        """The understanding card for the draft, in plain words: what was understood and which problems exist.
        Show it to the person, then wait for their answer in their NEXT message before save_building."""
        building = need_draft()
        errors = Findings(draft.findings.errors)
        floors = {floor["id"]: floor for floor in building["floors"]}
        by_floor: dict[str, list[str]] = {}
        for space in building["spaces"]:
            by_floor.setdefault(space["floor_id"], []).append(_label(space))
        understood = []
        for floor_id, labels in by_floor.items():
            floor = floors[floor_id]
            understood.append(
                {
                    "floor": floor["name"],
                    **counts(building, floor["level"]),
                    "room numbers": labels[:40],
                    "scale": draft.floors[floor["level"]].scale.note,
                }
            )
        card = {
            "I understood": understood,
            "problems found": describe(draft.findings),
            "can be saved": errors.ok,
            "status": "nothing saved yet, waiting for the person's yes",
        }
        if not errors.ok:
            card["saving blocked"] = (
                "There are problems that normally block saving. Fix them, or the person must say clearly they want "
                "to save anyway ('trotzdem speichern' or 'save it anyway')."
            )
            if any(error.code == "no_vertical_connectors" for error in errors.items):
                card["saving blocked"] += " Without stairs or lifts the floors stay separate buildings for routing."
        question = questions(building)
        if question:
            card["question"] = question
        suggestions = suggest_doors(building)
        if suggestions:
            card["proposal"] = describe_suggestions(suggestions)
        if draft.notes or draft.marker_notes:
            card["notes"] = draft.notes + draft.marker_notes
        draft.card_turn, draft.card_version, draft.card_blocked = state.turn, draft.version, not errors.ok
        return as_json(card)

    @beta_tool
    def save_building(confirmed: bool, user_reply: str, accept_problems: bool = False) -> str:
        """Save the draft as a building and make it the active one (call only after preview_draft).
        Only call this after the person answered the card in a NEW message.

        Args:
            confirmed: True only if the person clearly said yes to the card.
            user_reply: The person's answer to the card, copied word for word from their last message.
            accept_problems: True only if the card said saving is blocked and the person explicitly said they
                want to save anyway.
        """
        building = need_draft()
        if draft.card_turn is None:
            raise ToolError("No card was shown. Call preview_draft, show it, and wait for the person's answer.")
        if state.turn == draft.card_turn:
            raise ToolError("Ask the person first: show the card and wait for their answer in a new message.")
        card_turn, card_version, blocked = draft.card_turn, draft.card_version, draft.card_blocked
        draft.card_turn = None
        if state.turn > card_turn + 1:
            raise ToolError("The card is out of date (the person did not answer it right away). Call preview_draft.")
        if card_version != draft.version:
            raise ToolError("The draft changed since the card was shown. Call preview_draft again.")
        errors = draft.findings.errors
        accepting = bool(
            (errors or blocked) and accept_problems and ACCEPT.search(user_reply) and not NO.search(user_reply)
        )
        if confirmed and not accepting and (not YES.search(user_reply) or NO.search(user_reply)):
            raise ToolError("That reply is not a clear yes. Ask the person again, then call preview_draft anew.")
        if not confirmed:
            return as_json({"saved": False, "note": "Not saved. The draft is kept, you can still fix it."})
        if errors or blocked:
            if not accepting:
                raise ToolError(
                    "The draft still has problems that block saving: "
                    + describe(Findings(errors))
                    + " Fix them, or call preview_draft and ask whether to save anyway."
                )
            if any(finding.code == "building_invalid" for finding in errors):
                raise ToolError("The building data is incomplete and cannot be saved at all.")
        path = buildings_root / draft.building_id / "building.json"
        try:
            write_atomic(path, json.dumps(building, indent=1, ensure_ascii=False))
            new_map = BuildingMap.load(path)
        except (OSError, ValueError, KeyError) as error:
            raise ToolError(f"The building could not be saved ({type(error).__name__}). Nothing was changed.") from None
        bm_holder.bm = new_map
        state.session = None
        state.pending = None
        if hasattr(state, "undo"):
            state.undo.clear()  # the old building's snapshots must never be restored into the new one
        if on_saved is not None:
            on_saved(path)
        accepted = describe(Findings(errors)) if errors else None
        result = {
            "saved": True,
            "path": str(path),
            "building_id": draft.building_id,
            **counts(building),
            "accepted_problems": accepted,
            "note": (
                "This building is now the active one. The building has changed. "
                "Ask your question again in your next message."
            ),
        }
        fresh = Level4Draft(cache=draft.cache)  # a second plan starts clean and gets its own building id
        draft.__dict__.update(fresh.__dict__)
        return as_json(result)

    return [build_from_plan, fix_draft, preview_draft, save_building]
