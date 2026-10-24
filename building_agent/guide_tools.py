"""Conversation tools: hands-free directions in small chunks and edits that need a confirmed understanding card."""

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent import edit_ops, routing
from building_agent.directions import DirectionsSession
from building_agent.impact import analyse
from starter_agent.building_map import BuildingMap, MapError
from starter_agent.tools import as_json

ACTIONS = ("close", "reopen", "add_door", "remove_door", "widen_door", "move_asset")
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


@dataclass
class GuideState:
    """Per-conversation state. `turn` counts user messages so a change cannot be proposed and confirmed in one."""

    session: DirectionsSession | None = None
    pending: Pending | None = None
    turn: int = 0
    signature: tuple = ()
    log: list[dict] = field(default_factory=list)

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
    assets = hash(tuple(sorted((a["id"], a["space_id"], tuple(a["position"])) for a in bm.assets.values())))
    return (tuple(sorted(bm.closed)), len(bm.openings), openings, assets)


def apply_change(
    bm: BuildingMap,
    action: str,
    element: str,
    other: str | None,
    step_free: bool,
    width_m: float | None = None,
    to_space: str | None = None,
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
        edit = edit_ops.move_asset(bm, element, to_space or other or "")
        return (
            f"Move {edit['old_name']} to {bm.describe_space(edit['to_space'])}; it is then called {edit['new_name']}."
        )
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


def edit_sentences(bm: BuildingMap, edit: dict) -> list[str]:
    """Plain-words effects of a widening or a move, from the edit record of the preview."""
    if edit["action"] == "widen_door":
        door = edit_ops.door_label(bm, bm.openings[edit["id"]])
        return [
            f"{door} is {edit['width_m']} m wide afterwards. Routes stay the same; only wide deliveries are affected."
        ]
    sentences = [f"{edit['old_name']} becomes {edit['new_name']}; its id {edit['id']} stays."]
    sentences += [
        f"{item['old']} is renamed {item['new']} because the letters change." for item in edit["renamed_siblings"]
    ]
    sentences.append(
        f"It now stands in {bm.describe_space(edit['to_space'])}, no longer in {bm.describe_space(edit['from_space'])}."
    )
    return sentences


def check_directions(state: GuideState, bm: BuildingMap) -> None:
    if state.session is None:
        raise ToolError("No directions yet. Call give_directions first.")
    if state.signature != building_signature(bm):
        state.session = None
        raise ToolError("The building changed since these directions (a closure or door). Call give_directions again.")


def make_guide_tools(bm: BuildingMap, output_directory: Path, state: GuideState) -> list:
    @beta_tool
    def give_directions(start: str, destination: str, step_free: bool = False, via: list[str] | None = None) -> str:
        """Directions for a person on foot, with landmarks, handed out in chunks of at most 3 steps.
        Read out only the steps returned; the person asks for the rest with next_steps.

        Args:
            start: Space id, asset id, or exact room number/name of where the person is.
            destination: Space id, asset id, or exact room number/name of where they want to go.
            step_free: True to avoid stairs and steps (wheelchair, pram, trolley, crutches).
            via: Optional places to visit in order before the destination.
        """
        try:
            route = routing.route(bm, start, destination, step_free, via)
            state.session = DirectionsSession.from_route(bm, route)
            state.signature = building_signature(bm)
        except MapError as error:
            raise ToolError(str(error)) from error
        result = {
            "length_m": route.length_m,
            "step_free": route.step_free,
            "steps": state.session.next(),
            "steps_remaining": state.session.remaining(),
        }
        if step_free:
            result["normal_route_length_m"] = compare_normal_length(bm, route)
        return as_json(result)

    @beta_tool
    def next_steps() -> str:
        """The next (at most 3) steps of the current directions, when the person says 'weiter' or 'next'."""
        check_directions(state, bm)
        steps = state.session.next()
        return as_json({"steps": steps, "steps_remaining": state.session.remaining(), "done": not steps})

    @beta_tool
    def repeat_steps() -> str:
        """The steps handed out last, again, when the person says 'nochmal' or 'repeat'."""
        check_directions(state, bm)
        return as_json({"steps": state.session.repeat(), "steps_remaining": state.session.remaining()})

    @beta_tool
    def assume_closed(element: str) -> str:
        """Apply a closure the person STATES as a fact while asking for something else, for example
        "The east lift is closed for maintenance. How do I get from A to B?". It takes effect at once for this
        conversation, with no confirmation, so routes already respect it. Use propose_change instead whenever the
        person asks you to close, reopen or add something ("please close Lift 1", "add a door").

        Args:
            element: Name or id of the lift, staircase, door or room that is closed.
        """
        try:
            target = bm.find_element(element)
        except MapError as error:
            raise ToolError(str(error)) from error
        bm.closed.add(target)
        state.log.append({"turn": state.turn, "assumed_closed": target})
        return as_json({"closed": element_label(bm, target), "all_closed": sorted(bm.closed)})

    @beta_tool
    def propose_change(
        action: str,
        element: str,
        other: str | None = None,
        step_free: bool = True,
        width_m: float | None = None,
        to_space: str | None = None,
    ) -> str:
        """Prepare a change to the building and return an understanding card. Changes nothing yet.
        Show the card to the person, wait for their explicit yes in their NEXT message, then call confirm_change.

        Args:
            action: "close" or "reopen" (a lift, staircase, door or room), or "add_door" (between two rooms),
                "remove_door", "widen_door" (a door) or "move_asset" (a machine or piece of furniture to another room).
            element: What to close/reopen, the first room of a new door, the door to remove/widen (id), or the asset
                to move (id or exact name).
            other: The second room (add_door), or for remove_door/widen_door the room on the other side when
                element is a room instead of a door id ("outside" for an entrance).
            step_free: Whether a new door has no step (add_door only).
            width_m: New door width in metres, 0.6 to 5.0 (widen_door only).
            to_space: Target room id, number or name (move_asset only).
        """
        if action not in ACTIONS:
            raise ToolError(f"action must be one of {ACTIONS}.")
        if state.pending is not None and state.pending.turn == state.turn:
            raise ToolError("One proposal per message. Show the card you already made and wait for the answer.")
        state.pending = None
        preview = copy.deepcopy(bm)
        try:
            what = apply_change(preview, action, element, other, step_free, width_m, to_space)
        except MapError as error:
            raise ToolError(str(error)) from error
        card = {
            "I understood": what,
            "effect on your last route": route_effect(bm, preview),
            "status": "nothing changed yet, waiting for the person's yes",
        }
        if action in ("close", "reopen"):
            effect_key = "closed_add" if action == "close" else "closed_remove"
            card["effect on the whole building"] = analyse(bm, **{effect_key: [element]}).sentences()
        if action == "remove_door":
            card["effect on the whole building"] = removal_sentences(bm, element, other)
        elif action in ("widen_door", "move_asset"):
            card["effect on the whole building"] = edit_sentences(bm, preview.last_edit)
        state.pending = Pending(
            action, element, other, step_free, card, state.turn, building_signature(bm), width_m, to_space
        )
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
        if confirmed and (not YES.search(user_reply) or NO.search(user_reply)):
            raise ToolError("That reply is not a clear yes. Ask the person again, then call propose_change anew.")
        if not confirmed:
            return as_json({"applied": False, "note": "Dropped, nothing changed."})
        try:
            what = apply_change(
                bm,
                pending.action,
                pending.element,
                pending.other,
                pending.step_free,
                pending.width_m,
                pending.to_space,
            )
        except MapError as error:
            raise ToolError(str(error)) from error
        output_directory.mkdir(parents=True, exist_ok=True)
        bm.save(output_directory / "building_edited.json")
        state.log.append({"turn": state.turn, "change": what})
        return as_json(
            {
                "applied": True,
                "change": what,
                "effect": pending.card["effect on your last route"],
                "all_closed": sorted(bm.closed),
            }
        )

    return [give_directions, next_steps, repeat_steps, assume_closed, propose_change, confirm_change]
