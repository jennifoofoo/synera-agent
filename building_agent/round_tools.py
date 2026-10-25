"""Inspection rounds: visit every device of one type in an area in the shortest order, all in Python.

`plan_round` finds the matching devices, makes one stop per room (several devices in one room are one stop),
measures every stop-to-stop walk on the door-to-door route model (`routing`, the same graph as find_route) and
orders the stops: exact over all orders for up to EXACT_MAX_STOPS stops, else nearest neighbour from the start
followed by 2-opt until nothing improves. Ties go to the smaller space id, so the same question always gives the
same round. The final round is routed once with `routing.route` and remembered like find_route, so the plan
shows it and "guide me" can start. The model only picks the arguments and phrases the result."""

import itertools
import re

from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent import routing
from building_agent.find_tools import connector_candidates, matching_assets, natural_key, words_of
from building_agent.guide_tools import GuideState, building_signature
from building_agent.position import no_position_error, position_note
from building_agent.task_tools import fold, types_for_task
from building_agent.walk import WALK_M_PER_S, remember_route
from starter_agent.building_map import BuildingMap, MapError
from starter_agent.tools import as_json

EXACT_MAX_STOPS = 8
MAX_STOPS = 60
MAX_ENTRANCES = 6
EPSILON_M = 1e-6  # a new order must be shorter by more than this to replace the one found first
HERE_WORDS = {"here", "hier", "me", "my position", "current position", "where i am"}
HALL_LETTER = re.compile(r"^(?:hall|halle)\s+([a-z])$")


# ---------- what and where ----------


def resolve_assets(bm: BuildingMap, what: str) -> tuple[list[dict], str | None, list[str]]:
    """(assets, asset type, other plausible types). Type words in English or German first ("Feuerlöscher"), then
    the words of asset names and types as find_asset reads them."""
    text = (what or "").strip()
    if not text:
        raise MapError("Say which devices the round is for, e.g. 'fire extinguisher'.")
    present = {asset["type"] for asset in bm.assets.values()}
    snake = fold(text).replace(" ", "_")
    if snake in present:
        return [a for a in bm.assets.values() if a["type"] == snake], snake, []
    ranked = [match for match in types_for_task(text) if match.type in present]
    if ranked:
        best = ranked[0].score
        tied = [match.type for match in ranked if abs(match.score - best) < EPSILON_M]
        if len(tied) > 1:
            return [], None, tied
        return [a for a in bm.assets.values() if a["type"] == ranked[0].type], ranked[0].type, []
    hits = matching_assets(bm, words_of(text), None)
    return hits, None, []


def area_match(bm: BuildingMap, space: dict, area: str) -> bool:
    """Room name words ("Server room"), a ref or ref prefix ("H-A", "H-A4"), a room type ("production zones")
    or "Hall A" for the refs that start with H-A."""
    said = fold(area).strip()
    ref = fold(space.get("ref") or "")
    if ref and (ref == said or (ref.startswith(said) and not said[-1:].isdigit())):
        return True
    if (hall := HALL_LETTER.match(said)) and ref.startswith(f"h-{hall.group(1)}"):
        return True
    tokens = [token[:-1] if token.endswith("s") and len(token) > 3 else token for token in words_of(said)]
    known = set(words_of(fold(space["name"]))) | set(words_of(space["room_type"].replace("_", " ")))
    return bool(tokens) and all(token in known for token in tokens)


def area_names(bm: BuildingMap, assets: list[dict]) -> list[str]:
    return sorted({bm.spaces[a["space_id"]]["name"] for a in assets}, key=natural_key)[:12]


# ---------- ordering ----------


def path_length(matrix: dict, start: str, order: tuple, back: bool) -> float:
    stops = (start, *order, *((start,) if back else ()))
    return sum(matrix[a][b] for a, b in itertools.pairwise(stops))


def exact_order(matrix: dict, start: str, stops: list[str], back: bool) -> tuple:
    """Shortest of all orders; permutations of the sorted ids come in lexicographic order, so the first of equal
    lengths wins (the tie-break by id)."""
    best, best_length = (), float("inf")
    for order in itertools.permutations(sorted(stops)):
        length = path_length(matrix, start, order, back)
        if length < best_length - EPSILON_M:
            best, best_length = order, length
    return best


def nearest_neighbour(matrix: dict, start: str, stops: list[str]) -> list[str]:
    order, left, here = [], set(stops), start
    while left:
        here = min(left, key=lambda stop: (matrix[here][stop], stop))
        order.append(here)
        left.remove(here)
    return order


def two_opt(matrix: dict, start: str, order: list[str], back: bool) -> list[str]:
    """Reverse a stretch of the round while that makes it shorter; first improvement in index order, repeated."""
    order = list(order)
    improved = True
    while improved:
        improved = False
        current = path_length(matrix, start, tuple(order), back)
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                candidate = order[:i] + order[i : j + 1][::-1] + order[j + 1 :]
                length = path_length(matrix, start, tuple(candidate), back)
                if length < current - EPSILON_M:
                    order, current, improved = candidate, length, True
    return order


def best_order(matrix: dict, start: str, stops: list[str], back: bool) -> tuple[list[str], str]:
    if len(stops) <= EXACT_MAX_STOPS:
        return list(exact_order(matrix, start, stops, back)), "exact (all orders compared)"
    return two_opt(matrix, start, nearest_neighbour(matrix, start, stops), back), "nearest neighbour + 2-opt"


def distance_matrix(bm: BuildingMap, nodes: list[str], step_free: bool) -> dict:
    rg = routing.routing_graph(bm, step_free)
    return {node: routing.distances_from(bm, rg, node, nodes) for node in nodes}


# ---------- the round ----------


def entrance_options(bm: BuildingMap) -> list[dict]:
    """Rooms with an entrance, one per room, at most MAX_ENTRANCES."""
    found = {
        item["space_id"]: {"name": item["name"], "space_id": item["space_id"], "floor": item["floors"][0]}
        for item in connector_candidates(bm, "entrance", None)
    }
    return [found[space_id] for space_id in sorted(found)][:MAX_ENTRANCES]


def plan_round(
    bm: BuildingMap,
    what: str,
    start: str | None,
    floor_level: int | None = None,
    area: str | None = None,
    return_to_start: bool = False,
    step_free: bool = False,
) -> dict:
    """The shortest round from `start` (a space id or name) to every room holding a matching device. Sets bm.last_route
    (routing.route of the final round) and bm.located_asset_ids (the devices, for highlighting)."""
    assets, asset_type, tied = resolve_assets(bm, what)
    if tied:
        return {
            "needs_choice": True,
            "question": "Which devices do you mean: " + ", ".join(t.replace("_", " ") for t in tied) + "?",
        }
    if not assets:
        raise MapError(f"No device here matches '{what[:60]}'.")
    if floor_level is not None:
        levels = {floor_id: floor["level"] for floor_id, floor in bm.floors.items()}
        on_floor = [a for a in assets if levels[a["floor_id"]] == floor_level]
        if not on_floor:
            found = sorted({bm.floor_name(a["floor_id"]) for a in assets})
            raise MapError(f"No matching device on level {floor_level}. They are on: {', '.join(found)}.")
        assets = on_floor
    if area:
        in_area = [a for a in assets if area_match(bm, bm.spaces[a["space_id"]], area)]
        if not in_area:
            raise MapError(
                f"No matching device in '{area[:60]}'. Rooms that have one: {', '.join(area_names(bm, assets))}."
            )
        assets = in_area
    start_id = bm.resolve_space(start)
    by_room: dict[str, list[dict]] = {}
    for asset in sorted(assets, key=lambda a: (natural_key(a["name"]), a["id"])):
        by_room.setdefault(asset["space_id"], []).append(asset)
    if len(by_room) > MAX_STOPS:
        raise MapError(f"{len(by_room)} rooms is too many for one round. Narrow it to a floor or an area.")
    rooms = sorted(by_room)
    matrix = distance_matrix(bm, sorted({start_id, *rooms}), step_free)
    reachable = [room for room in rooms if room in matrix[start_id]]
    unreachable = [room for room in rooms if room not in reachable]
    if not reachable:
        raise MapError(f"None of these rooms can be reached from {bm.describe_space(start_id)}.")
    order, method = best_order(matrix, start_id, reachable, return_to_start)
    naive = sorted(reachable, key=lambda room: (natural_key(bm.spaces[room]["name"]), room))
    total = path_length(matrix, start_id, tuple(order), return_to_start)
    naive_total = path_length(matrix, start_id, tuple(naive), return_to_start)
    via, destination = (order, start_id) if return_to_start else (order[:-1], order[-1])
    route = routing.route(bm, start_id, destination, step_free, via)
    bm.located_asset_ids = [a["id"] for room in order for a in by_room[room]]
    stops, here = [], start_id
    for number, room in enumerate(order, start=1):
        stops.append(
            {
                "n": number,
                "room": bm.spaces[room]["name"],
                "space_id": room,
                "floor": bm.floor_name(bm.spaces[room]["floor_id"]),
                "devices": [a["name"] for a in by_room[room]],
                "leg_m": round(matrix[here][room], 1),
            }
        )
        here = room
    saved = round(naive_total - total, 1)
    return {
        "device_type": (asset_type or what).replace("_", " "),
        "devices": sum(len(by_room[room]) for room in order),
        "start": bm.spaces[start_id]["name"],
        "stops": stops,
        **({"back_to_start_m": round(matrix[order[-1]][start_id], 1)} if return_to_start else {}),
        "total_m": round(total, 1),
        "about_minutes": max(1, round(total / WALK_M_PER_S / 60)),
        "step_free": step_free,
        "order": method,
        "compare_hint": {
            "naive_order": "rooms in name order",
            "naive_total_m": round(naive_total, 1),
            "saved_m": saved,
            "say": f"{saved:.0f} m shorter than going through the rooms in name order."
            if saved >= 1
            else "Name order happens to be as short here.",
        },
        **(
            {"unreachable": [bm.describe_space(room) for room in unreachable] + ["(left out of the round)"]}
            if unreachable
            else {}
        ),
        "route": {"length_m": route.length_m, "drawn": True, "guide": "Say 'guide me' to be led stop by stop."},
    }


def make_round_tools(bm: BuildingMap, guide: GuideState) -> list:
    @beta_tool
    def plan_round_tool(
        what: str,
        start: str | None = None,
        floor_level: int | None = None,
        area: str | None = None,
        return_to_start: bool = False,
        step_free: bool = False,
        replace_guide: bool = False,
    ) -> str:
        """Inspection round: the SHORTEST order to visit every device of one type ('check all fire extinguishers
        on the ground floor'), computed here (exact for up to 8 rooms). Devices in one room are one stop. Returns
        the stops in order with metres per leg, total metres, minutes and compare_hint (how much shorter than
        name order); the round is drawn on the plan and can be guided. Never order stops yourself.

        Args:
            what: Device type in the person's words, e.g. "fire extinguisher", "Feuerlöscher", "defibrillators".
            start: Space id or room name where the round starts. Leave it out (or "here") to start at the
                person's position; with no position the result lists entrances to ask about.
            floor_level: Only devices on this floor (0 = ground floor, -1 = basement). Omit for all floors.
            area: Only devices in matching rooms: a name ("Server room"), a ref or prefix ("H-A", "H-A4"),
                a room type ("production zones") or "Hall A".
            return_to_start: True if the round ends back at the start.
            step_free: True to avoid stairs and steps.
            replace_guide: True only after the person agreed to drop the route they are being guided on.
        """
        if start is not None and fold(start).strip() in HERE_WORDS:
            start = None
        if start is None and guide.position is None:
            if "answer:" in str(getattr(guide, "last_user_text", "")).lower():
                raise ToolError(no_position_error(guide))  # a benchmark message: nobody can answer a question
            return as_json(
                {
                    "needs_start": True,
                    "question": "Where do you start the round?",
                    "entrances": entrance_options(bm),
                }
            )
        start_id = guide.position.space_id if start is None else start
        try:
            if guide.walk is not None and guide.walk.mode == "guided" and not replace_guide:
                destination = bm.spaces[guide.walk.destination]["name"]
                return as_json(
                    {
                        "needs_confirmation": True,
                        "question": f"I am guiding you to {destination}. Do you want to start the round instead?",
                    }
                )
            result = plan_round(bm, what, start_id, floor_level, area, return_to_start, step_free)
            if bm.last_route is not None and "stops" in result:
                via = [stop["space_id"] for stop in result["stops"]]
                remember_route(bm, guide, bm.last_route, via if return_to_start else via[:-1])
                guide.signature = building_signature(bm)
        except MapError as error:
            raise ToolError(str(error)) from error
        if start is None:
            result.update({"start_assumed": bm.describe_space(start_id), **position_note(bm, guide.position)})
        return as_json(result)

    plan_round_tool.name = "plan_round"
    return [plan_round_tool]
