"""Claude tools for one building: the starter tools plus one tool per registered kind plus find_space."""

import functools
import inspect
from pathlib import Path

from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent.find_space import find_space
from building_agent.registry import Kind, load_kinds
from starter_agent.building_map import BuildingMap, MapError
from starter_agent.tools import as_json
from starter_agent.tools import make_tools as make_starter_tools


def kind_tool(bm: BuildingMap, kind: Kind):
    """Expose a kind as a tool: same signature minus `bm`, docstring from the kind description."""
    signature = inspect.signature(kind.fn)
    parameters = list(signature.parameters.values())[1:]

    @functools.wraps(kind.fn)
    def run(*args, **kwargs) -> str:
        try:
            return as_json(kind.fn(bm, *args, **kwargs))
        except MapError as error:
            raise ToolError(str(error)) from error

    run.__signature__ = signature.replace(parameters=parameters)
    run.__name__ = kind.name
    run.__doc__ = kind.description
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
