"""Conversation tools: hands-free directions in small chunks and edits that need a confirmed understanding card."""

import copy
from dataclasses import dataclass, field
from pathlib import Path

from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent.directions import DirectionsSession
from starter_agent.building_map import BuildingMap, MapError
from starter_agent.tools import as_json

ACTIONS = ("close", "reopen", "add_door")


@dataclass
class Pending:
    action: str
    element: str
    other: str | None
    step_free: bool
    card: dict
    turn: int


@dataclass
class GuideState:
    """Per-conversation state. `turn` counts user messages so a change cannot be proposed and confirmed in one."""

    session: DirectionsSession | None = None
    pending: Pending | None = None
    turn: int = 0
    log: list[dict] = field(default_factory=list)

    def begin_turn(self) -> None:
        self.turn += 1


def apply_change(bm: BuildingMap, action: str, element: str, other: str | None, step_free: bool) -> str:
    """Apply one edit to `bm`; returns a one-line description. Raises MapError if it cannot be done."""
    if action == "add_door":
        if not other:
            raise MapError("add_door needs two rooms: element and other.")
        opening = bm.add_door(element, other, step_free)
        first, second = (bm.describe_space(space_id) for space_id in opening["space_ids"])
        return f"New {'step-free ' if step_free else ''}door between {first} and {second}."
    target = bm.set_closed(element, action == "close")
    return f"{'Close' if action == 'close' else 'Reopen'} {target}."


def route_effect(before: BuildingMap, after: BuildingMap) -> dict | None:
    """How the most recent route changes if the edit is applied. None if nobody asked for a route yet."""
    last = before.last_route
    if last is None:
        return None
    effect = {"route": f"{before.describe_space(last.start_space_id)} to {before.describe_space(last.destination_space_id)}",
              "length_before_m": last.length_m}
    try:
        effect["length_after_m"] = after.route(last.start_space_id, last.destination_space_id, last.step_free).length_m
    except MapError:
        effect["length_after_m"] = None
        effect["note"] = "No route any more after this change."
    return effect


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
            route = bm.route(start, destination, step_free, via)
            state.session = DirectionsSession.from_route(bm, route)
        except MapError as error:
            raise ToolError(str(error)) from error
        return as_json({"length_m": route.length_m, "step_free": route.step_free, "steps": state.session.next(),
                        "steps_remaining": state.session.remaining()})

    @beta_tool
    def next_steps() -> str:
        """The next (at most 3) steps of the current directions, when the person says 'weiter' or 'next'."""
        if state.session is None:
            raise ToolError("No directions yet. Call give_directions first.")
        steps = state.session.next()
        return as_json({"steps": steps, "steps_remaining": state.session.remaining(), "done": not steps})

    @beta_tool
    def repeat_steps() -> str:
        """The steps handed out last, again, when the person says 'nochmal' or 'repeat'."""
        if state.session is None:
            raise ToolError("No directions yet. Call give_directions first.")
        return as_json({"steps": state.session.repeat(), "steps_remaining": state.session.remaining()})

    @beta_tool
    def propose_change(action: str, element: str, other: str | None = None, step_free: bool = True) -> str:
        """Prepare a change to the building and return an understanding card. Changes nothing yet.
        Show the card to the person, wait for their explicit yes in their NEXT message, then call confirm_change.

        Args:
            action: "close" or "reopen" (a lift, staircase, door or room), or "add_door" (between two rooms).
            element: What to close/reopen, or the first room of a new door (id, number or name).
            other: The second room, only for add_door.
            step_free: Whether a new door has no step (add_door only).
        """
        if action not in ACTIONS:
            raise ToolError(f"action must be one of {ACTIONS}.")
        preview = copy.deepcopy(bm)
        try:
            what = apply_change(preview, action, element, other, step_free)
        except MapError as error:
            raise ToolError(str(error)) from error
        card = {"I understood": what, "effect on your last route": route_effect(bm, preview),
                "status": "nothing changed yet, waiting for the person's yes"}
        state.pending = Pending(action, element, other, step_free, card, state.turn)
        return as_json(card)

    @beta_tool
    def confirm_change(confirmed: bool) -> str:
        """Apply (confirmed=true) or drop (confirmed=false) the change from propose_change.
        Only call this after the person answered the card in a new message.

        Args:
            confirmed: True only if the person clearly said yes to the card.
        """
        pending = state.pending
        if pending is None:
            raise ToolError("Nothing to confirm. Call propose_change first.")
        if state.turn == pending.turn:
            raise ToolError("Ask the person first: show the card and wait for their answer in a new message.")
        state.pending = None
        if not confirmed:
            return as_json({"applied": False, "note": "Dropped, nothing changed."})
        try:
            what = apply_change(bm, pending.action, pending.element, pending.other, pending.step_free)
        except MapError as error:
            raise ToolError(str(error)) from error
        if pending.action == "add_door":
            bm.save(output_directory / "building_edited.json")
        state.log.append({"turn": state.turn, "change": what})
        return as_json({"applied": True, "change": what, "effect": pending.card["effect on your last route"],
                        "all_closed": sorted(bm.closed)})

    return [give_directions, next_steps, repeat_steps, propose_change, confirm_change]
