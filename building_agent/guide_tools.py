"""Conversation tools: hands-free directions in small chunks and edits that need a confirmed understanding card."""

import copy
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent import edit_ops, knowledge_tools, routing
from building_agent import walk as walking
from building_agent.directions import DirectionsSession
from building_agent.impact import analyse
from building_agent.position import EXACT_POSITION_NOTE, Position, exact_start_point, no_position_error
from building_agent.time_words import SCHEDULED_REPLY, names_a_time, when_is_later
from building_agent.walk import Walk
from starter_agent.building_map import BuildingMap, MapError
from starter_agent.tools import as_json

TIMED_REPLY = {
    "closed": False,
    "note": "This closure has an end time. Call propose_change(action='close', element, until=<their time words>) "
    "and show the card; nothing is closed until the person's yes.",
}
ACTIONS = (
    "close",
    "reopen",
    "add_door",
    "remove_door",
    "widen_door",
    "move_asset",
    "add_asset",
    "undo",
    "remember",
    "resolve",
)
KNOWLEDGE_ACTIONS = ("remember", "resolve")  # cards made by remember_here and resolve_here (knowledge_tools)
UNDO_DEPTH = 20
YES = re.compile(r"\b(ja|yes|yep|jep|genau|passt|do it|go ahead|mach das|bitte ja)\b", re.IGNORECASE)
NO = re.compile(r"\b(nein|no|nicht|stop|abbrechen|cancel|lieber|whatever|egal|aber|but|ja ja)\b", re.IGNORECASE)


@dataclass
class Pending:
    action: str
    element: str
    other: str | None
    step_free: bool
    card: dict
    turn: int
    signature: tuple = ()
    width_m: float | None = None
    to_space: str | None = None
    asset_type: str | None = None
    hint: dict | None = None
    extra: dict | None = None  # remember/resolve: the fact to store; close: until and reason


@dataclass
class GuideState:
    """Per-conversation state. `turn` counts user messages so a change cannot be proposed and confirmed in one."""

    session: DirectionsSession | None = None
    pending: Pending | None = None
    turn: int = 0
    signature: tuple = ()
    log: list[dict] = field(default_factory=list)
    undo: deque = field(default_factory=lambda: deque(maxlen=UNDO_DEPTH))
    position: Position | None = None  # where the person stands; only the server sets it, one per conversation
    last_user_text: str = ""  # the person's latest message, set by the agent: guards read it, not the model
    walk: Walk | None = None  # the route handed out last: room sequence, mode (overview, guided), current step
    knowledge: object | None = None  # KnowledgeStore (place knowledge) in a page session; None in the benchmark
    author: str | None = None  # who is talking, as typed on the page ('Technician A'); facts record it
    last_fact: dict | None = None  # the fact stored last in this conversation (for undo)
    facts_lookup: object | None = None  # rooms -> short lines of facts valid now; walk.py reads it while guiding

    def begin_turn(self) -> None:
        """A card can only be answered in the very next message; later it is stale and dropped."""
        self.turn += 1
        if self.pending is not None and self.turn > self.pending.turn + 1:
            self.pending = None


def element_label(bm: BuildingMap, element_id: str) -> str:
    if element_id in bm.connectors:
        return bm.connectors[element_id]["name"]
    if element_id in bm.spaces:
        return bm.describe_space(element_id)
    return element_id


def building_signature(bm: BuildingMap) -> tuple:
    """Changes whenever closures or doors change, so stale directions and cards can be detected."""
    openings = hash(tuple(sorted((o["id"], o.get("width_m"), o["step_free"]) for o in bm.openings.values())))
    assets = hash(
        tuple(
            sorted(
                (
                    a["id"],
                    a["space_id"],
                    tuple(a["position"]),
                    a["name"],
                    (a.get("footprint") or {}).get("rotation_deg"),
                )
                for a in bm.assets.values()
            )
        )
    )
    return (tuple(sorted(bm.closed)), len(bm.openings), openings, assets)


def apply_change(
    bm: BuildingMap,
    action: str,
    element: str,
    other: str | None,
    step_free: bool,
    width_m: float | None = None,
    to_space: str | None = None,
    asset_type: str | None = None,
    hint: dict | None = None,
) -> str:
    """Apply one edit to `bm`; returns a plain-words description. Raises MapError if it cannot be done."""
    if action == "add_door":
        if not other:
            raise MapError("add_door needs two rooms: element and other.")
        pair = {bm.resolve_space(element), bm.resolve_space(other)}
        if any(set(opening["space_ids"]) == pair for opening in bm.openings.values()):
            raise MapError("These two rooms already have a door between them.")
        opening = edit_ops.add_door_safe(bm, element, other, step_free)
        first, second = (bm.describe_space(space_id) for space_id in opening["space_ids"])
        return f"New {'step-free ' if step_free else ''}door between {first} and {second}."
    if action == "remove_door":
        edit = edit_ops.remove_door(bm, element, other)
        return f"Remove {edit_ops.door_label(bm, edit['opening'])} for good."
    if action == "widen_door":
        edit = edit_ops.widen_door(bm, element, other, width_m)
        door = edit_ops.door_label(bm, bm.openings[edit["id"]])
        before = f"from {edit['old_width_m']} m " if edit["old_width_m"] is not None else ""
        return f"Widen {door} {before}to {edit['width_m']} m."
    if action == "move_asset":
        edit = edit_ops.move_asset(bm, element, to_space or other, hint)
        room = bm.describe_space(edit["to_space"])
        if edit["to_space"] == edit["from_space"]:
            return f"Move {edit['old_name']} to another spot in {room}."
        return f"Move {edit['old_name']} to {room}; it is then called {edit['new_name']}."
    if action == "add_asset":
        room = to_space or other or element
        if not asset_type or not room:
            raise MapError("add_asset needs asset_type and a room (to_space).")
        edit = edit_ops.add_asset(bm, asset_type, room, hint)
        return f"Add a new {edit['name']} to {bm.describe_space(edit['to_space'])}."
    target = bm.find_element(element)
    if (target in bm.closed) == (action == "close"):
        raise MapError(f"{element_label(bm, target)} is already {'closed' if action == 'close' else 'open'}.")
    bm.set_closed(target, action == "close")
    return f"{'Close' if action == 'close' else 'Reopen'} {element_label(bm, target)}."


def route_effect(before: BuildingMap, after: BuildingMap) -> dict | None:
    """How the most recent route (start to destination, same step-free setting) changes. None before any route."""
    last = before.last_route
    if last is None:
        return None
    ends = (last.start_space_id, last.destination_space_id, last.step_free)
    effect = {
        "route": f"{before.describe_space(last.start_space_id)} to {before.describe_space(last.destination_space_id)}"
    }
    for label, building in (("length_before_m", before), ("length_after_m", after)):
        previous = building.last_route
        try:
            effect[label] = routing.route(building, *ends).length_m
        except MapError:
            effect[label] = None
            effect.setdefault(
                "note", "There is no route " + ("now." if label == "length_before_m" else "after this change.")
            )
        finally:
            building.last_route = previous
    return effect


def compare_normal_length(bm: BuildingMap, route) -> float | None:
    """Length of the same trip without the step-free constraint, to say how much longer the detour is."""
    stops = [route.start_space_id, route.destination_space_id]
    last = bm.last_route
    try:
        normal = routing.route(bm, *stops, False).length_m
    except MapError:
        normal = None
    bm.last_route = last
    return normal


def removal_sentences(bm: BuildingMap, element: str, other: str | None) -> list[str]:
    opening = edit_ops.resolve_opening(bm, element, other)
    if opening["id"] in bm.closed:
        return ["The door is closed already, so routes do not change when it is removed."]
    return analyse(bm, doors_remove=[opening["id"]]).sentences()


def placement_sentences(placement: dict | None, rotation_before: float | None = None) -> list[str]:
    """Plain words for where a hint put the asset, including when the exact spot could not be reached."""
    if not placement:
        return []
    mode, (x, y) = placement["mode"], placement["position"]
    spot = f"({x:g}, {y:g})"
    out = []
    if mode == "anchor":
        word = edit_ops.ANCHOR_WORDS[placement["anchor"]]
        gaps = placement["gaps"]
        if not placement["exact"]:
            out.append(
                f"Could not reach the exact {word}: placed at {spot}, {placement['distance_m']:g} m away from it."
            )
        elif placement["anchor"] == "CENTER":
            out.append("Placed in the centre of the room.")
        elif len(gaps) == 2 and len(set(gaps.values())) == 1:
            out.append(f"Placed in the {word}, {next(iter(gaps.values())):g} m from both walls.")
        elif len(gaps) == 2:
            sides = " and ".join(f"{gap:g} m from the {edit_ops.WALL_WORDS[key]} wall" for key, gap in gaps.items())
            out.append(f"Placed in the {word}, {sides}.")
        else:
            out.append(f"Placed with its back against the {word}, {next(iter(gaps.values())):g} m from it.")
    elif mode == "point":
        px, py = placement["point"]
        if placement["exact"]:
            out.append(f"Placed at the chosen point ({px:g}, {py:g}).")
        else:
            out.append(
                f"Could not use the exact point ({px:g}, {py:g}): placed at {spot}, {placement['distance_m']:g} m away."
            )
    elif mode == "near":
        gap = placement.get("gap_m")
        out.append(f"Placed next to {placement['near']}" + (f", {gap:g} m from it." if gap is not None else "."))
    else:
        out.append(f"Turned in place to {placement['rotation_deg']:g} degrees.")
    out += [f"Note: {note}." for note in placement["notes"]]
    if rotation_before is not None and rotation_before != placement["rotation_deg"] and mode != "rotate":
        out.append(f"Rotation is {placement['rotation_deg']:g} degrees (was {rotation_before:g}).")
    return out


def edit_sentences(bm: BuildingMap, edit: dict) -> list[str]:
    """Plain-words effects of a widening, a move or a new asset, from the edit record of the preview."""
    if edit["action"] == "widen_door":
        door = edit_ops.door_label(bm, bm.openings[edit["id"]])
        return [
            f"{door} is {edit['width_m']} m wide afterwards. Routes stay the same; only wide deliveries are affected."
        ]
    renamed = [
        f"{item['old']} is renamed {item['new']} because the letters change." for item in edit["renamed_siblings"]
    ]
    if edit["action"] == "add_asset":
        return [
            f"New asset {edit['name']} (id {edit['id']}, source generated) is {edit['width_m']} x {edit['depth_m']} m.",
            *renamed,
            f"It stands in {bm.describe_space(edit['to_space'])}.",
            *placement_sentences(edit["placement"]),
        ]
    room = bm.describe_space(edit["to_space"])
    if edit["to_space"] == edit["from_space"]:
        sentences = [f"{edit['new_name']} (id {edit['id']}) stays in {room}."]
    else:
        sentences = [f"{edit['old_name']} becomes {edit['new_name']}; its id {edit['id']} stays.", *renamed]
        sentences.append(f"It now stands in {room}, no longer in {bm.describe_space(edit['from_space'])}.")
    return sentences + placement_sentences(edit.get("placement"), edit.get("old_rotation_deg"))


def undo_label(bm: BuildingMap, action: str, what: str, edit: dict | None) -> str:
    """Short text for the undo card: what taking this change back means."""
    if action == "move_asset" and edit:
        if edit["to_space"] == edit["from_space"]:
            return f"move {edit['new_name']} back to its old spot"
        return f"move {edit['new_name']} back to {bm.spaces[edit['from_space']]['name']}"
    if action == "add_asset" and edit:
        return f"remove the added {edit['name']}"
    if action == "close":
        return what.replace("Close ", "reopen ", 1).rstrip(".")
    if action == "reopen":
        return what.replace("Reopen ", "close ", 1).rstrip(".") + " again"
    return f"take back '{what.rstrip('.')}'"


def check_directions(state: GuideState, bm: BuildingMap) -> None:
    if state.session is None:
        raise ToolError("No directions yet. Call give_directions first.")
    if state.signature != building_signature(bm):
        state.session = None
        raise ToolError("The building changed since these directions (a closure or door). Call give_directions again.")


def make_guide_tools(bm: BuildingMap, output_directory: Path, state: GuideState) -> list:
    @beta_tool
    def give_directions(
        destination: str,
        start: str | None = None,
        step_free: bool = False,
        via: list[str] | None = None,
        guided: bool = False,
        replace_guide: bool = False,
    ) -> str:
        """Directions for a person on foot, for voice. A route of 3 or more steps comes back as an OVERVIEW
        (2 to 4 landmarks, the length and one offer): say the landmarks in one flowing sentence, the length, then
        the offer, nothing more, and wait. A short route comes back as steps: read them out. With guided=true
        (the person said "guide me", "walk me there", "begleite mich", or said yes to the offer) you get only the
        first step: say it and wait. No ids, no lists, no question after a step.

        Args:
            destination: Space id, asset id, or exact room number/name of where they want to go.
            start: Space id, asset id, or exact room number/name of where the person is. Leave it out to start at
                the person's position (see set_position) and say so (start_assumed).
            step_free: True to avoid stairs and steps (wheelchair, pram, trolley, crutches).
            via: Optional places to visit in order before the destination.
            guided: True to start guiding at once (see above).
            replace_guide: True only after the person clearly agreed to drop the route they are being guided on
                (the tool returns needs_confirmation when another destination is being guided).
        """
        if start is None and state.position is None:
            raise ToolError(no_position_error(state))
        old = state.walk if state.walk is not None and state.walk.mode != "plain" else None
        point = None
        try:
            target = bm.resolve_space(destination)
            conflict = walking.guide_conflict(bm, state, target, replace_guide)
            if conflict is not None:
                return as_json(conflict)
            point = exact_start_point(bm, state) if start is None else None
            route = routing.route(
                bm,
                state.position.space_id if start is None else start,
                destination,
                step_free,
                via,
                **({"start_point": point, "start_floor": state.position.floor_id} if point else {}),
            )
            walk = walking.remember_route(bm, state, route, [bm.resolve_space(stop) for stop in via or []])
            state.session = None
            state.signature = building_signature(bm)
        except MapError as error:
            raise ToolError(str(error)) from error
        result = {
            **(
                {
                    "start_assumed": bm.describe_space(route.start_space_id)
                    + (f" ({EXACT_POSITION_NOTE})" if point else "")
                }
                if start is None
                else {}
            ),
            **({"replaced_previous": bm.spaces[old.destination]["name"]} if old and old.destination != target else {}),
            "length_m": route.length_m,
            "step_free": route.step_free,
        }
        if len(walk.steps) < walking.MIN_STEPS_FOR_OVERVIEW:
            result.update({"steps": walk.steps, "steps_remaining": 0})
        else:
            walk.mode = "guided" if guided else "overview"
            if guided:
                walking.set_route_position(bm, state, walk)
            result.update(walking.payload(bm, walk))
        if step_free:
            result["normal_route_length_m"] = compare_normal_length(bm, route)
        return as_json(result)

    def walk_message(said: str) -> dict:
        """One person message while a walk exists; a changed building is folded in first."""
        if state.signature != building_signature(bm):
            if state.walk.mode == "plain":  # all steps were handed out already: they are simply out of date
                state.walk = None
                raise ToolError(
                    "The building changed since these directions (a closure or door). Call give_directions again."
                )
            before = state.walk.left_cache.get(state.walk.index)
            state.signature = building_signature(bm)
            update = walking.after_change(bm, state, before)
            if update and "route_unaffected" not in update:
                return {
                    **update,
                    "note": "The building changed (a closure or door). Say the route changed, then go on.",
                }
        return walking.apply(bm, state, said)

    @beta_tool
    def next_steps() -> str:
        """While guiding: the person says next, done, ok, weiter, "I'm here", "where next" or "und jetzt?" (they
        reached the current stop): returns the next step only. Say a 1 to 3 word acknowledgement ("Good."), then the
        step, no question; on arrived say "You're there. That was the last step." Never repeat the overview.
        Without guiding it hands out the next (at most 3) steps of the current directions ('weiter', 'next')."""
        if state.walk is not None:
            return as_json(walk_message("next"))
        check_directions(state, bm)
        steps = state.session.next()
        return as_json({"steps": steps, "steps_remaining": state.session.remaining(), "done": not steps})

    @beta_tool
    def repeat_steps() -> str:
        """The current step again, when the person says 'nochmal', 'repeat' or 'again'. It never advances.
        Without guiding it repeats the steps handed out last."""
        if state.walk is not None:
            return as_json(walk_message("repeat"))
        check_directions(state, bm)
        return as_json({"steps": state.session.repeat(), "steps_remaining": state.session.remaining()})

    @beta_tool
    def walk(said: str) -> str:
        """Guiding commands, in the person's own words (English or German), copied word for word: yes or "guide
        me" after the offer, back, "how far" or "where am I on the way" (step k of n and metres left), stop,
        overview, "start over", "where do I go again" (say the current step and the destination, no advance).
        Also fine for next, repeat and "I'm here". If the person NAMES a place ("I'm at the lift") call
        set_position instead. The result says what to say; it is short and has no ids.

        Args:
            said: What the person said.
        """
        if state.walk is None:
            raise ToolError("No directions yet. Call give_directions first.")
        return as_json(walk_message(said))

    @beta_tool
    def assume_closed(element: str) -> str:
        """Apply a closure the person STATES as a fact while asking for something else, for example
        "The east lift is closed for maintenance. How do I get from A to B?". It takes effect at once for this
        conversation, with no confirmation, so routes already respect it. Use propose_change instead whenever the
        person asks you to close, reopen or add something ("please close Lift 1", "add a door").

        Args:
            element: Name or id of the lift, staircase, door or room that is closed.
        """
        if names_a_time(state.last_user_text):  # a closure for later cannot be scheduled: never close it now
            if state.knowledge is not None and knowledge_tools.parse_until(state.last_user_text, knowledge_tools.now()):
                return as_json(TIMED_REPLY)
            return as_json(SCHEDULED_REPLY)
        try:
            target = bm.find_element(element)
        except MapError as error:
            raise ToolError(str(error)) from error
        if target not in bm.closed:
            snapshot = edit_ops.take_snapshot(bm, f"reopen {element_label(bm, target)}")
            bm.closed.add(target)
            snapshot.after_signature = building_signature(bm)
            state.undo.append(snapshot)
        bm.closed.add(target)
        state.log.append({"turn": state.turn, "assumed_closed": target})
        return as_json({"closed": element_label(bm, target), "all_closed": sorted(bm.closed)})

    @beta_tool
    def propose_change(
        action: str,
        element: str = "",
        other: str | None = None,
        step_free: bool = True,
        width_m: float | None = None,
        to_space: str | None = None,
        asset_type: str | None = None,
        hint: dict | None = None,
        when: str | None = None,
        until: str | None = None,
        reason: str | None = None,
    ) -> str:
        """Prepare a change to the building and return an understanding card. Changes nothing yet.
        Show the card to the person, wait for their explicit yes in their NEXT message, then call confirm_change.

        Args:
            action: "close" or "reopen" (a lift, staircase, door or room), or "add_door" (between two rooms),
                "remove_door", "widen_door" (a door), "move_asset" (a machine or piece of furniture to another room
                or another spot), "add_asset" (a new machine or piece of furniture) or "undo" (take back the last
                change; needs no other argument).
            element: What to close/reopen, the first room of a new door, the door to remove/widen (id), or the asset
                to move (id or exact name). For add_asset the room (or give to_space). Empty for undo.
            other: The second room (add_door), or for remove_door/widen_door the room on the other side when
                element is a room instead of a door id ("outside" for an entrance).
            step_free: Whether a new door has no step (add_door only).
            width_m: New door width in metres, 0.6 to 5.0 (widen_door only).
            to_space: Target room id, number or name (move_asset, add_asset). Optional for move_asset when hint
                places the asset in the room it is already in, or at a point.
            asset_type: Type of the new asset, such as "cnc_mill" or "printer" (add_asset only).
            hint: Where exactly, for move_asset and add_asset. One of {"anchor": "NW"} (NW NE SW SE N S E W center;
                a corner or a wall, back against the wall), {"near": "<room or asset>"} or {"point": [x, y]}
                (metres, inside the room), plus optional {"rotation_deg": n}.
            when: Any time the person named for the change ("tomorrow", "from Monday", "next week", "morgen", "ab
                Montag"). Scheduling does not exist: pass it and nothing is changed or proposed. Not for now, today, jetzt or heute.
            until: close only: the end the person named for a closure that starts now ('until tomorrow', 'bis 14
                Uhr', 'for two hours'). The closure then ends by itself; the card says until when.
            reason: close only: why, in a few words ('broken', 'maintenance').
        """
        timed = None
        if action == "close" and state.knowledge is not None:  # place knowledge: 'out until tomorrow' is allowed
            timed = knowledge_tools.closure_time(state.last_user_text, until, when, knowledge_tools.now())
            if timed.scheduled:
                state.pending = None
                return as_json(SCHEDULED_REPLY)
            if timed.unclear:
                state.pending = None
                return as_json({"needs_time": True, "question": knowledge_tools.ASK_UNTIL, "changed": False})
        elif when_is_later(when) or names_a_time(state.last_user_text):  # decided on the person's own words too
            state.pending = None
            return as_json(SCHEDULED_REPLY)
        if action not in ACTIONS:
            raise ToolError(f"action must be one of {ACTIONS}.")
        if action in KNOWLEDGE_ACTIONS:
            raise ToolError("Call remember_here or resolve_here for this; they make the card.")
        if state.pending is not None and state.pending.turn == state.turn:
            raise ToolError("One proposal per message. Show the card you already made and wait for the answer.")
        state.pending = None
        if action == "undo":
            return undo_card()
        if not element and not (action == "add_asset" and (to_space or other)):
            raise ToolError("element is needed for this action.")
        preview = copy.deepcopy(bm)
        try:
            what = apply_change(preview, action, element, other, step_free, width_m, to_space, asset_type, hint)
        except MapError as error:
            raise ToolError(str(error)) from error
        card = {
            "I understood": what,
            "effect on your last route": route_effect(bm, preview),
            "status": "nothing changed yet, waiting for the person's yes",
        }
        if action in ("close", "reopen"):
            effect_key = "closed_add" if action == "close" else "closed_remove"
            try:
                card["effect on the whole building"] = analyse(bm, **{effect_key: [element]}).sentences()
            except (MapError, KeyError, ValueError, nx.NetworkXException):
                pass  # the card still works without the building-wide sentences
        if action == "remove_door":
            card["effect on the whole building"] = removal_sentences(bm, element, other)
        elif action in ("widen_door", "move_asset", "add_asset"):
            card["effect on the whole building"] = edit_sentences(bm, preview.last_edit)
        extra = None
        if timed is not None and timed.at is not None:
            until_text = knowledge_tools.until_words(timed.at, knowledge_tools.now())
            card["I understood"] = f"{what.rstrip('.')} {until_text}" + (f" ({reason.strip()})." if reason else ".")
            card["until"] = until_text
            card["after that"] = "It opens again by itself."
            extra = {"until": timed.at, "reason": reason}
        state.pending = Pending(
            action,
            element,
            other,
            step_free,
            card,
            state.turn,
            building_signature(bm),
            width_m,
            to_space,
            asset_type,
            hint,
            extra,
        )
        return as_json(card)

    def check_undo_is_safe(snapshot) -> None:
        """Undo restores a whole earlier state: refuse if anything else changed since (for example on the page)."""
        if snapshot.after_signature is not None and snapshot.after_signature != building_signature(bm):
            state.undo.clear()
            raise ToolError(
                "The building was changed in another way since that edit (for example on the plan page), so undoing "
                "it would also erase those changes. I cleared the undo history. Tell me what to change back."
            )

    def undo_card() -> str:
        if not state.undo:
            raise ToolError("There is nothing to undo.")
        snapshot = state.undo[-1]
        check_undo_is_safe(snapshot)
        knowledge_tools.undo_fact(bm, state, snapshot)  # a stored note only within two minutes
        preview = copy.deepcopy(bm)
        edit_ops.restore_snapshot(preview, snapshot)
        card = {
            "I understood": f"Undo: {snapshot.label}.",
            "effect on your last route": route_effect(bm, preview),
            "effect on the whole building": [
                f"This takes back the most recent change: {snapshot.label}.",
                f"{len(state.undo) - 1} earlier change(s) could still be undone afterwards.",
            ],
            "status": "nothing changed yet, waiting for the person's yes",
        }
        state.pending = Pending("undo", "", None, True, card, state.turn, building_signature(bm))
        return as_json(card)

    @beta_tool
    def confirm_change(confirmed: bool, user_reply: str) -> str:
        """Apply (confirmed=true) or drop (confirmed=false) the change from propose_change.
        Only call this after the person answered the card in a new message.

        Args:
            confirmed: True only if the person clearly said yes to the card.
            user_reply: The person's answer to the card, copied word for word from their last message.
        """
        pending = state.pending
        if pending is None:
            raise ToolError("Nothing to confirm. Call propose_change first.")
        if state.turn == pending.turn:
            raise ToolError("Ask the person first: show the card and wait for their answer in a new message.")
        state.pending = None
        if pending.signature != building_signature(bm):
            raise ToolError("The building changed since this card was made. Call propose_change again.")
        left_before = walking.left_now(bm, state)
        closure_until = None
        if confirmed and (not YES.search(user_reply) or NO.search(user_reply)):
            raise ToolError("That reply is not a clear yes. Ask the person again, then call propose_change anew.")
        if not confirmed:
            return as_json({"applied": False, "note": "Dropped, nothing changed."})
        if pending.action == "undo":
            if not state.undo:
                raise ToolError("There is nothing to undo.")
            check_undo_is_safe(state.undo[-1])
            knowledge_tools.undo_fact(bm, state, state.undo[-1])
            snapshot = state.undo.pop()
            edit_ops.restore_snapshot(bm, snapshot)
            knowledge_tools.undo_fact_apply(bm, state, snapshot)
            state.session = None
            state.signature = building_signature(bm)
            what = f"Undone: {snapshot.label}."
        elif pending.action in KNOWLEDGE_ACTIONS:
            snapshot = edit_ops.take_snapshot(bm)
            stored = knowledge_tools.apply_pending(bm, state, pending)
            if pending.action == "remember" and state.last_fact:  # 'undo that' takes the note back (2 minutes)
                snapshot.label = f"remove the note '{pending.extra['text']}'"
                snapshot.fact_at = state.last_fact["at"]
                snapshot.after_signature = building_signature(bm)
                state.undo.append(snapshot)
            state.log.append({"turn": state.turn, "fact": pending.action})
            return as_json({"applied": True, **stored})
        else:
            snapshot = edit_ops.take_snapshot(bm)
            try:
                what = apply_change(
                    bm,
                    pending.action,
                    pending.element,
                    pending.other,
                    pending.step_free,
                    pending.width_m,
                    pending.to_space,
                    pending.asset_type,
                    pending.hint,
                )
            except MapError as error:
                raise ToolError(str(error)) from error
            edit = bm.last_edit if pending.action in ("move_asset", "add_asset") else None
            snapshot.label = undo_label(bm, pending.action, what, edit)
            snapshot.after_signature = building_signature(bm)
            state.undo.append(snapshot)
            timed = (pending.extra or {}).get("until") if pending.action == "close" else None
            if timed is not None:  # the closure ends by itself: stored as a closure fact with valid_to
                target = bm.find_element(pending.element)
                fact = knowledge_tools.store_closure(bm, state, target, timed, pending.extra.get("reason"))
                snapshot.fact_at = state.last_fact["at"] if state.last_fact else None
                what = f"{what.rstrip('.')} {knowledge_tools.until_words(timed, knowledge_tools.now())}."
                closure_until = fact.get("valid_to")
            if pending.action == "reopen":
                knowledge_tools.end_closures(bm, state, bm.find_element(pending.element))
        output_directory.mkdir(parents=True, exist_ok=True)
        bm.save(output_directory / "building_edited.json")
        state.log.append({"turn": state.turn, "change": what})
        update = walking.after_change(bm, state, left_before)
        if update is not None:  # the walk now describes the changed building
            state.signature = building_signature(bm)
        return as_json(
            {
                "applied": True,
                "change": what,
                "effect": pending.card["effect on your last route"],
                "all_closed": sorted(bm.closed),
                **({"walk_update": update} if update else {}),
                **({"closed_until": str(closure_until)} if closure_until else {}),
            }
        )

    return [give_directions, next_steps, repeat_steps, walk, assume_closed, propose_change, confirm_change]
