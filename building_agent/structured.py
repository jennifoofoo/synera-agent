"""Structured answers from what the agent actually computed, not from its prose.

The kit's warm-up scorer reads the map state after a conversation (last route, located assets) and only the
number from the reply for counts. The Sunday PDF asks for the same facts as data: the located item or room id,
the route as an ordered list of node ids and the length in metres. One function serves both formats."""

from benchmark.score import committed_answer, numbers_in
from starter_agent.building_map import BuildingMap


def route_entry(bm: BuildingMap) -> dict | None:
    """The most recent route as data: ordered space ids (the nodes), length, constraints."""
    route = bm.last_route
    if route is None:
        return None
    return {
        "from_space_id": route.start_space_id,
        "to_space_id": route.destination_space_id,
        "space_path": list(route.space_path),
        "length_m": route.length_m,
        "step_free": route.step_free,
        "closed": list(route.closed),
    }


def located_entries(bm: BuildingMap, reply: str = "") -> list[dict]:
    """Assets the agent found in its last search, narrowed to those the reply names (id or asset name)."""
    lowered = reply.lower()
    found = [bm.assets[asset_id] for asset_id in bm.located_asset_ids if asset_id in bm.assets]
    named = [asset for asset in found if asset["id"].lower() in lowered or asset["name"].lower() in lowered]
    entries = []
    for asset in named or found:
        asset_id = asset["id"]
        space = bm.spaces[asset["space_id"]]
        entries.append(
            {
                "asset_id": asset_id,
                "space_id": asset["space_id"],
                "space_name": space["name"],
                "floor_level": bm.floors[asset["floor_id"]]["level"],
            }
        )
    return entries


def reply_number(reply: str) -> float | None:
    """The committed number, read exactly like the official scorer: the 'Answer:' line, else the whole reply."""
    committed = committed_answer(reply)
    if committed is not None:
        found = numbers_in(committed)
        return found[-1] if found else None
    found = numbers_in(reply)
    whole = [value for value in found if value.is_integer()]
    return (whole or found)[0] if found else None  # no committed line: a count is a whole number, mostly first


def structured_entry(question_id: str, kind: str, bm: BuildingMap, reply: str) -> dict:
    """One answers.json entry for one question, shaped by the question kind."""
    entry: dict = {"id": question_id, "kind": kind, "reply": reply}
    committed = committed_answer(reply)
    if committed is not None and len(numbers_in(committed)) > 1:
        entry["warnings"] = ["the Answer line holds several numbers, the scorer counts that as wrong"]
    if kind == "locate":
        entry["located"] = located_entries(bm, reply)
    elif kind == "count":
        entry["count"] = reply_number(reply)
    elif kind in {"route", "route_step_free", "route_with_closure", "tour"}:
        entry["route"] = route_entry(bm)
    return entry
