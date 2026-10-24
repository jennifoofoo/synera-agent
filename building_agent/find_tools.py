"""Ambiguity-aware find tools: groups of similar assets ("the second press") and compass words ("the east lift").

Both functions only report what the map supports. When several answers are plausible they say so
(`needs_choice`) and hand the agent a question to ask the person instead of guessing."""

import re
from collections import defaultdict

from anthropic import beta_tool
from anthropic.lib.tools import ToolError
from shapely.geometry import Polygon

from starter_agent.building_map import OUTSIDE, BuildingMap, MapError
from starter_agent.tools import as_json

MAX_QUERY_CHARS = 200
MAX_GROUPS = 30
MAX_ITEMS_PER_GROUP = 30
MARGIN_M = 3.0
ORDINALS = {
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
    "fifth": 5,
    "5th": 5,
    "sixth": 6,
    "6th": 6,
    "last": -1,
}
ZONE_WORDS = {"line", "bay", "zone"}
STOP_WORDS = {"the", "a", "an", "on", "in", "at", "of", "to", "is", "which", "one"}
DIRECTIONS = {
    "east": ("x", 1, "the right side of the plan (+x)"),
    "west": ("x", -1, "the left side of the plan (-x)"),
    "north": ("y", 1, "the top of the plan (+y)"),
    "south": ("y", -1, "the bottom of the plan (-y)"),
}
DIRECTION_WORDS = {
    "east": {"east", "ost"},
    "west": {"west"},
    "north": {"north", "nord"},
    "south": {"south", "süd", "sued"},
}
CONNECTOR_KINDS = {
    "lift": "lift",
    "lifts": "lift",
    "elevator": "lift",
    "elevators": "lift",
    "stairs": "stairs",
    "stair": "stairs",
    "staircase": "stairs",
    "staircases": "stairs",
}


def words_of(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.lower())


def natural_key(text: str) -> list:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text.lower())]


def vocabulary(bm: BuildingMap) -> set[str]:
    found: set[str] = set()
    for asset in bm.assets.values():
        found.update(words_of(asset["type"]))
        found.update(words_of(asset["name"]))
        found.update(words_of(asset.get("category") or ""))
    return found


def singular(word: str, known: set[str]) -> str:
    if word in known:
        return word
    for suffix in ("es", "s"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2 and word[: -len(suffix)] in known:
            return word[: -len(suffix)]
    return word


def phrase_position(type_words: list[str], run: list[str]) -> str | None:
    """Where a query phrase sits in a type name: "head" (whole or leading words) or "tail" (inside or at the end)."""
    size = len(run)
    for start in range(len(type_words) - size + 1):
        if type_words[start : start + size] == run:
            return "head" if start == 0 else "tail"
    return None


def type_match(type_words: list[str], tokens: list[str]) -> tuple[str, list[str]] | None:
    """Longest contiguous run of query tokens inside the type name; returns its position and the leftover tokens."""
    best = None
    for start in range(len(tokens)):
        for end in range(len(tokens), start, -1):
            position = phrase_position(type_words, tokens[start:end])
            if position and (best is None or end - start > best[0]):
                best = (end - start, position, tokens[:start] + tokens[end:])
    return (best[1], best[2]) if best else None


def zone_spaces(bm: BuildingMap, floor_level: int | None) -> list[dict]:
    zones = [space for space in bm.spaces.values() if space["room_type"] == "production_zone"]
    if not zones:
        zones = [space for space in bm.spaces.values() if space["room_type"].endswith("_zone")]
    zones = [space for space in zones if floor_level is None or bm.floors[space["floor_id"]]["level"] == floor_level]
    return sorted(zones, key=lambda space: natural_key(space.get("ref") or space["name"]))


def parse_query(query: str) -> tuple[list[str], int | None, int | None]:
    """Split a query into search tokens, an ordinal (1-based, -1 = last) and a line/bay/zone number."""
    tokens = words_of(query[:MAX_QUERY_CHARS])[:20]
    if not tokens:
        raise MapError("Empty query. Say what to find, e.g. 'press brake' or 'second lift'.")
    ordinal = zone_number = None
    rest: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        following = tokens[index + 1] if index + 1 < len(tokens) else ""
        if token in ZONE_WORDS and following.isdigit():
            zone_number = int(following)
            index += 2
            continue
        if token in STOP_WORDS and len(tokens) > 1:
            pass
        elif token in ORDINALS and ordinal is None:
            ordinal = ORDINALS[token]
        else:
            rest.append(token)
        index += 1
    return rest, ordinal, zone_number


def matching_assets(bm: BuildingMap, tokens: list[str], floor_level: int | None) -> list[dict]:
    known = vocabulary(bm)
    tokens = [singular(token, known) for token in tokens]
    hits: list[tuple[str, dict]] = []
    for asset in bm.assets.values():
        if floor_level is not None and bm.floors[asset["floor_id"]]["level"] != floor_level:
            continue
        name_words = set(words_of(asset["name"])) | set(words_of(asset["id"]))
        type_words = words_of(asset["type"])
        matched = type_match(type_words, tokens)
        if matched:
            position, leftover = matched
            if all(word in name_words for word in leftover):
                hits.append((position, asset))
            continue
        loose = name_words | set(type_words) | set(words_of(asset.get("category") or ""))
        if all(token in loose for token in tokens):
            hits.append(("head", asset))
    if any(position == "head" for position, _ in hits):
        hits = [(position, asset) for position, asset in hits if position == "head"]
    return [asset for _, asset in hits]


def find_asset(bm: BuildingMap, query: str, floor_level: int | None = None) -> dict:
    """Find assets by type words or name and group them by room and type with a stable first/second/third order."""
    tokens, ordinal, zone_number = parse_query(query)
    hints: list[str] = []
    hinted_zone = None
    if zone_number is not None:
        zones = zone_spaces(bm, floor_level)
        if 1 <= zone_number <= len(zones):
            hinted_zone = zones[zone_number - 1]
            hints.append(
                f"Number {zone_number} could mean the {zone_number}th production zone by name order: "
                f"{hinted_zone['name']} (of {len(zones)} zones). This is only a guess, confirm it with the person."
            )
        else:
            hints.append(f"There is no zone number {zone_number} here ({len(zones)} zones). Ask which one is meant.")
    hits = matching_assets(bm, tokens, floor_level) if tokens else []
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for asset in hits:
        grouped[(asset["space_id"], asset["type"])].append(asset)
    groups = []
    for (space_id, asset_type), assets in grouped.items():
        space = bm.spaces[space_id]
        ordered = sorted(assets, key=lambda asset: (natural_key(asset["name"]), asset["id"]))
        groups.append(
            {
                "zone": space["name"],
                "space_id": space_id,
                "floor": bm.floor_name(space["floor_id"]),
                "type": asset_type,
                "items": [
                    {"ordinal": number, "id": asset["id"], "name": asset["name"]}
                    for number, asset in enumerate(ordered, start=1)
                ],
            }
        )
    groups.sort(key=lambda group: (natural_key(group["type"]), natural_key(group["zone"])))
    total = len(hits)
    needs_choice = len(groups) > 1
    question = ""
    located = [asset["id"] for asset in hits]
    if ordinal is not None and len(groups) == 1:
        items = groups[0]["items"]
        index = len(items) - 1 if ordinal == -1 else ordinal - 1
        if 0 <= index < len(items):
            groups[0]["items"] = [items[index]]
            located = [items[index]["id"]]
        else:
            needs_choice = True
            hints.append(f"Only {len(items)} matching item(s) in {groups[0]['zone']}, so that ordinal does not exist.")
            question = f"There are only {len(items)} here. Which one do you mean?"
    elif ordinal is not None and groups:
        hints.append(
            "An ordinal counts inside one room. Several rooms or types match, so ask which one is meant first."
        )
    if zone_number is not None and not (
        len(groups) == 1 and hinted_zone and groups[0]["space_id"] == hinted_zone["id"]
    ):
        needs_choice = True
    if needs_choice and not question:
        if groups:
            listed = "; ".join(f"{group['type'].replace('_', ' ')} in {group['zone']}" for group in groups[:8])
            question = f"Several places match: {listed}. Which one do you mean?"
        else:
            question = "Which zone do you mean?"
    if hits:
        bm.located_asset_ids = located
    note = (
        ""
        if hits
        else f"No asset matches '{query[:60]}'" + (f" on level {floor_level}." if floor_level is not None else ".")
    )
    return {
        "matches": total,
        "groups": [{**group, "items": group["items"][:MAX_ITEMS_PER_GROUP]} for group in groups[:MAX_GROUPS]],
        "needs_choice": needs_choice,
        "question": question,
        "hints": hints,
        **({"note": note} if note else {}),
        **({"truncated": True} if len(groups) > MAX_GROUPS else {}),
    }


def connector_candidates(bm: BuildingMap, kind: str, floor_level: int | None) -> list[dict]:
    levels = {floor_id: floor["level"] for floor_id, floor in bm.floors.items()}
    found = []
    if kind == "entrance":
        for opening in bm.openings.values():
            if OUTSIDE not in opening["space_ids"] or opening["kind"] != "entrance":
                continue
            if floor_level is not None and levels[opening["floor_id"]] != floor_level:
                continue
            inner = bm.other_side(opening, OUTSIDE)
            x, y = opening["position"]
            found.append(
                candidate(
                    opening["id"], bm.spaces[inner]["name"], kind, [bm.floor_name(opening["floor_id"])], x, y, inner
                )
            )
        return found
    for connector in bm.connectors.values():
        if connector["kind"] != kind:
            continue
        if floor_level is not None and not any(levels[floor_id] == floor_level for floor_id in connector["floor_ids"]):
            continue
        stops = list(zip(connector["floor_ids"], connector["space_ids"], strict=True))
        _, space_id = min(stops, key=lambda stop: levels[stop[0]])
        centre = Polygon(bm.spaces[space_id]["polygon"]).centroid
        floors = [bm.floor_name(floor_id) for floor_id in sorted(connector["floor_ids"], key=levels.get)]
        found.append(candidate(connector["id"], connector["name"], kind, floors, centre.x, centre.y, space_id))
    return found


def candidate(item_id: str, name: str, kind: str, floors: list[str], x: float, y: float, space_id: str) -> dict:
    return {
        "id": item_id,
        "name": name,
        "kind": kind,
        "floors": floors,
        "position": [round(x, 2), round(y, 2)],
        "space_id": space_id,
    }


def find_connector(bm: BuildingMap, kind: str, direction: str | None = None, floor_level: int | None = None) -> dict:
    """Pick a lift, staircase or entrance by compass word: +x is east, +y is north in the building's local frame."""
    wanted = CONNECTOR_KINDS.get(kind.strip().lower(), kind.strip().lower())
    if wanted not in {"lift", "stairs", "entrance"}:
        raise MapError(f"Unknown kind '{kind}'. Use 'lift', 'stairs' or 'entrance'.")
    axis = sign = None
    assumption = None
    compass = None
    if direction is not None and direction.strip():
        compass = direction.strip().lower()
        if compass not in DIRECTIONS:
            raise MapError(
                f"Direction '{direction}' is not supported. Use north, south, east or west "
                "(translate Ost, West, Nord, Süd yourself). Left and right need a viewpoint I do not have: ask the person."
            )
        axis, sign, side = DIRECTIONS[compass]
        assumption = f"I take {compass} as {side}."
    candidates = connector_candidates(bm, wanted, floor_level)
    result: dict = {"kind": wanted, "direction": compass, "assumption": assumption, "needs_choice": False}
    if not candidates:
        return {
            **result,
            "candidates": [],
            "message": f"No {wanted} found in this building"
            + (f" on level {floor_level}." if floor_level is not None else "."),
        }
    if len(candidates) == 1:
        return {
            **result,
            "candidates": candidates,
            "chosen": candidates[0],
            "reason": f"This is the only {wanted} in the building, so no direction is needed.",
        }
    if compass is None:
        listed = ", ".join(f"{item['name']} ({item['id']})" for item in candidates)
        return {
            **result,
            "candidates": candidates,
            "needs_choice": True,
            "question": f"Which {wanted} do you mean? {listed}.",
        }
    words = DIRECTION_WORDS[compass]
    spaces = bm.spaces
    named = [
        item
        for item in candidates
        if words & (set(words_of(item["name"])) | set(words_of(spaces[item["space_id"]]["name"])))
    ]
    if len(named) == 1:
        return {
            **result,
            "candidates": candidates,
            "chosen": named[0],
            "reason": f"Its name contains the word for {compass}.",
        }
    pool = named or candidates
    index = 0 if axis == "x" else 1
    ranked = sorted(pool, key=lambda item: -sign * item["position"][index])
    margin = round(sign * (ranked[0]["position"][index] - ranked[1]["position"][index]), 2)
    for item in ranked:
        item["along_axis_m"] = round(sign * item["position"][index], 2)
    if margin < MARGIN_M:
        close = [item for item in ranked if sign * (ranked[0]["position"][index] - item["position"][index]) < MARGIN_M]
        names = " or ".join(f"{item['name']} ({item['id']})" for item in close)
        return {
            **result,
            "candidates": ranked,
            "needs_choice": True,
            "margin_m": margin,
            "question": f"The {wanted}s are too close to tell which is furthest {compass} (under {MARGIN_M:g} m apart). Do you mean {names}?",
        }
    reason = "Furthest along the axis" + (f" among those named {compass}" if named else "")
    return {
        **result,
        "candidates": ranked,
        "chosen": ranked[0],
        "margin_m": margin,
        "reason": f"{reason}, {margin} m ahead of the next one.",
    }


def make_find_tools(bm: BuildingMap, annotate=None) -> list:
    @beta_tool
    def find_asset_tool(query: str, floor_level: int | None = None) -> str:
        """Find equipment or furniture by type or name when the person's words may fit several items,
        e.g. "the second press", "the printer in H-A3", "press on line 4". Groups hits by room and type
        with a stable order (the -A/-B/-C suffix is first/second/third). If needs_choice is true, do NOT
        pick one: ask the person the returned question (but if the message contains 'Answer:' nobody can reply:
        take the most plausible candidate and say which). Hints (like "line 4") are guesses to confirm.

        Args:
            query: Type words, name words, optionally an ordinal (first, second, last) or "line/bay/zone N".
            floor_level: Floor of the item (0 = ground floor, -1 = basement). Omit if unknown.
        """
        try:
            result = find_asset(bm, query, floor_level)
            if annotate:
                annotate(result["groups"])  # route length from the person's position, when one is set
            return as_json(result)
        except MapError as error:
            raise ToolError(str(error)) from error

    find_asset_tool.name = "find_asset"

    @beta_tool
    def find_connector_tool(kind: str, direction: str | None = None, floor_level: int | None = None) -> str:
        """Pick a lift, stairs or entrance by compass word ("the east lift", "north stairs"). Use it when there
        are several. Always tell the person the returned assumption (which side of the plan the direction
        means). If needs_choice is true, ask the returned question instead of guessing (if the message contains 'Answer:', take the closest
        candidate and say so). Left and right are
        not supported: ask which one is meant.

        Args:
            kind: "lift", "stairs" or "entrance".
            direction: One of north, south, east, west (translate Ost, Nord, Süd yourself). Omit to list all.
            floor_level: Only connectors serving this floor (0 = ground floor). Omit if unknown.
        """
        try:
            return as_json(find_connector(bm, kind, direction, floor_level))
        except MapError as error:
            raise ToolError(str(error)) from error

    find_connector_tool.name = "find_connector"
    return [find_asset_tool, find_connector_tool]
