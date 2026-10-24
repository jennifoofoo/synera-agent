"""Level 3, conversation tools for a campus: routes across buildings, connecting buildings, closing links.

Changes to the campus (a new link, a closed link) use the same rule as confirm_change: a card first, a clear yes in
the NEXT message, then the change. The campus has its own pending slot (`CampusHolder.pending`) and its own confirm
tool, so the building edits of guide_tools stay untouched; the turn counter is the one of GuideState."""

import math
from dataclasses import dataclass, field
from pathlib import Path

from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent.campus import (
    LINK_KINDS,
    Campus,
    Link,
    entrances,
    estimate_missing_lengths,
    save_campus,
    validate_campus,
)
from building_agent.campus_routing import AmbiguousReference, CampusRouter, entrance_labels
from building_agent.directions import DirectionsSession
from building_agent.guide_tools import NO, YES, GuideState, building_signature
from starter_agent.building_map import BuildingMap, MapError
from starter_agent.tools import as_json

WAITING = "nothing changed yet, waiting for the person's yes"
SIDES = ("north", "south", "east", "west")


@dataclass
class CampusPending:
    action: str  # "connect_buildings" or "close_link"
    turn: int
    card: dict
    signature: tuple
    link: Link | None = None  # connect_buildings: the new link
    link_id: str = ""  # close_link
    closed: bool = True


@dataclass
class CampusHolder:
    """The campus of the session. `bm` is the agent's active map (it should be one of `maps`), used to keep
    next_steps working for directions that start here. `path` is where campus.json is saved."""

    campus: Campus
    maps: dict[str, BuildingMap | None]
    path: Path | None = None
    bm: BuildingMap | None = None
    pending: CampusPending | None = None
    router: CampusRouter = field(init=False)

    def __post_init__(self) -> None:
        self.router = CampusRouter(self.campus, self.maps)


def campus_signature(holder: CampusHolder) -> tuple:
    return tuple(
        (link.id, link.closed, link.length_m, link.step_free, link.from_entrance, link.to_entrance)
        for link in holder.campus.links
    )


def next_link_id(campus: Campus) -> str:
    used = {link.id for link in campus.links}
    return next(f"L{number}" for number in range(1, len(used) + 2) if f"L{number}" not in used)


def find_link(campus: Campus, reference: str) -> Link:
    wanted = str(reference).strip().lower()
    for link in campus.links:
        if wanted in (link.id.lower(), link.name.lower()):
            return link
    close = [link for link in campus.links if wanted and wanted in link.name.lower()]
    if len(close) == 1:
        return close[0]
    options = ", ".join(f"{link.id} ({link.name or link.kind})" for link in campus.links) or "there are no links yet"
    raise ToolError(f"No link matches '{reference}'. Links: {options}.")


def pick_entrance(router: CampusRouter, building_id: str, text: str) -> dict:
    """An entrance by id, room name, side ('east') or, if the building has only one, by nothing."""
    bm = router._map(building_id)
    found = entrances(bm)
    labels = entrance_labels(bm)
    lowered = str(text or "").strip().lower()
    if len(found) == 1 and (not lowered or lowered in ("main", "main entrance", "entrance")):
        return found[0]
    matches = [item for item in found if lowered and lowered == item["id"].lower()]
    if not matches and lowered:
        matches = [item for item in found if lowered == item["room"].lower()]
    if not matches and lowered:
        side = next((word for word in SIDES if word in lowered), "")
        matches = [item for item in found if side and labels[item["id"]].startswith(side)]
    if not matches and lowered:
        matches = [item for item in found if lowered in item["room"].lower()]
    if len(matches) == 1:
        return matches[0]
    options = "; ".join(
        f"{item['id']} ({labels[item['id']]}, room {item['room']}, {'step-free' if item['step_free'] else 'has steps'})"
        for item in found
    )
    raise ToolError(
        f"Which entrance of {router.building_name(building_id)}? Ask the person. Entrances: {options or 'none'}."
    )


def make_campus_tools(holder: CampusHolder, output_directory: Path, state: GuideState) -> list:
    router = holder.router

    def stop(value: str, building: str | None) -> tuple[str, str] | str:
        return (value, building) if building else value

    def guard_new_card() -> None:
        if holder.pending is not None and holder.pending.turn == state.turn:
            raise ToolError("One proposal per message. Show the card you already made and wait for the answer.")
        if state.pending is not None and state.pending.turn == state.turn:
            raise ToolError("One proposal per message. Show the card you already made and wait for the answer.")
        holder.pending = None

    @beta_tool
    def list_buildings() -> str:
        """The buildings of the campus with floors, entrances and the links between them."""
        listing = []
        for item in holder.campus.buildings:
            bm = holder.maps.get(item.building_id)
            labels = entrance_labels(bm) if bm else {}
            listing.append(
                {
                    "building_id": item.building_id,
                    "name": router.building_name(item.building_id),
                    "map_loaded": bm is not None,
                    "floors": len(bm.floors) if bm else None,
                    "entrances": [
                        {"id": e["id"], "side": labels[e["id"]], "room": e["room"], "step_free": e["step_free"]}
                        for e in (entrances(bm) if bm else [])
                    ],
                }
            )
        links = [
            {
                "id": link.id,
                "kind": link.kind,
                "name": link.name,
                "between": [router.building_name(link.from_building), router.building_name(link.to_building)],
                "length_m": link.length_m,
                "step_free": link.step_free,
                "closed": link.closed,
            }
            for link in holder.campus.links
        ]
        return as_json({"campus": holder.campus.name, "buildings": listing, "links": links})

    @beta_tool
    def campus_route(
        start: str,
        destination: str,
        start_building: str | None = None,
        destination_building: str | None = None,
        step_free: bool = False,
        via: list[str] | None = None,
    ) -> str:
        """Route and directions between places that may be in DIFFERENT buildings of the campus (use this
        whenever the person names another building). Returns the first (at most 3) steps; the person asks for the
        rest with next_steps. If a name exists in several buildings the tool lists them: ask which building.
        If there is no link between the buildings, say so and offer connect_buildings, never invent a link.

        Args:
            start: Room id, number or name where the person is.
            destination: Room id, number or name where they want to go.
            start_building: Building (name or id) of the start, if the person said it.
            destination_building: Building (name or id) of the destination, if the person said it.
            step_free: True to avoid stairs and steps (wheelchair, pram, trolley), also on links and entrances.
            via: Optional places to visit in order before the destination.
        """
        try:
            route = router.route(stop(start, start_building), stop(destination, destination_building), step_free, via)
        except AmbiguousReference as error:
            raise ToolError(f"{error} Candidates: {as_json(error.candidates)}") from error
        except MapError as error:
            hint = " Offer to connect them with connect_buildings." if "no link" in str(error).lower() else ""
            raise ToolError(f"{error}{hint}") from error
        state.session = DirectionsSession(route.steps)
        state.signature = building_signature(holder.bm) if holder.bm is not None else ()
        result = {
            "length_m": route.length_m,
            "step_free": route.step_free,
            "buildings": [router.building_name(item) for item in route.buildings],
            "links_used": [f"{link.kind} {link.id} ({link.name})" for link in route.links],
            "steps": state.session.next(),
            "steps_remaining": state.session.remaining(),
        }
        if step_free:
            try:
                result["normal_route_length_m"] = router.route(
                    stop(start, start_building), stop(destination, destination_building), False, via
                ).length_m
            except MapError:
                result["normal_route_length_m"] = None
        return as_json(result)

    @beta_tool
    def link_what_changes(link_id: str, closed: bool = True) -> str:
        """What changes for the campus if a link (walkway, bridge, tunnel) is closed or reopened: which pairs of
        buildings lose or regain their connection. Read-only, use it for 'what if the walkway is closed'.

        Args:
            link_id: Link id (such as L1) or its name.
            closed: True to ask about closing it, False about reopening it.
        """
        link = find_link(holder.campus, link_id)
        return as_json({"link": link.id, "effect": router.link_effect(link, closed)})

    @beta_tool
    def connect_buildings(
        first_building: str,
        first_entrance: str,
        second_building: str,
        second_entrance: str,
        kind: str = "walkway",
        length_m: float | None = None,
        width_m: float | None = None,
        step_free: bool = True,
    ) -> str:
        """Propose a new link between two buildings and return an understanding card. Changes nothing yet.
        Show the card, wait for the person's explicit yes in their NEXT message, then call confirm_campus_change.

        Args:
            first_building: Name or id of the first building.
            first_entrance: Entrance of the first building: its id, the room behind it, or a side such as 'east'.
                Empty if the building has only one entrance. If unclear the tool lists them: ask the person.
            second_building: Name or id of the second building.
            second_entrance: Entrance of the second building, like first_entrance.
            kind: "walkway", "bridge" or "tunnel".
            length_m: Length of the link in metres if the person knows it; otherwise it is estimated.
            width_m: Width in metres, optional.
            step_free: Whether the link has no steps.
        """
        guard_new_card()
        if kind not in LINK_KINDS:
            raise ToolError(f"kind must be one of {', '.join(LINK_KINDS)}.")
        try:
            first_b, second_b = router.find_building(first_building), router.find_building(second_building)
            if first_b == second_b:
                raise ToolError("A link joins two different buildings.")
            first_e, second_e = (
                pick_entrance(router, first_b, first_entrance),
                pick_entrance(router, second_b, second_entrance),
            )
        except MapError as error:
            raise ToolError(str(error)) from error
        if length_m is not None and not (math.isfinite(length_m) and length_m > 0):
            raise ToolError("The length must be a number of metres above 0.")
        link = Link(
            id=next_link_id(holder.campus),
            kind=kind,
            name=f"New {kind}",
            from_building=first_b,
            from_entrance=first_e["id"],
            to_building=second_b,
            to_entrance=second_e["id"],
            length_m=float(length_m) if length_m is not None else None,
            width_m=width_m,
            step_free=bool(step_free),
        )
        if any(
            {(item.from_building, item.from_entrance), (item.to_building, item.to_entrance)}
            == {(first_b, first_e["id"]), (second_b, second_e["id"])}
            for item in holder.campus.links
        ):
            raise ToolError("These two entrances are already joined by a link.")
        if link.length_m is None:
            estimate_missing_lengths(Campus("tmp", "tmp", holder.campus.buildings, [link]), holder.maps)
        if link.length_m is None:
            raise ToolError(
                "I cannot estimate the distance because the building positions are unknown. Ask the person how long "
                "the link is in metres, then call connect_buildings again with length_m."
            )
        before = router.connected_pairs()
        after = router.connected_pairs([*holder.campus.links, link])
        gained = sorted(tuple(sorted(pair)) for pair in after - before)
        names = (router.building_name(first_b), router.building_name(second_b))
        labels = (
            entrance_labels(router._map(first_b))[first_e["id"]],
            entrance_labels(router._map(second_b))[second_e["id"]],
        )
        notes = []
        for building_name, entrance in zip(names, (first_e, second_e), strict=True):
            if step_free and not entrance["step_free"]:
                notes.append(
                    f"The entrance by {entrance['room']} in {building_name} has steps, so step-free routes cannot use this link."
                )
        card = {
            "I understood": f"A {kind} of {link.length_m:g} m from the {labels[0]} of {names[0]} (room {first_e['room']}) "
            f"to the {labels[1]} of {names[1]} (room {second_e['room']}), "
            f"{'step-free' if step_free else 'with steps'}.",
            "length": (
                f"{link.length_m:g} m, as the person said."
                if not link.length_estimated
                else f"about {link.length_m:g} m, an estimate: straight line between the two entrances times 1.2. "
                "Ask if they know the real length."
            ),
            "effect on the campus": [
                f"{router.building_name(a)} and {router.building_name(b)} become connected." for a, b in gained
            ]
            or [f"{names[0]} and {names[1]} are connected already; this adds a second way."],
            "effect on routes": (
                "Routes between these buildings become possible."
                if gained
                else "Routes between them can get shorter if this link is the better way."
            ),
            "notes": notes,
            "status": WAITING,
        }
        holder.pending = CampusPending("connect_buildings", state.turn, card, campus_signature(holder), link=link)
        return as_json(card)

    @beta_tool
    def close_link(link_id: str, closed: bool = True) -> str:
        """Propose closing (or reopening) a link between buildings and return a card. Changes nothing yet.
        Show the card, wait for the person's explicit yes in their NEXT message, then call confirm_campus_change.
        For a plain 'what changes if' question use link_what_changes instead.

        Args:
            link_id: Link id (such as L1) or its name.
            closed: True to close the link, False to reopen it.
        """
        guard_new_card()
        link = find_link(holder.campus, link_id)
        if link.closed == closed:
            raise ToolError(f"The {link.kind} {link.id} is already {'closed' if closed else 'open'}.")
        card = {
            "I understood": f"{'Close' if closed else 'Reopen'} the {link.kind} {link.id}"
            + (f" ({link.name})" if link.name else "")
            + f" between {router.building_name(link.from_building)} and {router.building_name(link.to_building)}.",
            "effect on the campus": router.link_effect(link, closed),
            "status": WAITING,
        }
        holder.pending = CampusPending(
            "close_link", state.turn, card, campus_signature(holder), link_id=link.id, closed=closed
        )
        return as_json(card)

    @beta_tool
    def confirm_campus_change(confirmed: bool, user_reply: str) -> str:
        """Apply (confirmed=true) or drop (confirmed=false) the change from connect_buildings or close_link.
        Only call this after the person answered the card in a new message.

        Args:
            confirmed: True only if the person clearly said yes to the card.
            user_reply: The person's answer to the card, copied word for word from their last message.
        """
        pending = holder.pending
        if pending is None:
            raise ToolError("Nothing to confirm. Call connect_buildings or close_link first.")
        if state.turn == pending.turn:
            raise ToolError("Ask the person first: show the card and wait for their answer in a new message.")
        holder.pending = None
        if state.turn > pending.turn + 1:
            raise ToolError("That card is out of date. Call connect_buildings or close_link again.")
        if pending.signature != campus_signature(holder):
            raise ToolError("The campus changed since this card was made. Propose the change again.")
        if confirmed and (not YES.search(user_reply) or NO.search(user_reply)):
            raise ToolError("That reply is not a clear yes. Ask the person again, then propose the change anew.")
        if not confirmed:
            return as_json({"applied": False, "note": "Dropped, nothing changed."})
        if pending.action == "connect_buildings":
            holder.campus.links.append(pending.link)
            problems = [item for item in validate_campus(holder.campus, holder.maps) if item.level == "error"]
            if problems:
                holder.campus.links.remove(pending.link)
                raise ToolError(f"The link is not valid: {problems[0].message}")
            what = f"Added {pending.link.kind} {pending.link.id} ({pending.link.length_m:g} m)."
        else:
            link = find_link(holder.campus, pending.link_id)
            link.closed = pending.closed
            what = f"{'Closed' if pending.closed else 'Reopened'} {link.kind} {link.id}."
        path = holder.path or output_directory / "campus.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        save_campus(holder.campus, path)
        state.session = None
        state.log.append({"turn": state.turn, "campus_change": what})
        return as_json({"applied": True, "change": what, "effect": pending.card["effect on the campus"]})

    return [list_buildings, campus_route, link_what_changes, connect_buildings, close_link, confirm_campus_change]
