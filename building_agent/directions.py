"""Hands-free directions: landmark phrasing for a route and hand-out in chunks of at most 3 steps.

Pure Python on building.json data, no LLM. Not a question kind; the agent calls it after BuildingMap.route."""

import math
from collections import Counter
from dataclasses import dataclass

from shapely.geometry import Point, Polygon

from building_agent.geometry import repaired
from starter_agent.building_map import ADJACENT_DISTANCE_M, OUTSIDE, BuildingMap, RouteResult

MAX_STEPS = 3
STRAIGHT_DEG = 30.0
AROUND_DEG = 150.0
MIN_LEG_M = 0.3
LANDMARK_RADIUS_M = 7.0
FEW_M = 3.0
NAMED_ROOM_TYPES = frozenset({"lobby", "stairwell", "lift", "canteen", "lecture_hall", "library"})
# Types that are everywhere or look alike; never worth naming (derived from the dataset's type census).
BORING_TYPES = frozenset(
    {
        "chair", "office_chair", "dining_chair", "outdoor_chair", "desk", "wardrobe", "built_in_wardrobe",
        "nightstand", "plant", "shelf", "bookshelf", "paper_shelf", "single_bed", "bed", "filing_cabinet",
        "seminar_table", "coffee_table", "dining_table", "outdoor_table", "meeting_table", "canteen_table",
        "reading_table", "tv_stand", "armchair", "locker", "coat_rack", "shoe_cabinet", "lecture_seating_row",
        "bench", "tool_cabinet", "chemical_cabinet", "toilet", "sink", "bathtub", "shower", "kitchen_counter",
        "internal_stairs", "fire_extinguisher", "hand_dryer", "washing_machine", "dishwasher", "fridge",
        "stove", "microwave", "whiteboard", "projector", "projector_screen", "display_screen", "hvac_unit",
        "ups_unit", "electrical_panel", "defibrillator", "eyewash_station",
    }
)  # fmt: skip
CATEGORY_RANK = {"machine": 0, "equipment": 2, "fixture": 3, "furniture": 4}
SPACE_RANK = 1
PLAIN_ROOM_TYPES = {"corridor", "office", "generic_room"}


@dataclass
class Landmark:
    kind: str  # "asset" or "space"
    id: str
    label: str


def _candidates(bm: BuildingMap, space_id: str) -> list[tuple[tuple, Landmark]]:
    """Landmarks in or next to one space, each with a sort key (rarer on the floor first)."""
    space = bm.spaces[space_id]
    floor_id = space["floor_id"]
    asset_count = Counter(a["type"] for a in bm.assets.values() if a["floor_id"] == floor_id)
    room_count = Counter(s["room_type"] for s in bm.spaces.values() if s["floor_id"] == floor_id)
    found = []
    for asset in bm.assets.values():
        count = asset_count[asset["type"]]
        if asset["space_id"] != space_id or (asset["category"] == "furniture" and count > 1):
            continue
        label = asset["type"].replace("_", " ")
        found.append(((count, 1, asset["id"]), Landmark("asset", asset["id"], label)))
    polygon = repaired(Polygon(space["polygon"]))
    for other in bm.spaces.values():
        if other["id"] == space_id or other["floor_id"] != floor_id or other["room_type"] in PLAIN_ROOM_TYPES:
            continue
        if polygon.distance(repaired(Polygon(other["polygon"]))) <= ADJACENT_DISTANCE_M:
            key = (room_count[other["room_type"]], 0, other["id"])
            found.append((key, Landmark("space", other["id"], other["name"])))
    return found


def pick_landmark(bm: BuildingMap, space_id: str, used: set[str] | None = None) -> Landmark | None:
    """Best landmark in or next to a space: unique on the floor first, then rooms before assets.

    Landmarks in `used` are skipped unless nothing else is left. Deterministic (ties break on id)."""
    if space_id not in bm.spaces:
        return None
    ranked = [landmark for _, landmark in sorted(_candidates(bm, space_id), key=lambda item: item[0])]
    fresh = [landmark for landmark in ranked if landmark.id not in (used or set())]
    return (fresh or ranked or [None])[0]


def _hint(landmark: Landmark | None) -> str:
    if landmark is None:
        return ""
    if landmark.kind == "asset":
        return f" You will see the {landmark.label}."
    return f" {landmark.label} is right next to it."


def _connector_between(bm: BuildingMap, first: str, second: str) -> dict | None:
    for connector in bm.connectors.values():
        if first in connector["space_ids"] and second in connector["space_ids"]:
            return connector
    return None


def leg_space(route: RouteResult, index: int) -> str:
    """The space step `index` of route.steps is about (the arrival step uses the destination)."""
    return route.space_path[min(index, len(route.space_path) - 1)]


def leg_landmarks(bm: BuildingMap, route: RouteResult) -> list[Landmark | None]:
    """One landmark (or None) per entry of route.steps, same order and length.

    The last move into the destination gets none, the arrival step carries the destination's landmark."""
    path = route.space_path
    used: set[str] = set()
    result: list[Landmark | None] = []
    for index in range(len(path) + 1):
        is_last_move = len(path) > 1 and index == len(path) - 1
        landmark = None if is_last_move else pick_landmark(bm, leg_space(route, index), used)
        if landmark:
            used.add(landmark.id)
        result.append(landmark)
    return result


def landmark_directions(bm: BuildingMap, route: RouteResult) -> list[str]:
    """Route as short steps with a landmark per leg instead of distances. Same length as route.steps."""
    path = route.space_path
    landmarks = leg_landmarks(bm, route)
    steps = [f"Start in {bm.describe_space(path[0])}.{_hint(landmarks[0])}"]
    for index in range(1, len(path)):
        previous, current = path[index - 1], path[index]
        hint = _hint(landmarks[index])
        if current == OUTSIDE:
            steps.append("Leave the building through the entrance.")
        elif previous in bm.spaces and bm.spaces[previous]["floor_id"] != bm.spaces[current]["floor_id"]:
            connector = _connector_between(bm, previous, current)
            name = connector["name"] if connector else "the connector"
            kind = connector["kind"] if connector else "connector"
            floor = bm.floor_name(bm.spaces[current]["floor_id"])
            steps.append(f"Take {name} ({kind}) to {floor}.{hint}")
        else:
            steps.append(f"Go into {bm.spaces[current]['name']}.{hint}")
    steps.append(f"You have arrived at {bm.describe_space(path[-1])}.{_hint(landmarks[-1])}")
    return steps


@dataclass
class TurnStep:
    """One spoken step. `turn` is left/right/straight/around or None (no turn word)."""

    text: str
    rooms: list[str]  # space ids entered by this step (empty for the arrival)
    turn: str | None = None
    landmark: Landmark | None = None
    door_position: tuple[float, float] | None = None


@dataclass
class _Move:
    previous: str
    current: str
    kind: str  # door, vertical, exit, enter
    point: tuple[float, float] | None = None
    door_id: str | None = None
    turn: str | None = None


def turn_word(incoming: tuple[float, float], outgoing: tuple[float, float]) -> str | None:
    """Turn from walking `incoming` to walking `outgoing` (x right, y up), None if a leg is too short."""
    if math.hypot(*incoming) < MIN_LEG_M or math.hypot(*outgoing) < MIN_LEG_M:
        return None
    cross = incoming[0] * outgoing[1] - incoming[1] * outgoing[0]
    dot = incoming[0] * outgoing[0] + incoming[1] * outgoing[1]
    angle = math.degrees(math.atan2(cross, dot))
    if abs(angle) <= STRAIGHT_DEG:
        return "straight"
    if abs(angle) > AROUND_DEG:
        return "around"
    return "left" if angle > 0 else "right"


def _anchor(bm: BuildingMap, space_id: str) -> tuple[float, float] | None:
    return bm.anchor(space_id) if space_id in bm.spaces else None


def _move_kind(bm: BuildingMap, previous: str, current: str) -> str:
    if current == OUTSIDE:
        return "exit"
    if previous == OUTSIDE:
        return "enter"
    if bm.spaces[previous]["floor_id"] != bm.spaces[current]["floor_id"]:
        return "vertical"
    return "door"


def _door_layer(bm: BuildingMap, move: _Move) -> list[tuple[tuple[float, float] | None, str | None]]:
    if move.kind == "vertical":
        return [(_anchor(bm, move.current), None)]
    pair = {move.previous, move.current}
    doors = [o for o in bm.openings.values() if o["id"] not in bm.closed and set(o["space_ids"]) == pair]
    doors.sort(key=lambda o: o["id"])
    return [((o["position"][0], o["position"][1]), o["id"]) for o in doors] or [(None, None)]


def _distance(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float:
    return 0.0 if a is None or b is None else math.dist(a, b)


def _plan_moves(bm: BuildingMap, route: RouteResult) -> list[_Move]:
    """Moves between consecutive spaces; where several doors fit, the choice minimises the total walk."""
    path = route.space_path
    moves = [_Move(path[i - 1], path[i], _move_kind(bm, path[i - 1], path[i])) for i in range(1, len(path))]
    layers = [[(_anchor(bm, path[0]), None)], *[_door_layer(bm, m) for m in moves], [(_anchor(bm, path[-1]), None)]]
    best = [[0.0] * len(layer) for layer in layers]
    back = [[0] * len(layer) for layer in layers]
    for k in range(1, len(layers)):
        for j, (point, _) in enumerate(layers[k]):
            options = [best[k - 1][i] + _distance(layers[k - 1][i][0], point) for i in range(len(layers[k - 1]))]
            back[k][j] = min(range(len(options)), key=lambda i: (options[i], i))
            best[k][j] = options[back[k][j]]
    chosen = [0] * len(layers)
    chosen[-1] = min(range(len(layers[-1])), key=lambda j: (best[-1][j], j))
    for k in range(len(layers) - 1, 0, -1):
        chosen[k - 1] = back[k][chosen[k]]
    for k, move in enumerate(moves, start=1):
        move.point, move.door_id = layers[k][chosen[k]]
    points = [layers[0][0][0], *[m.point for m in moves], layers[-1][0][0]]
    for k, move in enumerate(moves, start=1):
        # The walk into the first door (from the start anchor) and out of a lift or stairwell (from its anchor)
        # gives the facing at that door, so those doors get a turn word too; an entrance does not.
        if move.kind != "door" or (k > 1 and moves[k - 2].kind == "exit"):
            continue
        before, here, after = points[k - 1], points[k], points[k + 1]
        if before is None or here is None or after is None:
            continue
        move.turn = turn_word((here[0] - before[0], here[1] - before[1]), (after[0] - here[0], after[1] - here[1]))
    return moves


def _door_landmark(bm: BuildingMap, move: _Move, used: set[str]) -> Landmark | None:
    """Best named thing within LANDMARK_RADIUS_M of the door, in either room: machines before furniture."""
    if move.point is None:
        return None
    door = Point(move.point)
    found = []
    room_names = {bm.spaces[move.previous]["name"], bm.spaces[move.current]["name"]}
    for space_id in (move.previous, move.current):
        for key, landmark in _candidates(bm, space_id):
            if landmark.id in used or landmark.id in (move.previous, move.current) or landmark.label in room_names:
                continue
            if landmark.kind == "asset":
                asset = bm.assets[landmark.id]
                distance = math.dist(asset["position"], move.point)
                rank = CATEGORY_RANK.get(asset["category"], 5)
                if asset["type"] in BORING_TYPES:
                    continue
            else:
                distance = repaired(Polygon(bm.spaces[landmark.id]["polygon"])).distance(door)
                rank = SPACE_RANK
            if distance <= LANDMARK_RADIUS_M:
                found.append(((rank, key[0], round(distance, 2), landmark.id), landmark))
    return min(found, key=lambda item: item[0])[1] if found else None


def _at(landmark: Landmark | None, word: str = "at") -> str:
    if landmark is None:
        return ""
    return f" {word} {'the ' if landmark.kind == 'asset' else ''}{landmark.label}"


def metres(distance: float | None) -> str | None:
    """A walking distance as people say it: 'a few metres' under 3 m, whole metres under 20 m, else steps of 5 m."""
    if distance is None:
        return None
    if distance < FEW_M:
        return "a few metres"
    if distance < 20:
        return f"{round(distance)} m"
    return f"{5 * round(distance / 5)} m"


def helps(bm: BuildingMap, space_id: str) -> bool:
    """Whether a room's name helps someone walking: lobbies, stairwells, lifts and other rooms you can recognise."""
    return space_id in bm.spaces and bm.spaces[space_id]["room_type"] in NAMED_ROOM_TYPES


def _into(bm: BuildingMap, space_id: str, word: str = "into") -> str:
    return f" ({word} {bm.spaces[space_id]['name']})" if helps(bm, space_id) else ""


def _vertical_step(bm: BuildingMap, move: _Move, used: set[str]) -> TurnStep:
    connector = _connector_between(bm, move.previous, move.current)
    name = connector["name"] if connector else "the connector"
    kind = connector["kind"] if connector else "connector"
    floor = bm.floor_name(bm.spaces[move.current]["floor_id"])
    landmark = pick_landmark(bm, move.current, used)
    if landmark:
        used.add(landmark.id)
    return TurnStep(f"Take {name} ({kind}) to {floor}.{_hint(landmark)}", [move.current], None, landmark)


def _leave_text(bm: BuildingMap, move: _Move, landmark: Landmark | None, distance: str | None) -> str:
    """The first walking step (facing unknown before it): out of the room, the metres to its door, the turn there."""
    head = f"Leave {bm.spaces[move.previous]['name']} through the door{_at(landmark, 'by')}"
    head += f" ({distance})" if distance else ""
    if move.turn in ("left", "right"):
        return f"{head}, then turn {move.turn}{_into(bm, move.current, 'towards')}."
    if move.turn == "around":
        return f"{head}, then turn around{_into(bm, move.current, 'towards')}."
    if move.turn == "straight":
        return f"{head} and go straight on{_into(bm, move.current)}."
    return f"{head}{_into(bm, move.current)}."


def _turn_text(bm: BuildingMap, move: _Move, landmark: Landmark | None, distance: str | None) -> str:
    walk = f"Walk {distance}" if distance else "Walk on"
    if move.turn in ("left", "right", "around"):
        return f"{walk}, then turn {move.turn}{_at(landmark)}{_into(bm, move.current, 'towards')}."
    lead = f"Walk straight on for {distance}" if distance and move.turn == "straight" else walk
    return f"{lead}{_at(landmark, 'past')}{_into(bm, move.current)}."


def _arrive_text(bm: BuildingMap, move: _Move, distance: str | None, leaving: bool) -> str:
    """The walk to the destination's door, with the side it is on when the geometry says so."""
    name = bm.spaces[move.current]["name"]
    if leaving and (move.turn not in ("left", "right", "straight") or not distance):
        head = f"Leave {bm.spaces[move.previous]['name']} through the door"
        return f"{head} into {name}" + (f" ({distance})." if distance else ".")
    if move.turn in ("left", "right") and distance:
        return f"Walk {distance} to {name} on your {move.turn}."
    if move.turn == "straight" and distance:
        return f"Walk {distance} to {name} straight ahead."
    return f"Walk {distance} into {name}." if distance else f"Go into {name}."


def turn_plan(bm: BuildingMap, route: RouteResult) -> list[TurnStep]:
    """Turn-first spoken steps like a navigation app: "Walk 12 m, then turn left at the coffee machine."

    Each step names the action and the metres to the door where it happens; room names come last and only where
    they help (the destination, lobbies, stairwells, lifts, see NAMED_ROOM_TYPES). The turn at a door comes from
    the walk into the door (previous door, or the room anchor) and the walk out of it (next door, or the
    destination anchor), in the building frame with y up: within 30 degrees is straight on, up to 150 degrees
    left or right (counter-clockwise is left), beyond that turn around. The first step cannot say which way to
    face, so it reads "Leave <room> through the door (8 m), then turn left." Straight-on doors (and doors without
    a turn word) merge into the next turn ("Walk 25 m, then turn right."), the walk to the destination's door says
    which side it is on ("Walk 5 m to Toilet 0.22 on your left."). Lifts, stairs and entrances keep their own
    wording. Every step enters at least one room, so the number of steps never exceeds the rooms on the route."""
    path = route.space_path
    if len(path) < 2:
        return [TurnStep(f"You are already at {bm.describe_space(path[0])}.", [])]
    moves = _plan_moves(bm, route)
    points = [_anchor(bm, path[0]), *[m.point for m in moves], _anchor(bm, path[-1])]
    legs = [
        None if points[k] is None or points[k + 1] is None else math.dist(points[k], points[k + 1])
        for k in range(len(moves))
    ]
    used: set[str] = set()
    arrival = pick_landmark(bm, path[-1], used)
    steps: list[TurnStep] = []
    run: list[int] = []  # straight-on doors waiting for the next turn

    def walked(indexes: list[int]) -> str | None:
        found = [legs[k] for k in indexes]
        return None if any(leg is None for leg in found) else metres(sum(found))

    def door_landmark(move: _Move, rooms: list[str]) -> Landmark | None:
        landmark = _door_landmark(bm, move, used)
        if landmark and landmark.id not in rooms and landmark.label not in {bm.spaces[r]["name"] for r in rooms}:
            used.add(landmark.id)
            return landmark
        return None

    def flush() -> None:
        if not run:
            return
        last = moves[run[-1]]
        landmark = door_landmark(last, [moves[k].current for k in run])
        text = _turn_text(bm, _Move(last.previous, last.current, "door", turn="straight"), landmark, walked(run))
        steps.append(TurnStep(text, [moves[k].current for k in run], "straight", landmark, last.point))
        run.clear()

    for k, move in enumerate(moves):
        is_last = k == len(moves) - 1
        leaving = k == 0 or moves[k - 1].kind in ("vertical", "enter")
        if move.kind != "door":
            flush()
            if move.kind == "vertical":
                steps.append(_vertical_step(bm, move, used))
            elif move.kind == "exit":
                steps.append(TurnStep("Leave the building through the entrance.", [move.current]))
            else:
                steps.append(
                    TurnStep(f"Go through the entrance into {bm.spaces[move.current]['name']}.", [move.current])
                )
            continue
        if is_last:
            rooms = [*(moves[i].current for i in run), move.current]
            text = _arrive_text(bm, move, walked([*run, k]), leaving and not run)
            run.clear()
            steps.append(TurnStep(text, rooms, move.turn, None, move.point))
            continue
        if not leaving and move.turn in ("straight", None):
            run.append(k)
            continue
        rooms = [*(moves[i].current for i in run), move.current]
        distance = walked([*run, k])
        run.clear()
        landmark = door_landmark(move, rooms)
        text = _leave_text(bm, move, landmark, distance) if leaving else _turn_text(bm, move, landmark, distance)
        steps.append(TurnStep(text, rooms, move.turn, landmark, move.point))
    flush()
    steps.append(TurnStep(f"You have arrived at {bm.describe_space(path[-1])}.{_hint(arrival)}", [], None, arrival))
    return steps


def turn_directions(bm: BuildingMap, route: RouteResult) -> list[str]:
    """Route as spoken steps with left/right/straight words and landmarks (see turn_plan)."""
    return [step.text for step in turn_plan(bm, route)]


def chunk_steps(steps: list[str], max_steps: int = MAX_STEPS) -> list[list[str]]:
    """Split steps into consecutive chunks of at most max_steps (default 3)."""
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1.")
    return [steps[start : start + max_steps] for start in range(0, len(steps), max_steps)]


class DirectionsSession:
    """Hands out directions chunk by chunk: next() = "weiter", repeat() = "nochmal"."""

    def __init__(self, steps: list[str], max_steps: int = MAX_STEPS) -> None:
        self.chunks = chunk_steps(steps, max_steps)
        self.position = 0  # number of chunks handed out so far

    @classmethod
    def from_route(cls, bm: BuildingMap, route: RouteResult, max_steps: int = MAX_STEPS) -> "DirectionsSession":
        return cls(turn_directions(bm, route), max_steps)

    def next(self) -> list[str]:
        """The next chunk, or [] when everything was handed out."""
        if self.position >= len(self.chunks):
            return []
        self.position += 1
        return self.chunks[self.position - 1]

    def repeat(self) -> list[str]:
        """The chunk handed out last, or [] if none yet."""
        return self.chunks[self.position - 1] if self.position else []

    def remaining(self) -> int:
        """Number of steps not handed out yet."""
        return sum(len(chunk) for chunk in self.chunks[self.position :])
