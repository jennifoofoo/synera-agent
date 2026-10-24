"""Claude tools for one building: the starter tools plus one tool per registered kind plus find_space."""

import functools
import inspect
import re
from pathlib import Path

import networkx as nx
from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent.find_space import find_space
from building_agent.guide_tools import GuideState, make_guide_tools
from building_agent.registry import Kind, load_kinds
from starter_agent.building_map import BuildingMap, MapError
from starter_agent.tools import as_json
from starter_agent.tools import make_tools as make_starter_tools


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


def make_tools(bm: BuildingMap, output_directory: Path, guide: GuideState | None = None) -> list:
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
    kinds = [kind_tool(bm, kind) for kind in load_kinds().values()]
    starter = [tool for tool in make_starter_tools(bm, output_directory) if tool.name not in REPLACED_BY_GUIDE]
    guide_tools = make_guide_tools(bm, output_directory, guide or GuideState())
    return [*starter, find_space_tool, *guide_tools, *kinds]
