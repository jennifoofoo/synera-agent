"""Registry of campus input adapters. Every file here (except `_common.py`) exports one `ADAPTER`; nothing else to edit.

`load_campus` in building_agent/campus.py tries every adapter's `detect` and uses the first that recognises the file."""

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PRIORITY = ("campus_json", "links_csv", "geo", "conversation")


@dataclass(frozen=True)
class Adapter:
    name: str
    detect: Callable[[Path], bool]
    load: Callable[..., object]  # load(path, root=None) -> Campus
    description: str  # what the file must contain, in a sentence the agent can read out


def load_adapters() -> dict[str, Adapter]:
    from building_agent import campus_adapters

    found: dict[str, Adapter] = {}
    for module_info in pkgutil.iter_modules(campus_adapters.__path__):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"building_agent.campus_adapters.{module_info.name}")
        adapter = getattr(module, "ADAPTER", None)
        if adapter is not None:
            found[adapter.name] = adapter
    order = sorted(found, key=lambda name: (PRIORITY.index(name) if name in PRIORITY else len(PRIORITY), name))
    return {name: found[name] for name in order}


def describe_adapters() -> str:
    lines = ["I can read these formats:"]
    lines += [f"- {adapter.name}: {adapter.description}" for adapter in load_adapters().values()]
    return "\n".join(lines)
