"""Inspection round and notes on the demo building, in the browser against the real web server (fake chat, no key).

Round (twin/src/round/*, ui/Round.tsx, docs/specs/inspection-round.md): fire extinguishers on the ground floor of
train/proc-factory-train-015 from Main aisle H-B3 give 5 stops, the drawn length equals /api/route through the same
stops (±1 m), the normal route card stays hidden while the round panel owns the route, "Hey Wanda, done" walks to the
next stop ("Stop n of m"), "how far" says the metres left, End route pauses the round, and a door between Production
zone H-A2 and Server room 0.16 makes the round shorter.
Notes (twin/src/notes/*, ui/Facts.tsx, docs/specs/place-knowledge.md): a note said hands-free is stored on the server
(GET /api/facts), not on the device, and survives a reload.

Skips without Playwright, chromium, data/train or twin/dist.
Run: scripts/build_twin.sh && uv run --group e2e pytest -m e2e tests/e2e/test_round_and_notes.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e.conftest import DATA, REPO, _free_port
from tests.e2e.test_voice_followup import FAKE_VOICE

pytestmark = pytest.mark.e2e

DEMO = "train/proc-factory-train-015"


@pytest.fixture()
def server(tmp_path_factory):
    if not (REPO / "twin" / "dist" / "index.html").exists():
        pytest.skip("twin/dist is missing (scripts/build_twin.sh)")
    if not (DATA / DEMO / "building.json").exists():
        pytest.skip("data/train is missing")
    root = tmp_path_factory.mktemp("round")
    shutil.copytree(DATA / DEMO, root / "data" / DEMO)
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if "API_KEY" not in k and not k.startswith("ANTHROPIC")}
    env["PYTHONPATH"] = str(REPO)
    # cwd is the temp folder, so the facts land in its agent_output/knowledge, not in the repo
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.e2e.fake_chat_server",
            "--data",
            "data",
            "--port",
            str(port),
            "--env-file",
            "no.env",
        ],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            if proc.poll() is not None:
                pytest.fail("server exited early")
            try:
                urllib.request.urlopen(url + "/", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("server did not start")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture()
def page(server, playwright_instance):
    try:
        browser = playwright_instance.chromium.launch()
    except Exception as error:  # noqa: BLE001 - missing browser binary
        pytest.skip(f"chromium not installed: {str(error)[:80]}")
    context = browser.new_context(viewport={"width": 1200, "height": 800})
    context.add_init_script(FAKE_VOICE)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.route("**/api/speak", lambda route: route.fulfill(status=503, body="no voice"))
    page.goto(f"{server}/?building={DEMO}")
    page.wait_for_function("() => !!(window.__twinStore?.getState().model && window.__round)", timeout=30000)
    page.wait_for_timeout(500)
    page.server = server
    yield page
    assert page.errors == [], page.errors
    context.close()
    browser.close()


def space_id(page, name: str) -> str:
    return page.evaluate(
        "(n) => window.__twinStore.getState().building.spaces.find((s) => s.name === n).id",
        name,
    )


def wait_until(page, js: str, timeout_s: float = 30.0, arg=None):
    end = time.time() + timeout_s
    while time.time() < end:
        value = page.evaluate(js, arg)
        if value:
            return value
        page.wait_for_timeout(100)
    raise AssertionError(f"not in time: {js} -> {page.evaluate(js, arg)}")


def say(page, text: str) -> str:
    """Speak to Wanda hands-free; returns what she says back."""
    wait_until(page, "() => window.__liveMics() > 0")
    before = page.evaluate("() => window.__spoken.length")
    assert page.evaluate("(t) => window.__say(t)", text)
    wait_until(page, "(n) => window.__spoken.length > n", arg=before)
    return page.evaluate("() => window.__spoken[window.__spoken.length - 1]")


ROUND = "() => { const r = window.__round.useRound.getState(); return { guiding: r.guiding, index: r.index, checked: r.checked.length, finished: r.finished, busy: r.busy, error: r.error, length: r.plan && r.plan.lengthM, stops: r.plan && r.plan.stops.map((s) => s.spaceId) }; }"


def test_round_on_the_demo_building(page):
    start = space_id(page, "Main aisle H-B3")
    page.evaluate(
        "async (start) => { await window.__round.openRound('fire extinguisher', 'Ground floor'); await window.__round.useRound.setState({ startId: start }); await window.__round.planRound(); }",
        start,
    )
    plan = wait_until(page, f"() => {{ const r = ({ROUND})(); return r.stops && !r.busy && r }}")
    assert len(plan["stops"]) == 5, plan
    stops = plan["stops"]
    same_order = page.evaluate(
        """async ([building, start, stops]) => { const r = await fetch('/api/route', { method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ building, start, destination: stops[stops.length - 1], via: stops.slice(0, -1) }) });
          return (await r.json()).route.length_m; }""",
        [DEMO, start, stops],
    )
    assert abs(same_order - plan["length"]) <= 1
    assert 95 <= plan["length"] <= 105, "spec: about 100 m"
    assert page.get_by_text("5 stops", exact=False).first.is_visible()
    # Leonie's question, decision A: the round panel is the only start button while it owns the route.
    assert page.locator(".card-route").count() == 0
    assert page.get_by_role("button", name="Start round").is_visible()

    page.evaluate("() => window.__twinStore.getState().setHandsFree(true)")
    page.get_by_role("button", name="Start round").click()
    wait_until(page, f"() => ({ROUND})().guiding")
    assert page.get_by_text("Stop 1 of 5").first.is_visible()

    reply = say(page, "hey wanda done")
    assert "Stop 2 of 5" in reply, reply
    wait_until(page, "() => window.__twinStore.getState().walkStep !== null")
    assert page.locator(".card-walk").get_by_text("Stop 2 of 5").is_visible()
    assert page.locator(".card-route").count() == 0

    far = say(page, "hey wanda how far")
    assert "metres left" in far or "steps left" in far, far

    # The last step's Done on the walk sheet checks the stop and goes on to stop 3.
    page.evaluate("() => { const s = window.__twinStore.getState(); s.setWalkStep(s.state.route.steps.length - 1); }")
    page.locator(".card-walk").get_by_role("button", name="Done", exact=True).last.click()
    wait_until(page, f"() => ({ROUND})().index === 2 && ({ROUND})().checked === 2")

    page.get_by_role("button", name="End route").first.click()
    state = wait_until(page, f"() => {{ const r = ({ROUND})(); return !r.guiding && r }}")
    assert state["checked"] == 2 and state["stops"] == stops, "End route pauses, the checks stay"
    assert page.evaluate("() => window.__twinStore.getState().walkStep") is None
    assert page.get_by_role("button", name="Resume (2 of 5 done)").is_visible()

    first, second = space_id(page, "Production zone H-A2"), space_id(page, "Server room 0.16")
    what_if = page.evaluate("async ([a, b]) => await window.__round.roundWhatIfDoor(a, b)", [first, second])
    assert what_if["afterM"] < what_if["beforeM"] - 20, what_if
    assert page.get_by_text("m shorter").first.is_visible()


def test_note_said_hands_free_is_stored_on_the_server(page):
    room = space_id(page, "Server room 0.16")
    page.evaluate("(id) => window.__twinStore.getState().select({ kind: 'space', id })", room)
    wait_until(page, "() => window.__twinNotes.useNotes.getState().storage?.kind === 'server'")
    page.evaluate("() => window.__twinStore.getState().setHandsFree(true)")
    reply = say(page, "hey wanda note: rack 3 fan is loud")
    assert reply.startswith("Noted at"), reply
    with urllib.request.urlopen(f"{page.server}/api/facts?key={DEMO}&space_id={room}") as response:
        facts = json.loads(response.read())["facts"]
    assert [fact["text"] for fact in facts] == ["rack 3 fan is loud"]
    # the page keeps the server's copy, once
    assert wait_until(page, "() => (window.__twinStore.getState().state.facts || []).length") == 1
    notes = page.evaluate("() => window.__twinNotes.useNotes.getState().notes.map((n) => n.id)")
    assert notes == [facts[0]["id"]]

    page.reload()
    page.wait_for_function("() => !!(window.__twinNotes?.useNotes.getState().loaded)", timeout=30000)
    assert page.evaluate("() => window.__twinNotes.useNotes.getState().notes.map((n) => n.text)") == [
        "rack 3 fan is loud"
    ]
