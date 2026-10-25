"""Screenshots of the twin for the UI polish (before/after): 3D overview with a route, a closed lift, the 2D plan and
the phone with the route sheet. Runs the web server with the fake chat turn (no API key) on the factory building
only, against the built page (`cd twin && npm run build`). Fails on any page error or console error.

Run: uv run --group e2e python scripts/ui_shots.py --out twin/docs/ui-before
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
BUILDING = "proc-factory-dev-012"
START = f"{BUILDING}-F0-S029"  # Office 0.29, ground floor
DESTINATION = f"{BUILDING}-F1-S006"  # Meeting room 1.06, first floor (the route takes the office lift)
LIFT_SPACE = f"{BUILDING}-F0-S027"  # Lift 0.27
LIFT = "Office lift"

WAIT_MODEL = (
    "() => !!(window.__twinStore && window.__twinStore.getState().model && window.__twinControls"
    " && window.__twinControls.current)"
)
WAIT_ROUTE = "() => { const s = window.__twinStore.getState().state; return !!(s && s.route && s.route.ok); }"
SILENT = "(() => { try { if (window.speechSynthesis) window.speechSynthesis.speak = () => {}; } catch (e) {} })();"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(data: Path, port: int) -> subprocess.Popen:
    env = {k: v for k, v in os.environ.items() if "API_KEY" not in k and not k.startswith("ANTHROPIC")}
    command = [
        sys.executable,
        "-m",
        "tests.e2e.fake_chat_server",
        "--data",
        str(data),
        "--port",
        str(port),
        "--env-file",
        str(data / "no.env"),
    ]
    proc = subprocess.Popen(command, cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/"
    for _ in range(150):
        if proc.poll() is not None:
            raise SystemExit("web server exited early")
        try:
            urllib.request.urlopen(url, timeout=1).read()
            return proc
        except OSError:
            time.sleep(0.1)
    raise SystemExit("web server did not start")


def open_page(context, url: str, errors: list[str]):
    page = context.new_page()
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: m.type == "error" and errors.append(f"console: {m.text}"))
    page.goto(f"{url}?building=dev/{BUILDING}")
    page.wait_for_function(WAIT_MODEL, timeout=90000)
    page.wait_for_timeout(1200)
    return page


def store(page, call: str) -> None:
    page.evaluate(f"() => window.__twinStore.getState().{call}")


def set_route(page) -> None:
    store(page, f"route('{START}', '{DESTINATION}')")
    page.wait_for_function(WAIT_ROUTE, timeout=60000)


def settle(page, ms: int = 2600) -> None:
    page.mouse.move(40, 300)
    page.mouse.wheel(0, 1)  # the phone renders on demand
    page.wait_for_timeout(ms)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=REPO / "twin" / "docs" / "ui-before")
    args = parser.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    if not (REPO / "twin" / "dist" / "index.html").exists():
        raise SystemExit("twin/dist is missing: cd twin && npm run build")
    tmp = Path(tempfile.mkdtemp(prefix="ui_shots_"))
    shutil.copytree(REPO / "data" / "dev" / BUILDING, tmp / "dev" / BUILDING)
    port = free_port()
    proc = start_server(tmp, port)
    url = f"http://127.0.0.1:{port}/"
    errors: list[str] = []
    stats: dict[str, object] = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--mute-audio"])
            desktop = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            desktop.add_init_script(SILENT)
            page = open_page(desktop, url, errors)
            # 3D overview with the route
            store(page, "setViewMode('3d')")
            set_route(page)
            store(page, "requestCamera({ kind: 'home' })")
            settle(page)
            page.screenshot(path=str(out / "3d-route.png"))
            stats["3d-route"] = page.evaluate("() => window.__twinStats ? window.__twinStats() : null")
            # the closed lift, camera on it
            store(page, f"setClosed('{LIFT}', true)")
            page.wait_for_timeout(800)
            store(page, f"flyTo('{LIFT_SPACE}')")
            settle(page)
            page.screenshot(path=str(out / "3d-closed.png"))
            # 2D plan with the route (closure still set)
            store(page, "setViewMode('2d')")
            store(page, "requestCamera({ kind: 'home' })")
            settle(page)
            page.screenshot(path=str(out / "2d-plan.png"))
            desktop.close()
            phone = browser.new_context(
                viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True
            )
            phone.add_init_script(SILENT)
            page = open_page(phone, url, errors)
            set_route(page)
            settle(page)
            page.screenshot(path=str(out / "mobile-sheet.png"))
            phone.close()
            browser.close()
    finally:
        proc.terminate()
        shutil.rmtree(tmp, ignore_errors=True)
    print("stats:", stats)
    if errors:
        print("ERRORS:\n" + "\n".join(errors))
        raise SystemExit(1)
    print(f"saved 4 screenshots to {out}")


if __name__ == "__main__":
    main()
