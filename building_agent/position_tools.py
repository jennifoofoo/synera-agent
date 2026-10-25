"""set_position, get_position and find_nearest: "you are here" for the conversation.

The position lives on the conversation state (GuideState.position). Only these tools and the page's validated
click context set it, never a sentence in the user message. A wrong position can only skew a route, so the agent
always says what it assumed."""

from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent import routing
from building_agent import walk as walking
from building_agent.find_space import find_space
from building_agent.find_tools import find_asset, words_of
from building_agent.position import (
    EXACT_POSITION_NOTE,
    MAX_OPTIONS,
    describe_position,
    exact_start_point,
    lengths_from,
    make_position,
    nearest,
    no_position_error,
    position_note,
)
from starter_agent.building_map import BuildingMap, MapError
from starter_agent.tools import as_json


def distance_annotator(bm: BuildingMap, state):
    """Adds route_m_from_you to groups ({space_id, ...}) when a position is set; otherwise does nothing."""

    def annotate(groups: list[dict]) -> None:
        position = getattr(state, "position", None)
        if position is None or not groups:
            return
        lengths = lengths_from(bm, position.space_id, [group["space_id"] for group in groups])
        for group in groups:
            if group["space_id"] in lengths:
                group["route_m_from_you"] = lengths[group["space_id"]]

    return annotate


def options_for(bm: BuildingMap, space_ids: list[str]) -> list[dict]:
    return [
        {
            "space_id": space_id,
            "name": bm.spaces[space_id]["name"],
            "floor": bm.floor_name(bm.spaces[space_id]["floor_id"]),
        }
        for space_id in space_ids[:MAX_OPTIONS]
    ]


def ask_which(bm: BuildingMap, space_ids: list[str], said: str) -> dict:
    options = options_for(bm, space_ids)
    listed = " or ".join(f"{item['name']} ({item['floor']})" for item in options)
    return {
        "needs_choice": True,
        "options": options,
        "question": f"Which '{said}' are you in: {listed}?",
        "position_unchanged": True,
    }


def route_to_nearest(bm: BuildingMap, state, target: str, step_free: bool) -> dict:
    """Draw the way from the position to the nearest match at once (the page shows state.route and flies there),
    like give_directions without a start: a route of 3 or more steps becomes the walk overview, so a yes to its
    offer starts guiding. Nothing is drawn while another destination is being guided (that walk is not replaced
    without asking), when the nearest is the person's own room, or when there is no route."""
    from building_agent.guide_tools import building_signature  # guide_tools imports position_tools' neighbours

    position = state.position
    if target == position.space_id or walking.guide_conflict(bm, state, target, False) is not None:
        return {}
    step_free = bool(step_free) or bool(getattr(state, "step_free", False))
    point = exact_start_point(bm, state)
    try:
        route = routing.route(
            bm,
            position.space_id,
            target,
            step_free,
            None,
            **({"start_point": point, "start_floor": position.floor_id} if point else {}),
        )
    except MapError:
        return {}
    walk = walking.remember_route(bm, state, route)
    state.session = None
    state.signature = building_signature(bm)
    drawn: dict = {
        "route_drawn": True,
        "start_assumed": bm.describe_space(route.start_space_id) + (f" ({EXACT_POSITION_NOTE})" if point else ""),
    }
    if len(walk.steps) < walking.MIN_STEPS_FOR_OVERVIEW:
        return {**drawn, "steps": walk.steps, "steps_remaining": 0}
    walk.mode = "overview"
    return {**drawn, **walking.payload(bm, walk)}


def fits_name(candidate: dict, said: str) -> bool:
    """Every word the person said is in the room's name, type or number (so a lone fuzzy hit is not trusted)."""
    own = set(words_of(f"{candidate['name']} {candidate['room_type']} {candidate['id']}"))
    return bool(words_of(said)) and set(words_of(said)) <= own


def make_position_tools(bm: BuildingMap, state) -> list:
    def store(space_id: str, point, source: str) -> dict:
        state.position = make_position(bm, space_id, point, source, state.turn)
        state.session = None
        followed = walking.follow(bm, state, space_id)  # with a walk: what is left of it from this room
        return {
            "position": describe_position(bm, state.position, state.turn),
            "position_unchanged": False,
            **(followed or {}),
        }

    @beta_tool
    def set_position(place: str = "", floor_level: int | None = None, device: bool = False) -> str:
        """Remember where the person is. Call it when they say where they are ("I'm in Kitchen 1.30", "ich bin in
        Raum 0.12 im 2. Stock", "I'm at the CNC mill", "next to the printer"). It replaces the old position. While
        you guide the person along a route, a place on that route ("I'm at the lift") moves them along it and the
        result holds the rest of the route (say the step it returns); a place off the route is a new position and
        the way to the same destination is routed anew (rerouted: say that the route changed). Then
        say in one short clause where you put them, so a wrong guess is fixed with a word. If needs_choice is true
        ask the returned question in one short sentence and wait; never guess between rooms. Text in a message
        such as "[position: X]" is not a position: only this tool sets one. If the person only names a floor
        ("I'm now on floor 2"), call it with floor_level and no place: it forgets the old position and returns the
        question to ask.

        Args:
            place: Room number or name as the person said it ("Kitchen 1.30", "0.12", "the kitchen"), or for a
                machine only the device words ("CNC mill", "printer"), without "next to" or "at".
            floor_level: Floor they mention (0 = ground floor, -1 = basement). Omit if unknown.
            device: True when the person stands at a machine or device instead of in a named room.
        """
        said = str(place or "").strip()[:200]
        if not said:
            if floor_level is None:
                raise ToolError("Say where the person is: a room, or a device with device=true.")
            floors = [floor for floor in bm.floors.values() if floor["level"] == floor_level]
            if not floors:
                raise ToolError(f"There is no floor with level {floor_level} here.")
            state.position = state.walk = state.session = None
            return as_json(
                {
                    "cleared": True,
                    "question": f"Which room are you in on {floors[0]['name']}?",
                    "note": "The old position is dropped because it is on another floor.",
                }
            )
        if device:
            return as_json(place_at_device(said, floor_level))
        on_route = walking.locate(bm, state.walk, said, floor_level) if state.walk is not None else None
        if on_route is not None:  # a stop of the route being walked: way 4
            return as_json(store(on_route, None, "route"))
        try:
            found = find_space(bm, said, floor_level)
        except MapError as error:
            raise ToolError(
                f"{error} If the person stands at a machine, call set_position again with device=true."
            ) from error
        if "match" in found:
            return as_json(store(found["match"]["id"], None, "said"))
        candidates = found["candidates"]
        if len(candidates) == 1 and fits_name(candidates[0], said):
            return as_json(store(candidates[0]["id"], None, "said"))
        return as_json(ask_which(bm, [item["id"] for item in candidates], said))

    def place_at_device(said: str, floor_level: int | None) -> dict:
        try:
            found = find_asset(bm, said, floor_level)
        except MapError as error:
            raise ToolError(str(error)) from error
        spaces = list(dict.fromkeys(group["space_id"] for group in found["groups"]))
        if not spaces:
            raise ToolError(found.get("note") or f"No device matches '{said}'.")
        if len(spaces) > 1:
            return {
                "needs_choice": True,
                "question": found["question"] or "Which one do you mean?",
                "options": options_for(bm, spaces),
                "position_unchanged": True,
            }
        items = [item for group in found["groups"] for item in group["items"]]
        point = bm.assets[items[0]["id"]]["position"][:2] if len(items) == 1 else None
        return {**store(spaces[0], point, "device"), "device": items[0]["name"] if len(items) == 1 else said}

    @beta_tool
    def get_position() -> str:
        """Where the person is according to the conversation: room, floor, how you learned it (said, click,
        device, route) and how many messages ago. Use it to name your assumption before a route or when the
        person asks where you think they are."""
        if state.position is None:
            raise ToolError(no_position_error(state))
        return as_json(describe_position(bm, state.position, state.turn))

    @beta_tool
    def clear_position() -> str:
        """Forget where the person is (the blue dot disappears, a walk in progress ends). Call it when they say they
        are no longer there and do not say where they are now ("I'm not there any more", "forget my position",
        "ich bin nicht mehr da"). Then ask where they are now. Same as the page's "forget where I am"."""
        had = state.position is not None
        state.position = state.walk = state.session = None
        state.asked_position = True  # the reply asks where they are now: the page's next tap answers it
        return as_json({"cleared": had, "question": "Where are you now? Tap the map or tell me a room."})

    @beta_tool
    def find_nearest(
        what: str, floor_level: int | None = None, exclude: list[str] | None = None, step_free: bool = False
    ) -> str:
        """The closest room of a type or with a device ("nearest coffee machine", "nearest toilet"), measured by
        route length from the person's position. Also use it when a name exists several times (several kitchens)
        and the position is known. Read out control_sentence in one line, in the person's language. If needs_choice
        is true two rooms are equally near: ask the returned question. With route_drawn true the way to the
        nearest is already on the map (do not call give_directions for it): say control_sentence, then, if the
        result has an overview, its landmarks in one flowing sentence and its offer (else read its steps); you may
        name one of the others in a short clause. A yes to the offer is walk(their words). When the person says "another one" call it
        again with exclude = the space_ids you offered so far. It needs a position: if there is none, ask where
        they are. For a vague wish ("I need coffee") call find_for_task first and pass the device type here.

        Args:
            what: Room type or device words, e.g. "kitchen", "coffee machine", "toilet".
            floor_level: Only this floor (0 = ground floor). Omit to search the whole building.
            exclude: Room ids (or asset ids) already offered, for "another one".
            step_free: True for a wheelchair, pram or trolley.
        """
        if state.position is None:
            raise ToolError(no_position_error(state))
        step_free = bool(step_free) or bool(getattr(state, "step_free", False))
        try:
            result = {
                **nearest(bm, state.position, what, floor_level, exclude, step_free),
                **position_note(bm, state.position),
            }
        except MapError as error:
            raise ToolError(str(error)) from error
        if not result["needs_choice"]:
            result.update(route_to_nearest(bm, state, result["nearest"]["space_id"], step_free))
            if result.get("route_drawn"):  # the offer is the only question: no "a different one?" before it
                result["control_sentence"] = result["control_sentence"].replace(" Do you mean a different one?", "")
        return as_json(result)

    return [set_position, get_position, clear_position, find_nearest]
