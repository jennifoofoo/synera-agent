"""Registry of question kinds. Every file in building_agent/kinds/ exports one `KIND`; nothing else to edit.

tools.py builds the Claude tools from load_kinds(), so adding a kind is: new file in kinds/ plus tests/test_<kind>.py."""

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Kind:
    name: str
    fn: Callable[..., dict]
    description: str


def load_kinds() -> dict[str, Kind]:
    from building_agent import kinds

    found: dict[str, Kind] = {}
    for module_info in pkgutil.iter_modules(kinds.__path__):
        module = importlib.import_module(f"building_agent.kinds.{module_info.name}")
        kind = getattr(module, "KIND", None)
        if kind is not None:
            found[kind.name] = kind
    return found
