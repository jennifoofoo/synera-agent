"""Inspection rounds: visit every device of one type in an area in the shortest order, all in Python.

`plan_round` finds the matching devices, makes one stop per DEVICE (two devices in one room are two stops),
measures every device-to-device walk on the door-to-door route model (`routing`, the same graph and in-room walks
as find_route with start_point / destination_point: from the device through its room's doors to the next device)
and orders the stops: exact (Held-Karp) for up to EXACT_MAX_STOPS stops, else nearest neighbour from the start
followed by 2-opt until nothing improves. Ties go to the smaller asset id, so the same question always gives the
same round. The round is drawn once with `routing.route` through every device (via stops with via_points), so the
drawn line touches each device and its length is total_m; it is remembered like find_route, so the plan shows it
and "guide me" can start. The model only picks the arguments and
phrases the result."""

import itertools
import re

import networkx as nx
import numpy as np
from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent import routing
from building_agent.find_tools import connector_candidates, matching_assets, natural_key, words_of
from building_agent.guide_tools import GuideState, building_signature
from building_agent.position import no_position_error, position_note
from building_agent.task_tools import fold, types_for_task
from building_agent.walk import WALK_M_PER_S, remember_route
from starter_agent.building_map import LENGTH_DECIMALS, BuildingMap, MapError
from starter_agent.tools import as_json

EXACT_MAX_STOPS = 16  # Held-Karp up to here (about 0.1 s for 16 stops); above it nearest neighbour + 2-opt
MAX_STOPS = 60
START = "@start"  # the start's key in the distance matrix (asset ids are the other keys)
MAX_ENTRANCES = 6
EPSILON_M = 1e-6  # a new order must be shorter by more than this to replace the one found first
HERE_WORDS = {"here", "hier", "me", "my position", "current position", "where i am"}
HALL_LETTER = re.compile(r"^(?:hall|halle)\s+([a-z])$")
# "the entrance in Main aisle H-B3", "Eingang in Halle A": the room behind the door is the start.
ENTRANCE_IN = re.compile(
    r"^(?:at\s+)?(?:the\s+)?(?:main\s+)?(?:entrance|eingang)\s+(?:in|at|of|to|im|in der|zur|zum)\s+", re.IGNORECASE
)


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


def start_space(bm: BuildingMap, start: str | None) -> str:
    """resolve_space, also for "entrance in <room>" (people name the start by its entrance)."""
    try:
        return bm.resolve_space(start)
    except MapError:
        room = ENTRANCE_IN.sub("", (start or "").strip())
        if room == (start or "").strip():
            raise
        return bm.resolve_space(room)


def area_names(bm: BuildingMap, assets: list[dict]) -> list[str]:
    return sorted({bm.spaces[a["space_id"]]["name"] for a in assets}, key=natural_key)[:12]


# ---------- ordering ----------


def path_length(matrix: dict, start: str, order: tuple, back: bool) -> float:
    stops = (start, *order, *((start,) if back else ()))
    return sum(matrix[a][b] for a, b in itertools.pairwise(stops))


def held_karp(matrix: dict, start: str, stops: list[str], back: bool) -> list[str]:
    """The shortest order by Held-Karp dynamic programming (O(n² · 2ⁿ), numpy over all subsets of one size at a
    time), run over the rest of the round: rest[mask, j] is the shortest walk that starts at stop j, visits the
    stops in `mask` and ends (or goes back to the start). The order is then read from the front, and every minimum
    takes the first index on a tie, so of equally long rounds the one with the smaller asset ids first wins."""
    order = sorted(stops)
    n = len(order)
    if n == 0:
        return []
    inf = float("inf")
    between = np.array([[matrix[a].get(b, inf) for b in order] for a in order])
    from_start = np.array([matrix[start].get(b, inf) for b in order])
    to_start = np.array([matrix[a].get(start, inf) for a in order]) if back else np.zeros(n)
    rest = np.full((1 << n, n), inf)
    then = np.full((1 << n, n), -1, dtype=np.int16)  # the stop after j in the best rest
    bits = 1 << np.arange(n)
    rest[bits, np.arange(n)] = to_start
    masks = np.arange(1 << n)
    sizes = np.array([m.bit_count() for m in range(1 << n)])
    for size in range(1, n):
        layer = masks[sizes == size]
        through = between.T[None, :, :] + rest[layer][:, :, None]  # (masks, k, j): j, then the rest from k
        following = through.argmin(axis=1)  # first k on a tie: the smaller id goes next
        length = np.take_along_axis(through, following[:, None, :], axis=1)[:, 0, :]
        for j in range(n):
            free = (layer & bits[j]) == 0
            target = layer[free] | bits[j]
            rest[target, j] = length[free, j]
            then[target, j] = following[free, j]
    mask = (1 << n) - 1
    here = int((from_start + rest[mask]).argmin())
    path = []
    while here >= 0:
        path.append(order[here])
        here, mask = int(then[mask, here]), mask ^ (1 << here)
    return path


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
        return held_karp(matrix, start, stops, back), "exact (Held-Karp, shortest of all orders)"
    return two_opt(matrix, start, nearest_neighbour(matrix, start, stops), back), "nearest neighbour + 2-opt"


def distance_matrix(bm: BuildingMap, nodes: list[str], step_free: bool) -> dict:
    """Room-to-room (anchor to anchor) route lengths, as routing.route measures them without points."""
    rg = routing.routing_graph(bm, step_free)
    return {node: routing.distances_from(bm, rg, node, nodes) for node in nodes}


def device_point(bm: BuildingMap, asset: dict) -> tuple[float, float] | None:
    """The device's position as a route end inside its room (routing.check_point), None (the room's anchor) when
    the position is too far outside the room to be a route end."""
    try:
        return routing.check_point(bm, asset["space_id"], asset["position"][:2])
    except MapError:
        return None


def add_point_node(bm: BuildingMap, rg: routing.RoutingGraph, graph, node: str, space_id: str, point) -> None:
    """On a copy of the graph: an extra node for an exact point in a room, wired like routing.rewire_room wires the
    room node (walks to the room's doors, stair and lift edges plus the walk to the anchor), so a search from or to
    it measures what routing.route measures with start_point / destination_point. The room node stays as it is."""
    walks = routing.room_walks(bm, rg, space_id, point)
    for neighbour in list(graph.neighbors(space_id)):
        for edge in list(graph[space_id][neighbour].values()):
            if "via" in edge:
                graph.add_edge(
                    node, neighbour, **{**edge, "weight": round(edge["weight"] + walks["anchor"], LENGTH_DECIMALS)}
                )
            elif neighbour not in walks["doors"]:
                graph.add_edge(node, neighbour, **edge)
    for door, length in walks["doors"].items():
        graph.add_edge(node, door, weight=round(length, LENGTH_DECIMALS), space=space_id)


def point_matrix(bm: BuildingMap, ends: dict[str, tuple[str, tuple | None]], step_free: bool) -> dict:
    """{key: {key: metres}} between exact points: ends maps a key to (space id, point or None for the anchor).
    Two ends in one room walk inside the room (routing.same_room_walk), like routing.route does."""
    rg = routing.routing_graph(bm, step_free)
    graph = rg.graph.copy()
    nodes: dict[str, str] = {}
    for key, (space_id, point) in ends.items():
        if space_id not in graph:
            continue
        if point is None:
            nodes[key] = space_id
        else:
            nodes[key] = f"point:{key}"
            add_point_node(bm, rg, graph, nodes[key], space_id, point)
    matrix: dict[str, dict[str, float]] = {}
    for key, node in nodes.items():
        reached = nx.single_source_dijkstra_path_length(graph, node, weight="weight")
        row = {}
        for other, other_node in nodes.items():
            space, other_space = ends[key][0], ends[other][0]
            if space == other_space:
                row[other] = routing.same_room_walk(bm, space, ends[key][1], ends[other][1])
            elif other_node in reached:
                row[other] = reached[other_node]
        matrix[key] = row
    return matrix


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
    start_point=None,
) -> dict:
    """The shortest round from `start` (a space id or name; `start_point` an exact [x, y] in it, e.g. the person's
    dot) to every matching device, one stop per device. Sets bm.last_route (routing.route through every device, the
    same legs as the stops' leg_m) and bm.located_asset_ids (the devices, for highlighting)."""
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
    start_id = start_space(bm, start)
    if start_point is not None:
        try:
            start_point = routing.check_point(bm, start_id, start_point)
        except MapError:
            start_point = None  # a dot too far outside its room: start at the room instead
    if len(assets) > MAX_STOPS:
        raise MapError(f"{len(assets)} devices is too many for one round. Narrow it to a floor or an area.")
    by_id = {asset["id"]: asset for asset in assets}
    points = {asset_id: device_point(bm, asset) for asset_id, asset in by_id.items()}
    ends = {START: (start_id, start_point), **{i: (by_id[i]["space_id"], points[i]) for i in sorted(by_id)}}
    matrix = point_matrix(bm, ends, step_free)
    reachable = [asset_id for asset_id in sorted(by_id) if asset_id in matrix.get(START, {})]
    unreachable = sorted({by_id[i]["space_id"] for i in by_id if i not in reachable})
    if not reachable:
        raise MapError(f"None of these devices can be reached from {bm.describe_space(start_id)}.")
    order, method = best_order(matrix, START, reachable, return_to_start)
    naive = sorted(reachable, key=lambda i: (natural_key(by_id[i]["name"]), i))
    total = path_length(matrix, START, tuple(order), return_to_start)
    naive_total = path_length(matrix, START, tuple(naive), return_to_start)
    # The drawn round is the legs themselves: start -> device 1 -> ... (-> start), every via stop at its device.
    rooms = [by_id[i]["space_id"] for i in order]
    at = [points[i] for i in order]
    if return_to_start:
        via, via_points, destination, end_point = rooms, at, start_id, start_point
    else:
        via, via_points, destination, end_point = rooms[:-1], at[:-1], rooms[-1], at[-1]
    route = routing.route(bm, start_id, destination, step_free, via, start_point, None, end_point, via_points)
    bm.located_asset_ids = list(order)
    legs, here = [], START
    for asset_id in order:
        legs.append(round(matrix[here][asset_id], 1))
        here = asset_id

    def where(asset_id: str) -> list[float] | None:
        point = points[asset_id]
        return None if point is None else [round(point[0], 3), round(point[1], 3)]

    # For the page (web/api.py adopt_agent_route): this route is a round, so the page can guide it device by device.
    bm.planned_round = {
        "route": route,
        "via": via,
        "via_points": [list(point) if point is not None else None for point in via_points],
        "destination_point": list(end_point) if end_point is not None else None,
        "info": {
            "device_type": asset_type or what,
            "start": start_id,
            "start_point": list(start_point) if start_point is not None else None,
            "stops": [
                {
                    "asset_id": asset_id,
                    "asset_ids": [asset_id],
                    "name": by_id[asset_id]["name"],
                    "space_id": by_id[asset_id]["space_id"],
                    "position": where(asset_id),
                    "leg_m": leg,
                }
                for asset_id, leg in zip(order, legs, strict=True)
            ],
            "return_to_start": return_to_start,
            **({"back_to_start_m": round(matrix[order[-1]][START], 1)} if return_to_start else {}),
            "total_m": round(total, 1),
            "step_free": step_free,
        },
    }
    stops = []
    for number, (asset_id, leg) in enumerate(zip(order, legs, strict=True), start=1):
        room = by_id[asset_id]["space_id"]
        stops.append(
            {
                "n": number,
                "asset_id": asset_id,
                "device": by_id[asset_id]["name"],
                "room": bm.spaces[room]["name"],
                "space_id": room,
                "floor": bm.floor_name(bm.spaces[room]["floor_id"]),
                "position": where(asset_id),
                "devices": [by_id[asset_id]["name"]],
                "leg_m": leg,
            }
        )
    saved = round(naive_total - total, 1)
    return {
        "device_type": (asset_type or what).replace("_", " "),
        "devices": len(order),
        "start": bm.spaces[start_id]["name"],
        "stops": stops,
        **({"back_to_start_m": round(matrix[order[-1]][START], 1)} if return_to_start else {}),
        "total_m": round(total, 1),
        "about_minutes": max(1, round(total / WALK_M_PER_S / 60)),
        "step_free": step_free,
        "order": method,
        "compare_hint": {
            "naive_order": "devices in name order",
            "naive_total_m": round(naive_total, 1),
            "saved_m": saved,
            "say": f"{saved:.0f} m shorter than going to the devices in name order."
            if saved >= 1
            else "Name order happens to be as short here.",
        },
        **(
            {"unreachable": [bm.describe_space(room) for room in unreachable] + ["(left out of the round)"]}
            if unreachable
            else {}
        ),
        "route": {"drawn": True, "guide": "Say 'guide me' to be led device by device."},
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
        on the ground floor'), computed here (exact for up to 16 devices). One stop per device, walked device to
        device. Returns the stops in order with metres per leg, total metres, minutes and compare_hint (how much shorter than
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
            point = guide.position.point if start is None else None
            result = plan_round(bm, what, start_id, floor_level, area, return_to_start, step_free, point)
            if bm.last_route is not None and "stops" in result:
                remember_route(bm, guide, bm.last_route, bm.planned_round["via"])
                guide.signature = building_signature(bm)
        except MapError as error:
            raise ToolError(str(error)) from error
        if start is None:
            result.update({"start_assumed": bm.describe_space(start_id), **position_note(bm, guide.position)})
        return as_json(result)

    plan_round_tool.name = "plan_round"
    return [plan_round_tool]
