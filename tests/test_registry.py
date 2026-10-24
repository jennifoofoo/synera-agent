"""Guards the one-file-per-kind convention (see docs/specs/core-2d.md)."""

import importlib
import inspect
import pkgutil
from pathlib import Path

from building_agent import kinds
from building_agent.registry import load_kinds

TESTS = Path(__file__).parent
STATUS = Path(__file__).parent.parent / "docs" / "STATUS.md"


def test_every_file_in_kinds_exports_a_kind_named_like_the_file():
    modules = [info.name for info in pkgutil.iter_modules(kinds.__path__)]
    assert modules, "no files in building_agent/kinds/"
    for module_name in modules:
        module = importlib.import_module(f"building_agent.kinds.{module_name}")
        kind = getattr(module, "KIND", None)
        assert kind is not None, f"kinds/{module_name}.py has no KIND, so it is not registered"
        assert kind.name == module_name, (
            f"kinds/{module_name}.py registers '{kind.name}', file and kind name must match"
        )


def test_every_kind_has_the_contract_shape():
    for name, kind in load_kinds().items():
        assert kind.description.strip(), f"{name}: description is empty"
        first_parameter = next(iter(inspect.signature(kind.fn).parameters))
        assert first_parameter == "bm", f"{name}: first parameter must be 'bm'"


def test_every_kind_has_a_test_file():
    for name in load_kinds():
        assert (TESTS / f"test_{name}.py").exists(), f"missing tests/test_{name}.py"


def test_every_kind_is_listed_in_status():
    status = STATUS.read_text(encoding="utf-8")
    for name in load_kinds():
        assert name in status, f"{name} is not in docs/STATUS.md (claim it there first)"
