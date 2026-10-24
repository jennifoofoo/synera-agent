"""Fixtures and the audit summary for the mobile smoke tests (see docs/mobile-audit.md).

These tests need Playwright and its browsers (`uv sync --group e2e`, `uv run playwright install chromium webkit`).
Without them every test skips, so scripts/check.sh stays green. They are excluded from the default run by the `e2e`
marker, run them with `scripts/mobile_smoke.sh` or `uv run pytest -m e2e tests/e2e`.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
DEVICES = ["Pixel 7", "iPhone 14"]

_NODE_ITEMS: dict[str, tuple[str, str]] = {}
_RESULTS: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: browser tests with Playwright (need `uv sync --group e2e`)")
    config.addinivalue_line("markers", "audit(item, title): which docs/mobile-audit.md item a test protects")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _pick_buildings(target: Path) -> None:
    """Copy two small dev buildings (building.json, equipment, floor files) into the fixture data folder."""
    dev = DATA / "dev"
    if not dev.exists():
        pytest.skip("data/dev is missing (symlink data into the worktree)")
    candidates = [d for d in dev.iterdir() if (d / "building.json").exists()]
    if len(candidates) < 2:
        pytest.skip("data/dev has fewer than 2 buildings")
    smallest = sorted(candidates, key=lambda d: (sum(f.stat().st_size for f in d.iterdir() if f.is_file()), d.name))
    for src in smallest[:2]:
        shutil.copytree(src, target / "dev" / src.name)


@pytest.fixture(scope="session")
def base_url(tmp_path_factory):
    """Start the web server with the fake chat turn (tests/e2e/fake_chat_server.py: "I'm here" sets the position,
    every other message gets "ok") on a free port with 2 dev buildings and no API key; always shut it down."""
    if not (REPO / "twin" / "dist" / "index.html").exists():
        pytest.skip("twin/dist is missing (scripts/build_twin.sh)")
    data = tmp_path_factory.mktemp("mobile_data")
    _pick_buildings(data)
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if "API_KEY" not in k and not k.startswith("ANTHROPIC")}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.e2e.fake_chat_server",
            "--data",
            str(data),
            "--port",
            str(port),
            "--env-file",
            str(data / "no.env"),
        ],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/"
    try:
        for _ in range(100):
            if proc.poll() is not None:
                pytest.fail("web server exited early")
            try:
                urllib.request.urlopen(url, timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("web server did not start")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def playwright_instance():
    sync_api = pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")
    with sync_api.sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def _browsers(playwright_instance):
    opened: dict[str, object] = {}
    yield opened
    for browser in opened.values():
        browser.close()


@pytest.fixture(params=DEVICES, ids=["pixel7", "iphone14"])
def device(request, playwright_instance, _browsers):
    """(name, descriptor, browser) for the phone profile; skips when the browser binary is missing."""
    name = request.param
    descriptor = playwright_instance.devices[name]
    kind = descriptor["default_browser_type"]
    if kind not in _browsers:
        try:
            _browsers[kind] = getattr(playwright_instance, kind).launch()
        except Exception as error:  # noqa: BLE001 - missing browser binaries
            pytest.skip(f"{kind} not installed (playwright install chromium webkit): {str(error)[:80]}")
    return name, descriptor, _browsers[kind]


@pytest.fixture
def open_page(device, base_url):
    """Factory: open the twin on the phone profile (optionally landscape, optionally with an init script), wait for
    the plan and the camera to settle. Contexts are closed afterwards."""
    contexts = []

    def _open(init_script: str | None = None, wait_plan: bool = True, landscape: bool = False):
        _, descriptor, browser = device
        options = dict(descriptor)
        if landscape:
            options["viewport"] = {"width": descriptor["viewport"]["height"], "height": descriptor["viewport"]["width"]}
        context = browser.new_context(**options)
        contexts.append(context)
        if init_script:
            context.add_init_script(init_script)
        page = context.new_page()
        page.errors = []
        page.console_errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and page.console_errors.append(m.text))
        page.goto(base_url)
        if wait_plan:
            page.wait_for_function(
                "() => !!(window.__twinScene && window.__twinStore && window.__twinStore.getState().model"
                " && window.__twinCamera && document.querySelector('.phone-back'))",
                timeout=20000,
            )
            page.wait_for_timeout(1500)  # the camera flies to the floor first
        return page

    yield _open
    for context in contexts:
        context.close()


# ---------- summary per audit item ----------


def pytest_collection_modifyitems(items):
    for test in items:
        mark = test.get_closest_marker("audit")
        if mark:
            item, title = mark.args
            _NODE_ITEMS[test.nodeid] = (item, title)


def pytest_runtest_logreport(report):
    key = _NODE_ITEMS.get(report.nodeid)
    if key is None:
        return
    device_id = report.nodeid.rsplit("[", 1)[-1].rstrip("]")
    if hasattr(report, "wasxfail"):
        if report.when != "call":
            return
        outcome = "xfail" if report.skipped else "XPASS"
    elif report.when == "call":
        outcome = "pass" if report.passed else "FAIL"
    elif report.skipped:
        outcome = "skip"
    elif report.failed:
        outcome = "ERROR"
    else:
        return
    _RESULTS[key][device_id] = outcome


def pytest_terminal_summary(terminalreporter):
    if not _RESULTS:
        return
    write = terminalreporter.write_line
    write("")
    write("Mobile audit summary (pass = protected, xfail = known gap, XPASS = gap fixed so drop the xfail)")
    for key in sorted(_RESULTS, key=lambda k: (k[0] == "ok", k[0].zfill(3), k[1])):
        item, title = key
        cells = "  ".join(f"{dev}={result}" for dev, result in sorted(_RESULTS[key].items()))
        label = "works" if item == "ok" else f"item {item}"
        write(f"  {label:8} {title:55} {cells}")
