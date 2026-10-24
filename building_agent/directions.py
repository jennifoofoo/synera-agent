"""Hands-free directions: landmark phrasing for a route and hand-out in chunks of at most 3 steps.

Pure Python on building.json data, no LLM. Not a question kind; the agent calls it after BuildingMap.route."""

from collections import Counter
from dataclasses import dataclass

from shapely.geometry import Polygon

from starter_agent.building_map import ADJACENT_DISTANCE_M, OUTSIDE, BuildingMap, RouteResult

MAX_STEPS = 3
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
    polygon = Polygon(space["polygon"])
    for other in bm.spaces.values():
        if other["id"] == space_id or other["floor_id"] != floor_id or other["room_type"] in PLAIN_ROOM_TYPES:
            continue
        if polygon.distance(Polygon(other["polygon"])) <= ADJACENT_DISTANCE_M:
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
            steps.append(f"Go through the door into {bm.spaces[current]['name']}.{hint}")
    steps.append(f"You have arrived at {bm.describe_space(path[-1])}.{_hint(landmarks[-1])}")
    return steps


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
    def from_route(
        cls, bm: BuildingMap, route: RouteResult, max_steps: int = MAX_STEPS
    ) -> "DirectionsSession":
        return cls(landmark_directions(bm, route), max_steps)

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
