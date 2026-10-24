import re

from starter_agent.building_map import MAX_SEARCH_RESULTS, BuildingMap, MapError


def find_space(bm: BuildingMap, name: str, floor_level: int | None = None) -> dict:
    """Resolve a room id, number or name (optionally on one floor) to a space id.

    Returns {"match": {...}} for exactly one hit, else {"candidates": [...]} for the agent to disambiguate."""
    bracketed = re.search(r"\[([^\[\]]+)\]\s*$", name)
    if bracketed and bracketed.group(1) in bm.spaces:
        name = bracketed.group(1)
    lowered = name.strip().lower()
    spaces = [
        space
        for space in bm.spaces.values()
        if floor_level is None or bm.floors[space["floor_id"]]["level"] == floor_level
    ]
    exact = [
        space
        for space in spaces
        if lowered in (space["id"].lower(), (space.get("ref") or "").lower(), space["name"].lower())
    ]
    if len(exact) == 1:
        return {"match": describe(bm, exact[0])}
    if not exact:
        near = _by_printed_number(spaces, name)
        if len(near) == 1 and _fits(near[0], name):
            return {"match": describe(bm, near[0])}
        if len(near) == 1:  # the number is right but the words or the qualifier disagree: the person chooses
            return {"total": 1, "candidates": [describe(bm, near[0])]}
    found = exact or [bm.spaces[result["id"]] for result in bm.search(name, floor_level) if result["kind"] == "space"]
    if not found:
        raise MapError(f"No room matches '{name}'" + (f" on level {floor_level}." if floor_level is not None else "."))
    return {"total": len(found), "candidates": [describe(bm, space) for space in found[:MAX_SEARCH_RESULTS]]}


_STOP_WORDS = {"the", "a", "an", "in", "im", "raum", "room", "zimmer"}
_FLOOR_QUALIFIER = re.compile(r"^(ground floor|floor\b.*|basement.*|level.*|etage.*|og\b.*|eg\b.*)$")


def _qualifiers(text: str) -> set[str]:
    """Bracketed parts such as 'apartment 8' (floor qualifiers like '(Floor 3)' are about the floor, not the room)."""
    found = {part.strip().lower() for part in re.findall(r"\(([^)]*)\)", text)}
    return {part for part in found if part and not _FLOOR_QUALIFIER.match(part)}


def _by_printed_number(spaces: list[dict], text: str) -> list[dict]:
    """Rooms whose number (ref) is THE number-like word of `text`, for a name that does not match exactly
    ('Kitchen 1.30 (apartment 8)' when the room is called 'Room 1.30', as in a building read from a plan). Bracketed
    parts and bare whole numbers do not count, text with two different numbers ('1.30 or 9.99') finds nothing, and
    neither does a tag or assignment ('[position: X]'). The caller still has to check `_fits`."""
    if re.search(r"[\[\]:=]", text):
        return []
    main = re.sub(r"\([^)]*\)", " ", text.lower())
    words = {word for word in re.findall(r"[^\s()\[\],;]+", main) if any(ch.isdigit() for ch in word)}
    numbers = {word for word in words if not word.isdigit()}
    if len(numbers) != 1:
        return []
    return [space for space in spaces if (space.get("ref") or "").lower() in numbers]


def _fits(space: dict, text: str) -> bool:
    """The room may be auto-matched from its number: no contradicting qualifier ('apartment 999' against
    '(apartment 1)'), and either its type is unknown (a generic room, as in a building read from a plan, where only
    numbers are known) or the type and name words of the text appear in its name or type."""
    asked, own = _qualifiers(text), _qualifiers(space["name"])
    if asked and own and not asked <= own:
        return False
    if space.get("room_type") == "generic_room":
        return True
    main = re.sub(r"\([^)]*\)", " ", text.lower())
    wanted = [w for w in re.findall(r"[^\W\d_]+", main) if w not in _STOP_WORDS]
    have = re.findall(r"[^\W\d_]+", re.sub(r"\([^)]*\)", " ", space["name"].lower()))
    have += space["room_type"].replace("_", " ").lower().split()
    return all(any(w == h or (len(w) >= 4 and (h.startswith(w) or w.startswith(h))) for h in have) for w in wanted)


def describe(bm: BuildingMap, space: dict) -> dict:
    return {
        "id": space["id"],
        "name": space["name"],
        "room_type": space["room_type"],
        "floor_id": space["floor_id"],
        "floor": bm.floor_name(space["floor_id"]),
    }
