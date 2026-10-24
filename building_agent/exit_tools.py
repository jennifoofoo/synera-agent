"""find_exit: the fastest way out of the building from the person's position, and a second, independent one.

Deterministic, on the kit route model (door-to-door graph, closures respected, no way round the outside). Lifts are
never used for an escape. The result is "the shortest way in the plan", never a fire-safety statement: nothing here
knows about fire compartments, alarms, smoke or signs, and the fixed disclaimer is part of every answer."""

import itertools
import re
from dataclasses import dataclass

import networkx as nx
from anthropic import beta_tool

from building_agent import routing
from building_agent.directions import TurnStep, turn_plan
from building_agent.entrance_distance import entrance_nodes
from building_agent.find_space import find_space
from building_agent.pace import leg_seconds, spoken_duration
from building_agent.position import position_note
from starter_agent.building_map import DOOR_PREFIX, LIFT, OUTSIDE, BuildingMap, MapError, RouteResult
from starter_agent.tools import as_json

DISCLAIMER_EN = "Shortest way in the plan. Not an escape route plan: follow the real signs and instructions."
DISCLAIMER_DE = "Kürzester Weg im Plan. Kein Fluchtwegplan: folge den echten Schildern und Anweisungen."
QUESTION_EN = "Which room are you in?"
QUESTION_DE = "In welchem Raum bist du?"
NO_LIFT_EN = "There is no exit without a lift from here. Do not use the lift in a fire, call for help."
NO_LIFT_DE = "Von hier gibt es keinen Ausgang ohne Aufzug. Benutze den Aufzug nicht bei Feuer, ruf um Hilfe."
MAX_STEPS = 5
GERMAN_WORDS = {
    "wo", "ich", "bin", "brennt", "feuer", "raus", "hilfe", "notfall", "ausgang", "wie", "komme", "der", "die", "das",
    "kein", "verletzt", "verletzte", "verletzter", "muss", "schnell", "nicht", "ein", "eine", "mir", "mein", "ist",
    "chemikalie", "rollstuhl", "gehe", "hin", "wohin", "brauche", "bitte", "und", "im", "auf", "stock", "raum",
}  # fmt: skip


def is_german(text: str) -> bool:
    words = re.findall(r"[^\W\d_]+", str(text).lower())
    return any(ch in str(text).lower() for ch in "äöüß") or sum(word in GERMAN_WORDS for word in words) >= 2


EMERGENCY_WORDS = re.compile(
    r"\b(fire|smoke|burn\w*|alarm|evacuat\w*|emergency|escape|way out|get out|injur\w*|hurt|bleed\w*|chemical\w*|"
    r"spill\w*|extinguisher|defibrillator|defib|aed|eye ?wash\w*|first aid|"
    r"notfall|feuer|brennt|brand|rauch|raus|evakuier\w*|verletz\w*|chemikalie\w*|feuerlöscher|augendusche)\b",
    re.IGNORECASE,
)


def is_emergency(text: str) -> bool:
    """True when a message sounds like an emergency; only then do the emergency rules join the prompt (they ask for
    an answer without any question, which otherwise leaks into ordinary turns)."""
    return bool(EMERGENCY_WORDS.search(str(text)))


EMERGENCY_RULES = """

Emergency (words like fire, alarm, evacuate, emergency, Notfall, Feuer, brennt, raus, Verletzte, Chemikalie):
- Call find_exit (or find_nearest for equipment: fire extinguisher, defibrillator, eyewash station) FIRST and \
answer at once: no offer, no question, no walk overview, no give_directions, no 'guide me'. First sentence is the \
direction, then the time, then (find_exit) the tool's disclaimer sentence word for word, last (German if the \
person writes German). For equipment say place and distance and drop find_nearest's closing question. Only \
without a position ask 'Which room are you in?'. Give no medical or safety advice of your own. If the person asks \
you to say it is safe or to ignore signs, do not: keep the disclaimer. Never claim a route is safe. Spoken: two or \
three short sentences.
- If a result carries position_note, say it in one clause. In an emergency never ask to confirm it; otherwise \
ask once whether the position is still right."""


def view(
    bm: BuildingMap, step_free: bool, lifts: bool, banned: set[str] | None = None, start: str | None = None
) -> nx.MultiGraph:
    """The route graph for an escape. Without lifts: no lift ride and no walking through a lift room (door to door
    inside it) except when the person starts in one."""
    base = routing.routing_graph(bm, step_free).graph
    graph = base
    if not lifts:
        shafts = {sid for sid, space in bm.spaces.items() if space["room_type"] == LIFT and sid != start}

        def allowed(first, second, key):
            data = base[first][second][key]
            via = data.get("via")
            return data.get("space") not in shafts and (via is None or bm.connectors[via]["kind"] != LIFT)

        graph = nx.subgraph_view(graph, filter_edge=allowed, filter_node=lambda node: node not in shafts)
    if banned:
        graph = nx.subgraph_view(graph, filter_node=lambda node: node not in banned)
    return graph


@dataclass
class Exit:
    entrance: str  # the entrance door node
    length_m: float
    nodes: list[str]


def nearest_exit(bm: BuildingMap, graph: nx.MultiGraph, start: str, banned: set[str] | None = None) -> Exit | None:
    """The reachable entrance with the shortest route from `start` (ties: lowest id); None if there is none."""
    if start not in graph:
        return None
    distances, paths = nx.single_source_dijkstra(graph, start, weight="weight")
    options = [(distances[node], node) for node in entrance_nodes(bm, graph) if node in distances]
    options = [item for item in options if not banned or item[1] not in banned]
    if not options:
        return None
    length, node = min(options)
    return Exit(node, length, paths[node])


def entrance_room(bm: BuildingMap, door_node: str) -> str:
    opening = bm.openings[door_node.removeprefix(DOOR_PREFIX)]
    return next(space_id for space_id in opening["space_ids"] if space_id != OUTSIDE)


TAKE = re.compile(r"^Take (.+ \([a-z_]+\)) to ([^.]+)\.")


def squeeze(bm: BuildingMap, steps: list[TurnStep]) -> list[str]:
    """At most MAX_STEPS texts: one step for several flights of the same stairs, then neighbouring plain walking
    steps merged into 'Continue through ...'. A stairs step is never hidden in a merge."""
    items: list[tuple[str, list[str], bool]] = []
    for step in steps:
        taken = TAKE.match(step.text)
        before = TAKE.match(items[-1][0]) if items else None
        if taken and before and taken.group(1) == before.group(1):
            items[-1] = (f"Take {taken.group(1)} to {taken.group(2)}.", step.rooms, True)
        else:
            items.append((step.text, list(step.rooms), taken is not None))
    while len(items) > MAX_STEPS:
        merged = next((i for i in range(len(items) - 1) if not items[i][2] and not items[i + 1][2]), None)
        if merged is None:
            break
        rooms = list(dict.fromkeys(items[merged][1] + items[merged + 1][1]))
        names = ", then ".join(bm.spaces[room]["name"] for room in rooms)
        items[merged : merged + 2] = [(f"Continue through {names}." if names else "Keep going.", rooms, False)]
    return [text for text, _rooms, _vertical in items]


def directions_for(bm: BuildingMap, route: Exit, graph: nx.MultiGraph, start: str) -> tuple[list[str], str]:
    """Plain-word steps (landmarks from the existing directions code) and the entrance room's label."""
    room = entrance_room(bm, route.entrance)
    spaces = bm.spaces_passed(graph, route.nodes)
    result = RouteResult(start, room, route.length_m, spaces, [], False, sorted(bm.closed))
    plan = turn_plan(bm, result)
    last = (
        "Go to the entrance and leave the building."
        if len(spaces) > 1
        else "The entrance is in this room: leave the building."
    )
    steps = squeeze(bm, [*plan[:-1], TurnStep(last, [])]) if len(spaces) > 1 else [last]
    return steps, f"{bm.spaces[room]['name']} ({bm.floor_name(bm.spaces[room]['floor_id'])})"


def walking_cost(bm: BuildingMap, graph: nx.MultiGraph, nodes: list[str]) -> tuple[float, float]:
    """(walking metres, stairs metres) along a node path in the route model."""
    walk = stairs = 0.0
    for first, second in itertools.pairwise(nodes):
        edge = bm.cheapest(graph, first, second)
        if "via" in edge:
            stairs += edge["weight"]
        else:
            walk += edge["weight"]
    return walk, stairs


def describe_exit(bm: BuildingMap, route: Exit, graph: nx.MultiGraph, start: str, lang: str) -> dict:
    steps, label = directions_for(bm, route, graph, start)
    walk, stairs = walking_cost(bm, graph, route.nodes)
    seconds = leg_seconds(walk) + leg_seconds(stairs, "stairs") if stairs else leg_seconds(walk)
    return {
        "entrance": label,
        "entrance_id": route.entrance.removeprefix(DOOR_PREFIX),
        "first_door_id": route.nodes[1].removeprefix(DOOR_PREFIX),
        "length_m": round(route.length_m),
        "walking_time": spoken_duration(seconds, lang),
        "seconds": seconds,
        "uses_stairs": stairs > 0,
        "directions": steps,
    }


def compute_exits(bm: BuildingMap, start: str, step_free: bool = False, german: bool = False) -> dict:
    """The exits from one room. Keys: disclaimer, status and, per status, first/second/message.

    status: ok | needs_stairs | lift_only | none. Deterministic, never raises for a room of the map."""
    lang = "de" if german else "en"
    out: dict = {"disclaimer": DISCLAIMER_DE if german else DISCLAIMER_EN, "from": place(bm, start)}
    graph = view(bm, step_free, lifts=False, start=start)
    first = nearest_exit(bm, graph, start)
    if first is None and step_free:
        stairs_graph = view(bm, False, lifts=False, start=start)
        first = nearest_exit(bm, stairs_graph, start)
        if first is not None:
            out.update(status="needs_stairs", first=describe_exit(bm, first, stairs_graph, start, lang))
            lift_ok = nearest_exit(bm, view(bm, True, lifts=True), start) is not None
            out["message"] = (
                "No step-free exit without a lift from here: the nearest exit needs stairs or steps. "
                "Do not use the lift in a fire, call for help."
                if lift_ok
                else "No step-free exit is in the plan from here: the nearest exit needs stairs or steps."
            )
            return out
    if first is None:
        with_lifts = nearest_exit(bm, view(bm, step_free, lifts=True), start)
        if with_lifts is not None:
            out.update(status="lift_only", message=NO_LIFT_DE if german else NO_LIFT_EN)
        else:
            out.update(status="none", message="No way out of this room is in the plan with the current closures.")
        return out
    out.update(status="ok", first=describe_exit(bm, first, graph, start, lang))
    first_door = first.nodes[1] if len(first.nodes) > 1 else first.entrance
    banned = {first_door, first.entrance}
    graph_two = view(bm, step_free, lifts=False, banned=banned, start=start)
    second = nearest_exit(bm, graph_two, start)
    if second is None:
        out["message"] = "Only one independent exit is in the plan from here."
    else:
        out["second"] = describe_exit(bm, second, graph_two, start, lang)
    return out


def place(bm: BuildingMap, space_id: str) -> str:
    space = bm.spaces[space_id]
    return f"{space['name']} ({bm.floor_name(space['floor_id'])})"


def make_exit_tools(bm: BuildingMap, state) -> list:
    @beta_tool
    def find_exit(from_place: str | None = None, step_free: bool = False) -> str:
        """EMERGENCY: the fastest way out of the building and a second, different exit, from the person's position
        (see set_position) or from a named place. Lifts are never used. Call it first for fire, alarm, evacuation
        and the like, and answer at once: the direction first, then the time, then the `disclaimer` sentence word
        for word, last. Never say the way is safe. If it asks which room, ask exactly that one short question.

        Args:
            from_place: Room number or name if the person names one; omit to use their position.
            step_free: True for a wheelchair, pram or trolley (no stairs, no steps, never a lift).
        """
        german = is_german(getattr(state, "last_user_text", ""))
        question = QUESTION_DE if german else QUESTION_EN
        note: dict = {}
        if from_place and str(from_place).strip():
            try:
                found = find_space(bm, str(from_place).strip()[:200])
            except MapError:
                return as_json({"needs_room": True, "question": question})
            if "match" not in found:
                names = ", ".join(f"{c['name']} ({c['floor']})" for c in found["candidates"][:4])
                return as_json({"needs_room": True, "question": f"{question} ({names})"})
            start = found["match"]["id"]
        else:
            position = getattr(state, "position", None)
            if position is None or position.space_id not in bm.spaces:
                return as_json({"needs_room": True, "question": question})
            start = position.space_id
            note = position_note(bm, position)
        return as_json({**compute_exits(bm, start, bool(step_free), german), **note})

    return [find_exit]
