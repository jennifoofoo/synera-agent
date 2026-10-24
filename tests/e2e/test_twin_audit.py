"""Drawn-vs-data audit of the twin (see tests/e2e/twin_audit.py). Slow (starts two servers and a browser), so it is
marked e2e and left out of scripts/check.sh; run it with `uv run --with playwright pytest -m e2e tests/e2e` or
`scripts/twin_audit.sh`. Skips cleanly without Playwright, its Chromium, twin/node_modules or the data."""

import importlib.util
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]


def _skip_reason() -> str | None:
    if importlib.util.find_spec("playwright") is None:
        return "playwright is not installed (uv run --with playwright ...; then: playwright install chromium)"
    if not (ROOT / "twin" / "node_modules" / ".bin" / "vite").exists():
        return "twin/node_modules is missing (cd twin && npm install)"
    if shutil.which("node") is None:
        return "node is not installed"
    if not (ROOT / "data" / "dev").exists():
        return "data/ is missing (scripts/get_data.sh)"
    return None


def test_twin_draws_what_the_data_says():
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    from tests.e2e import twin_audit

    try:
        report = twin_audit.run()
    except Exception as error:  # a browser that cannot start is an environment problem, not a twin bug
        if "Executable doesn't exist" in str(error) or "playwright install" in str(error):
            pytest.skip("Chromium for Playwright is not installed (playwright install chromium)")
        raise
    print()
    print(report.table())
    assert not report.failed, "\n" + report.table()
