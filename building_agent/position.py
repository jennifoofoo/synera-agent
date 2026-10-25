"""Where the person stands ("you are here"): the state, and the deterministic parts that use it.

The server alone sets a Position (tools, or the validated click context of the page), never a sentence in the user
message. Everything here is plain Python on the building map: ranking hits by route length from the position and
the remembered route with its room sequence. The model only chooses which tool to call and phrases the reply."""

import time
from dataclasses import dataclass, field

from building_agent import routing
from building_agent.find_tools import matching_assets, parse_query, words_of
from building_agent.safety_words import safety_query
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError

SOURCES = ("said", "click", "device", "route")
MAX_QUERY_CHARS = 120
MAX_OPTIONS = 6
CLOCK = time.monotonic  # seconds; tests replace it to age a position without waiting
STALE_AFTER_S = 600.0  # a position older than this is 'last known'
TIE_M = 1.0  # two different rooms this close in route length count as equally near
BENCHMARK_START = (
    "The start is given in the question: pass it as `start` (a room number or name from the question). "
    "Nobody can answer, never ask where the person is."
)
NO_POSITION = "I do not know where the person is. Ask once 'Where are you?', then call set_position."


@dataclass(frozen=True)
class Position:
    space_id: str
    floor_id: str
    point: tuple[float, float] | None = None
    source: str = "said"
    turn: int = 0
    set_at: float | None = field(
        default=None, compare=False
    )  # CLOCK() when set; None for a hand-built Position (age unknown)

    def view(self) -> dict:
        """What the page gets in state_view: {space_id, floor_id, point, source}."""
        return {
            "space_id": self.space_id,
            "floor_id": self.floor_id,
            "point": list(self.point) if self.point else None,
            "source": self.source,
        }


def no_position_error(state) -> str:
    """The message when a route has no start: ask the person, except in a benchmark message ('Answer:').
    Asking marks state.asked_position: the chat reply then tells the page it waits for a place (needs_position)."""
    if "answer:" in str(getattr(state, "last_user_text", "")).lower():
        return BENCHMARK_START
    state.asked_position = True
    return NO_POSITION


def make_position(bm: BuildingMap, space_id: str, point=None, source: str = "said", turn: int = 0) -> Position:
    if space_id not in bm.spaces or source not in SOURCES:
        raise MapError(f"Unknown space or source: {space_id!r}, {source!r}.")
    floor_id = bm.spaces[space_id]["floor_id"]
    return Position(space_id, floor_id, tuple(point) if point else None, source, turn, CLOCK())


def place_label(bm: BuildingMap, space_id: str) -> str:
    space = bm.spaces[space_id]
    return f"{space['name']} ({bm.floor_name(space['floor_id'])})"


def age_seconds(position: Position) -> float | None:
    return None if position.set_at is None else max(0.0, CLOCK() - position.set_at)


def age_words(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes} minutes" if minutes < 120 else f"{minutes // 60} hours"


def position_note(bm: BuildingMap, position: Position | None) -> dict:
    """{'position_note': ..., 'position_old': True} when the position is older than 10 minutes, else {}.

    Used wherever the position is the default start. Emergency answers state it, other answers ask once."""
    age = None if position is None else age_seconds(position)
    if position is None or age is None or age <= STALE_AFTER_S:
        return {}
    return {
        "position_old": True,
        "position_note": f"from your last known position, {place_label(bm, position.space_id)}, "
        f"set {age_words(age)} ago",
    }


def page_note(bm: BuildingMap, state) -> str:
    """A line in front of the person's message when the page changed the position since the model last heard of it.

    The model only learns a tapped position through tools, and with an earlier 'Where are you?' in the history it
    kept asking although the page had set it (it answered from the history without a tool call). The note comes
    from the conversation state (a validated click), never from message text. A typed copy of it changes nothing:
    every tool reads state.position, not the message."""
    position = getattr(state, "position", None)
    told = getattr(state, "told_position", None)
    if position is not None and position.source == "click" and position.space_id in bm.spaces:
        if position.space_id == told:
            return ""
        state.told_position = position.space_id
        return (
            f"(Page note, not typed by the person: they tapped their position on the plan, it is now "
            f"{place_label(bm, position.space_id)}. Do not ask where they are; routes and 'nearest' start there.)"
        )
    if position is None and told is not None:
        state.told_position = None
        return "(Page note, not typed by the person: their position was cleared, it is unknown now.)"
    if position is not None:
        state.told_position = position.space_id if position.source == "click" else None
    return ""


def describe_position(bm: BuildingMap, position: Position, now_turn: int | None = None) -> dict:
    space = bm.spaces[position.space_id]
    return {
        **position_note(bm, position),
        "space_id": position.space_id,
        "room": space["name"],
        "floor": bm.floor_name(position.floor_id),
        "source": position.source,
        "turns_ago": None if now_turn is None else max(0, now_turn - position.turn),
    }


# ---------- route length from the position ----------


def lengths_from(bm: BuildingMap, start: str, targets: list[str], step_free: bool = False) -> dict[str, float]:
    """Route length in metres from one room to each reachable target room. Does not touch bm.last_route."""
    found = routing.distances_from(bm, routing.routing_graph(bm, step_free), start, targets)
    return {target: round(length, 2) for target, length in found.items()}


def matching_places(bm: BuildingMap, what: str, floor_level: int | None = None) -> tuple[dict[str, list[str]], str]:
    """Rooms that count as 'X': by room type first, else rooms holding a matching device. Returns
    ({space_id: [asset names]}, label). Raises MapError when nothing matches."""
    text = safety_query(bm, str(what or "")[:MAX_QUERY_CHARS])
    tokens = words_of(text)
    if not tokens:
        raise MapError("Say what to find, for example 'coffee machine' or 'toilet'.")
    label = " ".join(tokens)

    def on_floor(space: dict) -> bool:
        return floor_level is None or bm.floors[space["floor_id"]]["level"] == floor_level

    usable = [space for space in bm.spaces.values() if space["id"] != OUTSIDE and on_floor(space)]
    wanted = "_".join(tokens)
    for candidate in dict.fromkeys([wanted, wanted.removesuffix("es"), wanted.removesuffix("s")]):
        rooms = [space["id"] for space in usable if space["room_type"] == candidate]
        if rooms:
            return {space_id: [] for space_id in rooms}, label
    asset_tokens, _, _ = parse_query(text)
    by_space: dict[str, list[str]] = {}
    for asset in matching_assets(bm, asset_tokens, floor_level):
        by_space.setdefault(asset["space_id"], []).append(asset["name"])
    if by_space:
        return by_space, label
    loose = {
        space["id"]: []
        for space in usable
        if set(tokens) <= set(words_of(space["room_type"]) + words_of(space["name"]))
    }
    if loose:
        return loose, label
    where = f" on level {floor_level}" if floor_level is not None else ""
    raise MapError(f"Nothing matches '{label}'{where} in this building.")


def nearest(
    bm: BuildingMap,
    position: Position,
    what: str,
    floor_level: int | None = None,
    exclude: list[str] | None = None,
    step_free: bool = False,
) -> dict:
    """The closest room for 'nearest X' by route length from the position, one control sentence, a tie rule.

    `exclude` holds rooms or devices already offered ('another one' gives the next nearest)."""
    places, label = matching_places(bm, what, floor_level)
    skipped = {bm.assets[item]["space_id"] if item in bm.assets else item for item in exclude or []}
    lengths = lengths_from(
        bm, position.space_id, [space_id for space_id in places if space_id not in skipped], step_free
    )
    ranked = sorted(lengths.items(), key=lambda item: (item[1], item[0]))
    if not ranked:
        left = [space_id for space_id in places if space_id not in skipped]
        if not left:
            raise MapError(f"There is no other {label} in this building.")
        raise MapError(f"No route from {place_label(bm, position.space_id)} to any {label} with the current closures.")

    def entry(space_id: str, length: float) -> dict:
        return {
            "space_id": space_id,
            "name": bm.spaces[space_id]["name"],
            "floor": bm.floor_name(bm.spaces[space_id]["floor_id"]),
            "length_m": length,
            "devices": places[space_id][:5],
        }

    result: dict = {
        "query": label,
        "from": place_label(bm, position.space_id),
        "matches": len(places),
        "nearest": entry(*ranked[0]),
        "others": [entry(*item) for item in ranked[1:3]],
        "needs_choice": False,
    }
    tied = [item for item in ranked if item[1] - ranked[0][1] <= TIE_M][:MAX_OPTIONS]
    # Rooms with the same name on the same floor ("Toilets" or "Toilets"?) give the person nothing to choose by:
    # the shorter route wins. A question only when the tied rooms can be told apart.
    if len(tied) > 1 and len({place_label(bm, space_id) for space_id, _ in tied}) > 1:
        listed = " or ".join(place_label(bm, space_id) for space_id, _ in tied)
        result["needs_choice"] = True
        result["tied"] = [entry(*item) for item in tied]
        result["question"] = f"The nearest {label} is equally far away ({ranked[0][1]:g} m): {listed}. Which one?"
        return result
    first = result["nearest"]
    far = "right here" if first["length_m"] < 1.0 else f"{first['length_m']:.0f} m from you"
    result["control_sentence"] = (
        f"Nearest {label}: {place_label(bm, first['space_id'])}, {far}. Do you mean a different one?"
    )
    return result


# ---------- exact start point ----------

EXACT_POSITION_NOTE = "from your exact position"


def exact_start_point(bm: BuildingMap, state) -> tuple[float, float] | None:
    """The point to start a route at when the person gave no start: the session position's own point, if it has
    one that lies in its room. Never in a benchmark message ('Answer:'), never from message text."""
    position = getattr(state, "position", None)
    if position is None or position.point is None or "answer:" in str(getattr(state, "last_user_text", "")).lower():
        return None
    try:
        return routing.check_point(bm, position.space_id, position.point, position.floor_id)
    except MapError:
        return None
