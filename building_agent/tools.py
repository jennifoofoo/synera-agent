"""Claude tools for one building: the starter tools plus one tool per registered kind plus find_space."""

import functools
import inspect
from pathlib import Path

import networkx as nx
from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent.find_space import find_space
from building_agent.registry import Kind, load_kinds
from starter_agent.building_map import BuildingMap, MapError
from starter_agent.tools import as_json
from starter_agent.tools import make_tools as make_starter_tools


def snake_case(name: str, value):
    """Type parameters are snake_case identifiers ("living_room"), but questions say "living room"."""
    if name.endswith("_type") and isinstance(value, str):
        return value.strip().lower().replace(" ", "_")
    return value


def kind_tool(bm: BuildingMap, kind: Kind):
    """Expose a kind as a tool: same signature minus `bm`, docstring from the kind description."""
    signature = inspect.signature(kind.fn)
    parameters = list(signature.parameters.values())[1:]

    @functools.wraps(kind.fn)
    def run(*args, **kwargs) -> str:
        kwargs = {name: snake_case(name, value) for name, value in kwargs.items()}
        try:
            return as_json(kind.fn(bm, *args, **kwargs))
        except MapError as error:
            raise ToolError(str(error)) from error
        except (KeyError, ValueError, nx.NodeNotFound) as error:
            raise ToolError(f"Invalid argument: {error}. Use space ids from find_space and floor ids from the overview.") from error

    run.__signature__ = signature.replace(parameters=parameters)
    run.__name__ = kind.name
    run.__doc__ = f"{kind.description}\n\nSpace parameters take space ids from find_space; floor_id takes a floor id from the building overview; *_type parameters are snake_case identifiers such as lab_bench or living_room."
    return beta_tool(run)


def make_tools(bm: BuildingMap, output_directory: Path) -> list:
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
    return [*make_starter_tools(bm, output_directory), find_space_tool, *kinds]
