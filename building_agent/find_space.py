from starter_agent.building_map import MAX_SEARCH_RESULTS, BuildingMap, MapError


def find_space(bm: BuildingMap, name: str, floor_level: int | None = None) -> dict:
    """Resolve a room id, number or name (optionally on one floor) to a space id.

    Returns {"match": {...}} for exactly one hit, else {"candidates": [...]} for the agent to disambiguate."""
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
    found = exact or [
        bm.spaces[result["id"]]
        for result in bm.search(name, floor_level)
        if result["kind"] == "space"
    ]
    if not found:
        raise MapError(f"No room matches '{name}'" + (f" on level {floor_level}." if floor_level is not None else "."))
    return {"total": len(found), "candidates": [describe(bm, space) for space in found[:MAX_SEARCH_RESULTS]]}


def describe(bm: BuildingMap, space: dict) -> dict:
    return {
        "id": space["id"],
        "name": space["name"],
        "room_type": space["room_type"],
        "floor_id": space["floor_id"],
        "floor": bm.floor_name(space["floor_id"]),
    }
