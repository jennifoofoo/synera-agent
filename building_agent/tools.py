"""Claude tools for one building: the starter tools plus one tool per registered kind plus find_space."""

import functools
import inspect
import re
from dataclasses import asdict
from pathlib import Path

import networkx as nx
from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent import routing
from building_agent.campus_tools import CampusHolder, make_campus_tools
from building_agent.find_space import find_space
from building_agent.find_tools import make_find_tools
from building_agent.guide_tools import GuideState, building_signature, make_guide_tools
from building_agent.impact import make_impact_tools
from building_agent.judge_route import judge_route
from building_agent.level4.tools import BMHolder, make_level4_tools
from building_agent.position import EXACT_POSITION_NOTE, exact_start_point, no_position_error
from building_agent.position_tools import distance_annotator, make_position_tools
from building_agent.registry import Kind, load_kinds
from building_agent.selection_tools import make_selection_tools
from building_agent.task_tools import make_task_tools
from building_agent.walk import guide_conflict, remember_route
from starter_agent.building_map import BuildingMap, MapError
from starter_agent.tools import as_json
from starter_agent.tools import make_tools as make_starter_tools

REPLACED_STARTER_TOOLS = {"find_route"}  # re-defined below on the door-to-door route model


def snake_case(name: str, value):
    """Type parameters are snake_case identifiers ("living_room"), but questions say "living room"."""
    if name.endswith("_type") and isinstance(value, str):
        return value.strip().lower().replace(" ", "_")
    return value


BRACKET_ID = re.compile(r"\[([^\[\]]+)\]\s*$")


def clean_reference(bm: BuildingMap, value):
    """The overview prints "Name [id]"; models sometimes copy that whole string. Keep just the id."""
    if isinstance(value, str) and (match := BRACKET_ID.search(value)):
        candidate = match.group(1)
        if candidate in bm.spaces or candidate in bm.connectors or candidate in bm.assets:
            return candidate
    return value


def known_types(bm: BuildingMap, name: str) -> set[str]:
    if name == "asset_type":
        return {asset["type"] for asset in bm.assets.values()}
    return {space["room_type"] for space in bm.spaces.values()}


def resolve_type(bm: BuildingMap, name: str, value):
    """Map a shortened type ("generic", "ups") to the one building type it stands for; refuse if unclear."""
    value = snake_case(name, value)
    if not (name.endswith("_type") and isinstance(value, str)):
        return value
    types = known_types(bm, name)
    if value in types:
        return value
    close = [kind for kind in types if kind.startswith(value + "_") or value in kind.split("_")]
    if len(close) == 1:
        return close[0]
    raise MapError(f"Unknown {name} '{value}'. Valid values here: {', '.join(sorted(types))}.")


def kind_tool(bm: BuildingMap, kind: Kind):
    """Expose a kind as a tool: same signature minus `bm`, docstring from the kind description."""
    signature = inspect.signature(kind.fn)
    parameters = list(signature.parameters.values())[1:]

    @functools.wraps(kind.fn)
    def run(*args, **kwargs) -> str:
        try:
            kwargs = {name: resolve_type(bm, name, clean_reference(bm, value)) for name, value in kwargs.items()}
            try:
                signature.bind(bm, *args, **kwargs)
            except TypeError as error:  # a wrong argument list is the model's mistake, not a kind bug
                raise ToolError(f"Wrong arguments for {kind.name}: {error}") from error
            return as_json(kind.fn(bm, *args, **kwargs))
        except MapError as error:
            raise ToolError(str(error)) from error
        except (KeyError, ValueError, nx.NodeNotFound) as error:
            raise ToolError(
                f"Invalid argument: {error}. Use space ids from find_space and floor ids from the overview."
            ) from error

    run.__signature__ = signature.replace(parameters=parameters)
    run.__name__ = kind.name
    run.__doc__ = f"{kind.description}\n\nSpace parameters take space ids from find_space; floor_id takes a floor id from the building overview; *_type parameters are snake_case identifiers such as lab_bench or living_room."
    return beta_tool(run)


REPLACED_BY_GUIDE = {"set_closed", "add_door"}  # edits go through propose_change and confirm_change


def make_tools(
    bm: BuildingMap,
    output_directory: Path,
    guide: GuideState | None = None,
    on_saved=None,
    campus: CampusHolder | None = None,
) -> list:
    guide = guide or GuideState()

    @beta_tool
    def find_space_tool(name: str, floor_level: int | None = None) -> str:
        """Resolve a room id, number or name to its space id. Use this before the calculation tools,
        which need space ids. Returns one match, or candidates to choose from.

        Args:
            name: Room number or name, e.g. "Lab 0.12" or "0.12".
            floor_level: Floor of the room (0 = ground floor, -1 = basement). Omit if unknown.
        """
        try:
            return as_json(find_space(bm, name, floor_level))
        except MapError as error:
            raise ToolError(str(error)) from error

    find_space_tool.name = "find_space"

    @beta_tool
    def find_route(
        destination: str,
        start: str | None = None,
        step_free: bool = False,
        via: list[str] | None = None,
        replace_guide: bool = False,
    ) -> str:
        """Shortest walking route between two places, with step-by-step directions and length in metres.

        Args:
            destination: Space id, asset id, or exact room number/name of where they want to go.
            start: Space id, asset id, or exact room number/name of where the person is. Leave it out to start at
                the person's position (see set_position) and say so (start_assumed).
            step_free: True to avoid stairs and steps (wheelchair, trolley, pram).
            via: Optional list of places to visit in order between start and destination (multi-stop tour).
            replace_guide: True only after the person agreed to drop the route they are being guided on.
        """
        if start is None and guide.position is None:
            raise ToolError(no_position_error(guide))
        point = None
        try:
            conflict = guide_conflict(bm, guide, bm.resolve_space(destination), replace_guide)
            if conflict is not None:
                return as_json(conflict)
            point = exact_start_point(bm, guide) if start is None else None
            result = routing.route(
                bm,
                guide.position.space_id if start is None else start,
                destination,
                step_free,
                via,
                **({"start_point": point, "start_floor": guide.position.floor_id} if point else {}),
            )
            remember_route(bm, guide, result, [bm.resolve_space(stop) for stop in via or []])
            guide.signature = building_signature(bm)
        except MapError as error:
            raise ToolError(str(error)) from error
        assumed = {"start_assumed": bm.describe_space(result.start_space_id)} if start is None else {}
        if point:
            assumed["start_assumed"] += f" ({EXACT_POSITION_NOTE})"
        return as_json({**asdict(result), **assumed})

    @beta_tool
    def find_forklift_route(start: str, destination: str, via: list[str] | None = None) -> str:
        """Route for a FORKLIFT or pallet truck: only forklift aisles and openings 3 m or wider, never stairs,
        and production bays only as a start or destination, never passed through. Use this instead of
        find_route when the person drives a forklift or moves pallets by truck.

        Args:
            start: Space id, asset id, or exact room number/name of where the forklift is.
            destination: Space id, asset id, or exact room number/name of where it must go.
            via: Optional list of places to visit in order between start and destination.
        """
        try:
            result = judge_route(bm, start, destination, forklift=True, via=via)
        except MapError as error:
            raise ToolError(str(error)) from error
        if not result["ok"]:
            raise ToolError(f"No forklift route: {result['reason']}")
        return as_json(result)

    kinds = [kind_tool(bm, kind) for kind in load_kinds().values()]
    annotate = distance_annotator(bm, guide)
    starter = [
        tool
        for tool in make_starter_tools(bm, output_directory)
        if tool.name not in REPLACED_BY_GUIDE | REPLACED_STARTER_TOOLS
    ]
    guide_tools = make_guide_tools(bm, output_directory, guide)
    level4_tools = make_level4_tools(BMHolder(bm), output_directory, guide, on_saved)
    return [
        *starter,
        find_route,
        find_forklift_route,
        find_space_tool,
        *make_find_tools(bm, annotate),
        *make_position_tools(bm, guide),
        *make_task_tools(bm, annotate),
        *make_impact_tools(bm),
        *guide_tools,
        *make_selection_tools(bm, guide),
        *level4_tools,
        *(make_campus_tools(campus, output_directory, guide) if campus else []),
        *kinds,
    ]
