"""Walking a route with a person who cannot look at a screen: an overview first, then one step at a time.

Pure Python state machine on the conversation state (GuideState.walk). Modes:
- plain: all steps were handed out at once (short routes, or a route from find_route); nothing to guide.
- overview: 2 to 4 landmarks, the length and one offer. Nothing else is read out.
- guided: only the current step. The person moves on with next, done, "I'm here", "where next" or by naming a
  place on the route; repeat never advances; back, how far, stop, overview and start over work as named.
- stopped: guiding ended, the route is kept so the person can say "start over" or "overview".

The words a person says reach `intent`, which maps English and German phrasings to an action, so the mapping is
tested and does not depend on the model. Nothing here detects arrival (there is no GPS): the person says it."""

import itertools
import re
from dataclasses import dataclass, field

from building_agent import routing
from building_agent.directions import turn_plan
from building_agent.find_tools import CONNECTOR_KINDS, words_of
from building_agent.position import make_position, nearest
from starter_agent.building_map import BuildingMap, MapError

WALK_M_PER_S = 1.2
MIN_STEPS_FOR_OVERVIEW = 3  # a route of 3 or more steps starts with the overview
MAX_LANDMARKS = 4
PACE_ROUND_S = 5
OFFER = "Want me to talk you through it while you walk?"
SAY_OVERVIEW = (
    "Say the landmarks in ONE flowing sentence in the person's language (no list, no bullets, no step numbers), "
    "then the length in metres, then the offer. Nothing else, no other lengths."
)
SAY_STEP = (
    "Say a 1 to 3 word acknowledgement (not for the first step), then this one step in one short sentence. No step "
    "numbers, no list, no question, nothing about later steps. You may add about_seconds as 'about twenty seconds'."
)
SAY_LAST = "Say \"You're there. That was the last step.\" in the person's language, nothing else."
ID_IN_BRACKETS = re.compile(r"\s*\[[^\[\]]*\]")
MODES = ("plain", "overview", "guided", "stopped")


@dataclass
class Walk:
    """The route handed to the person and where they are on it. `index` is the step they are about to do."""

    spaces: list[str]
    start: str
    destination: str
    step_free: bool
    via: list[str]
    length_m: float
    steps: list[str]
    rooms: list[list[str]]  # rooms each step enters (empty for the arrival step)
    room_pos: list[int] = field(default_factory=list)  # index in `spaces` of the room before each step
    mode: str = "plain"
    index: int = 0
    left_cache: dict = field(default_factory=dict)


def spoken(text: str) -> str:
    """No ids in anything that is read out."""
    return ID_IN_BRACKETS.sub("", text)


def guide_conflict(bm: BuildingMap, state, target: str, replace: bool) -> dict | None:
    """A second route while one is being guided asks first. None when the new route may go ahead."""
    old = state.walk
    if old is None or old.mode != "guided" or replace or target == old.destination:
        return None
    return {
        "needs_confirmation": True,
        "question": f"I am guiding you to {bm.spaces[old.destination]['name']}. "
        f"Do you want to go to {bm.spaces[target]['name']} instead?",
    }


def room_positions(spaces: list[str], rooms: list[list[str]]) -> list[int]:
    """For each step, where on the room sequence the person stands before it (a room may occur twice)."""
    found, at = [], 0
    for entered in rooms:
        found.append(at)
        for room in entered:
            at = next((i for i in range(at + 1, len(spaces)) if spaces[i] == room), at)
    return found


def build_walk(bm: BuildingMap, route, via: list[str] | None = None, mode: str = "plain") -> Walk:
    plan = turn_plan(bm, route)
    return Walk(
        spaces=list(route.space_path),
        start=route.start_space_id,
        destination=route.destination_space_id,
        step_free=route.step_free,
        via=list(via or []),
        length_m=route.length_m,
        steps=[spoken(step.text) for step in plan],
        rooms=[list(step.rooms) for step in plan],
        room_pos=room_positions(list(route.space_path), [list(step.rooms) for step in plan]),
        mode=mode,
    )


def remember_route(bm: BuildingMap, state, route, via: list[str] | None = None, mode: str = "plain") -> Walk:
    state.walk = build_walk(bm, route, via, mode)
    return state.walk


def room_at(walk: Walk, index: int) -> str:
    """The room the person stands in when they are about to do step `index`."""
    found = walk.start
    for rooms in walk.rooms[:index]:
        if rooms:
            found = rooms[-1]
    return found


def room_index(walk: Walk) -> int:
    """Where the person is on the room sequence."""
    return walk.room_pos[walk.index] if walk.room_pos else 0


def metres_left(bm: BuildingMap, walk: Walk, index: int) -> float | None:
    """Route length from the room before step `index` to the destination, through the stops still ahead."""
    if index not in walk.left_cache:
        here = room_at(walk, index)
        passed = {room for rooms in walk.rooms[:index] for room in rooms}
        ahead = [stop for stop in walk.via if stop not in passed and stop != here]
        previous = bm.last_route
        try:
            walk.left_cache[index] = routing.route(bm, here, walk.destination, walk.step_free, ahead or None).length_m
        except MapError:
            walk.left_cache[index] = None
        finally:
            bm.last_route = previous
    return walk.left_cache[index]


def name_of(bm: BuildingMap, space_id: str) -> str:
    return bm.spaces[space_id]["name"]


def step_payload(bm: BuildingMap, walk: Walk) -> dict:
    """The current step only: one instruction with its landmark, no question. `about_seconds` is a pace hint."""
    index, count = walk.index, len(walk.steps)
    arrived = index >= count - 1
    here, after = metres_left(bm, walk, index), None if arrived else metres_left(bm, walk, index + 1)
    leg = here - after if here is not None and after is not None else None
    seconds = round(leg / WALK_M_PER_S / PACE_ROUND_S) * PACE_ROUND_S if leg is not None and leg > 0 else 0
    return {
        "mode": "guided",
        "step": walk.steps[index],
        "step_number": index + 1,
        "of": count,
        "arrived": arrived,
        "destination": name_of(bm, walk.destination),
        "about_seconds": seconds or None,
        "say": SAY_LAST if arrived else SAY_STEP,
    }


def landmark_indexes(walk: Walk) -> list[int]:
    """2 to 4 steps worth naming: the first, every lift or stair ride (a ride past several floors counts once,
    at its last floor), then evenly spread ones. Never the arrival."""
    last = len(walk.steps) - 1
    rides = [i for i in range(last) if walk.steps[i].startswith("Take ")]
    rides = [
        i
        for i in rides
        if not (i + 1 in rides and walk.steps[i].rsplit(" to ", 1)[0] == walk.steps[i + 1].rsplit(" to ", 1)[0])
    ]
    chosen = {0, *rides}
    spread = [i for i in range(1, last) if i not in chosen and not walk.steps[i].startswith("Take ")]
    while len(chosen) < MAX_LANDMARKS and spread:
        chosen.add(spread.pop(len(spread) // 2))
    return sorted(chosen)[:MAX_LANDMARKS]


def overview_payload(bm: BuildingMap, walk: Walk) -> dict:
    return {
        "mode": "overview",
        "landmarks": [walk.steps[i] for i in landmark_indexes(walk)],
        "length_m": walk.length_m,
        "steps_total": len(walk.steps),
        "destination": name_of(bm, walk.destination),
        "offer": OFFER,
        "say": SAY_OVERVIEW,
    }


def payload(bm: BuildingMap, walk: Walk) -> dict:
    if walk.mode == "guided":
        return step_payload(bm, walk)
    if walk.mode == "overview":
        return overview_payload(bm, walk)
    return {"mode": walk.mode, "steps": walk.steps, "length_m": walk.length_m}


# ---------- what the person said ----------

PATTERNS = [  # first match wins; order matters ("where do I go again" must not read as "again")
    ("stop", r"\b(stop|cancel|abbrechen|beenden|hoer auf|hör auf|schluss)\b"),
    ("overview", r"\b(overview|summary|whole way|übersicht|uebersicht|zusammenfassung|ganzen weg)\b"),
    ("restart", r"\b(start over|restart|from the beginning|von vorn|von vorne|neu starten)\b"),
    (
        "repeat_destination",
        r"\b(where do i go again|wo ging'?s nochmal hin|wo ging es nochmal hin|wo ging's noch mal hin)\b",
    ),
    ("back", r"\b(back|previous|zurück|zurueck)\b"),
    ("where", r"\b(where am i|how far|how much is left|wie weit|wo bin ich|wie viel noch)\b"),
    ("repeat", r"\b(repeat|again|nochmal|noch mal|wiederhole|say that again)\b"),
    (
        "advance",
        (
            r"\b(next|done|ok|okay|weiter|fertig|erledigt|got it|i'?m here|i am here|i'?m there|i am there|arrived|"
            r"ich bin da|ich bin hier|angekommen|und jetzt|where next|what now|what'?s next|wo geht'?s jetzt hin|"
            r"wo geht es jetzt hin|wo jetzt)\b"
        ),
    ),
]
YES = r"\b(yes|yeah|yep|sure|please|guide me|walk me|talk me|begleite mich|begleit mich|ja|klar|gerne|gern)\b"


def intent(said: str, mode: str) -> str | None:
    """The action behind the person's words, or None. In the overview only a clear yes starts guiding
    ('ok' and 'next' are not a yes there); 'guide me' and 'begleite mich' start it in any mode."""
    text = " ".join(str(said or "").lower().split())[:200]
    if re.search(r"\b(guide me|walk me|talk me|begleite mich|begleit mich)\b", text):
        return "guide"
    for action, pattern in PATTERNS:
        if re.search(pattern, text):
            if action == "advance" and mode == "overview":
                break
            return action
    if mode == "overview":
        if re.search(r"\b(no|nope|nein|nicht|no thanks|not now)\b", text):
            return "decline"
        if re.search(YES, text):
            return "guide"
    return None


# ---------- the state machine ----------


def set_route_position(bm: BuildingMap, state, walk: Walk) -> None:
    here = room_at(walk, walk.index)
    if here in bm.spaces:  # walking outside between two entrances has no room
        state.position = make_position(bm, here, None, "route", state.turn)


def apply(bm: BuildingMap, state, said: str) -> dict:
    """One person message while a walk exists: change the state and return what to say."""
    walk = state.walk
    action = intent(said, walk.mode)
    if action is None:
        return {
            **payload(bm, walk),
            "note": "Not clear what the person wants. Ask in one short sentence.",
            "unclear": True,
        }
    if action == "guide":
        walk.mode = "guided"
        set_route_position(bm, state, walk)
        return step_payload(bm, walk)
    if action == "overview":
        walk.mode = "overview"
        return overview_payload(bm, walk)
    if walk.mode == "plain":
        if action in ("repeat", "repeat_destination"):  # all steps again, in the same words
            return {
                "mode": "plain",
                "steps": walk.steps,
                "length_m": walk.length_m,
                "destination": name_of(bm, walk.destination),
                **({"say_destination": True} if action == "repeat_destination" else {}),
            }
        return {"mode": "plain", "steps": [], "done": True, "note": "All steps were already given."}
    if walk.mode == "overview":
        if action in ("stop", "decline"):
            walk.mode = "stopped"
            return {"mode": "stopped", "note": "No guiding. Say once that you will not guide; the route stays."}
        return {**overview_payload(bm, walk), "note": "Guiding has not started. Ask the offer, wait for a clear yes."}
    if walk.mode == "stopped":
        if action == "restart":
            walk.mode, walk.index = "guided", 0
            set_route_position(bm, state, walk)
            return step_payload(bm, walk)
        return {"mode": "stopped", "note": "Guiding is stopped. Offer to start over or give the overview."}
    last = len(walk.steps) - 1
    if action == "stop":
        walk.mode = "stopped"
        return {"mode": "stopped", "note": "Guiding ended. Say it once, no question."}
    if action == "restart":
        walk.index = 0
    elif action == "back":
        walk.index = max(0, walk.index - 1)
    elif action == "advance":
        if walk.index >= last:
            return {**step_payload(bm, walk), "note": "The person is already there. Say so, do not repeat the step."}
        walk.index += 1
    elif action == "where":
        left = metres_left(bm, walk, walk.index)
        return {
            "mode": "guided",
            "step_number": walk.index + 1,
            "of": len(walk.steps),
            "metres_left": None if left is None else round(left),
            "destination": name_of(bm, walk.destination),
        }
    result = step_payload(bm, walk)
    if action == "repeat_destination":
        return {**result, "say_destination": True}
    if action != "repeat":
        set_route_position(bm, state, walk)
    return result


# ---------- places the person names ----------


def room_named(bm: BuildingMap, space_id: str, said: str, floor_level: int | None) -> bool:
    space = bm.spaces.get(space_id)
    if space is None or (floor_level is not None and bm.floors[space["floor_id"]]["level"] != floor_level):
        return False
    names = {" ".join(words_of(space["name"])), " ".join(words_of(space.get("ref") or ""))} - {""}
    return said in names or any(name in said for name in names)


def locate(bm: BuildingMap, walk: Walk, place: str, floor_level: int | None = None) -> str | None:
    """The room of the rest of the route that `place` names, or None if it does not name one clearly.

    A lift or stair is found by its kind or name among the connectors the route still uses (the first one on the
    way, so 'the lift' is the one ahead), a room by number or name."""
    ahead = walk.spaces[room_index(walk) :]
    said = " ".join(words_of(place))
    if not said or not ahead:
        return None
    hits: list[str] = []
    for connector in bm.connectors.values():
        name = " ".join(words_of(connector["name"]))
        named = bool(name) and name in said
        kind = any(CONNECTOR_KINDS.get(word, word) == connector["kind"] for word in said.split())
        stops = [space_id for space_id in ahead if space_id in connector["space_ids"]]
        if (named or kind) and stops:
            hits.append(stops[0])
    if hits:
        return min(hits, key=ahead.index)
    rooms = [space_id for space_id in dict.fromkeys(ahead) if room_named(bm, space_id, said, floor_level)]
    return rooms[0] if len(rooms) == 1 else None


def follow(bm: BuildingMap, state, space_id: str) -> dict | None:
    """The person is now in `space_id` (position already set). With a walk, recompute what is left from there.

    On the route this is the rest of the same route. Off it, the place is a fresh position and the way to the
    same destination is routed anew ('rerouted'). Returns what to say, or None if there is no walk."""
    walk = state.walk
    if walk is None:
        return None
    ahead = walk.spaces[room_index(walk) :]
    on_route = space_id in ahead
    if walk.mode in ("plain", "stopped") and not on_route:
        state.walk = None
        return {"on_route": False}
    after = ahead[ahead.index(space_id) + 1 :] if on_route else ahead
    via_ahead = [stop for stop in walk.via if stop in after]
    kept = bm.last_route  # the page keeps drawing the route that was asked for, not the rest of it
    try:
        fresh = routing.route(bm, space_id, walk.destination, walk.step_free, via_ahead or None)
    except MapError as error:
        state.walk = None
        return {"on_route": on_route, "note": str(error)}
    finally:
        bm.last_route = kept
    state.walk = build_walk(bm, fresh, via_ahead, walk.mode if walk.mode != "stopped" else "plain")
    if on_route:
        state.position = make_position(bm, space_id, None, "route", state.turn)
    return {
        "on_route": on_route,
        "rerouted": not on_route,
        "remaining_length_m": fresh.length_m,
        **payload(bm, state.walk),
    }


# ---------- closures and other changes while a walk is active ----------


def left_now(bm: BuildingMap, state) -> float | None:
    """Metres left from the person's room, measured before a change so the effect can be told afterwards."""
    walk = state.walk
    return None if walk is None or walk.mode == "plain" else metres_left(bm, walk, walk.index)


def alternative(bm: BuildingMap, state, walk: Walk) -> dict | None:
    """When the destination can no longer be reached: the nearest reachable room of the same type."""
    here = room_at(walk, walk.index)
    try:
        found = nearest(
            bm,
            make_position(bm, here, None, "route", state.turn),
            bm.spaces[walk.destination]["room_type"],
            exclude=[walk.destination],
            step_free=walk.step_free,
        )
    except MapError:
        return None
    return found["nearest"] if not found["needs_choice"] else found["tied"][0]


def path_is_open(bm: BuildingMap, spaces: list[str], step_free: bool) -> bool:
    """The rooms in this order can still be walked: no room closed, an open door or connector between each pair."""
    for first, second in itertools.pairwise(spaces):
        if first in bm.closed or second in bm.closed:
            return False
        pair = {first, second}
        door = any(
            opening["id"] not in bm.closed
            and set(opening["space_ids"]) == pair
            and (opening["step_free"] or not step_free)
            for opening in bm.openings.values()
        )
        lift_or_stairs = any(
            connector["id"] not in bm.closed
            and pair <= set(connector["space_ids"])
            and (connector["step_free"] or not step_free)
            for connector in bm.connectors.values()
        )
        if not (door or lift_or_stairs):
            return False
    return True


def after_change(bm: BuildingMap, state, before_left: float | None) -> dict | None:
    """The building changed (a closure the person confirmed, or an edit on the page) while a walk is active:
    recompute what is left from the person's room, avoiding what is closed, and say what that means."""
    walk = state.walk
    if walk is None or walk.mode == "plain":
        return None
    here = room_at(walk, walk.index)
    ahead = walk.spaces[room_index(walk) :]
    via_ahead = [stop for stop in walk.via if stop in ahead[1:]]
    kept = bm.last_route
    try:
        fresh = routing.route(bm, here, walk.destination, walk.step_free, via_ahead or None)
    except MapError as error:
        return {
            "no_route": True,
            "note": f"{error} Say so honestly and offer the alternative if there is one.",
            "alternative": alternative(bm, state, walk),
        }
    finally:
        bm.last_route = kept
    same_length = before_left is None or abs(fresh.length_m - before_left) < 0.01
    if same_length and path_is_open(bm, ahead, walk.step_free):  # a tie to another way does not count as a change
        walk.left_cache.clear()
        return {"route_unaffected": True}
    longer = None if before_left is None else round(fresh.length_m - before_left, 1)
    state.walk = build_walk(bm, fresh, via_ahead, walk.mode)
    return {"rerouted": True, "longer_by_m": longer, "remaining_length_m": fresh.length_m, **payload(bm, state.walk)}


def guide_info(walk: Walk | None) -> dict | None:
    """What the page needs while guiding: the current leg as rooms. None unless guiding and not yet arrived."""
    if walk is None or walk.mode != "guided" or walk.index >= len(walk.steps) - 1 or not walk.rooms[walk.index]:
        return None
    rooms = walk.rooms[walk.index]
    return {
        "step_index": walk.index,
        "step_count": len(walk.steps),
        "from": room_at(walk, walk.index),
        "to": rooms[-1],
        "between": rooms[:-1],
        "step_free": walk.step_free,
        "target": walk.destination,
    }
