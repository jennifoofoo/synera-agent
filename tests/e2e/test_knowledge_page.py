"""Place knowledge on the page (docs/specs/place-knowledge-page.md), desktop and phone, real web server, no API key:

- the "Notes & photos" layer is off by default: facts created with POST /api/facts show no pin; switched on, the pins
  show (laid out with the labels, no overlaps) and the switch is remembered after a reload
- tapping a pin opens its card: text, author, "since …", the photo (and the photo viewer), the history
- "Note here" in the room card asks the name once, saves a note (the pin appears), "Undo" removes it again
- a timed closure (a closure fact with valid_to) shows "Closed until tomorrow 18:00" beside the closed lift and in
  the route's "Avoids closed …" line

Screenshots go to docs/twin-audit/knowledge-page/. Needs the built page (`scripts/build_twin.sh`), Playwright and
Chromium and data/dev; skips otherwise. Run: `uv run pytest -m e2e tests/e2e/test_knowledge_page.py`.
"""

from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e.conftest import DATA, REPO, _free_port
from tests.e2e.test_semantic_zoom import SHOWN, _open, _zoom, chromium  # noqa: F401 - fixture

pytestmark = pytest.mark.e2e

B = "proc-factory-dev-012"
LIFT = f"{B}-V02"
SHOTS = REPO / "docs" / "twin-audit" / "knowledge-page"

# Create a fact the way the page does (same-origin POST /api/facts) on the n-th largest named room of floor 0, and
# hand the returned state to the store (as the page does after its own POST).
ADD_FACT = """async ([kind, text, photo, index]) => {
  const s = window.__twinStore.getState();
  const floor = s.model.floors.find((f) => f.level === 0);
  const rooms = floor.spaces.filter((sp) => sp.type === 'room' && sp.name).sort((a, b) => b.area_m2 - a.area_m2 || a.id.localeCompare(b.id));
  const room = rooms[index];
  const body = { building: s.buildingKey, kind, text, author: 'Techniker A', anchor: { space_id: room.id } };
  if (photo) body.photo_base64 = photo;
  const response = await fetch('/api/facts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error);
  window.__twinStore.getState().applyState(result.state);
  return { id: result.fact.id, room: room.id, floor: room.floor_id, photo: result.fact.photo };
}"""

PINS = """() => [...document.querySelectorAll('[data-testid="fact-pin"]')].map((el) => ({
  ids: el.dataset.factIds.split(' '), kind: el.dataset.factKind, photo: !!el.dataset.photo }))"""

TWO_F0_ROOMS = """() => {
  const m = window.__twinStore.getState().model;
  const rooms = m.floors.find((f) => f.level === 0).spaces.filter((s) => s.type === 'room' && s.name);
  return [rooms[0].id, rooms[rooms.length - 1].id];
}"""


def _jpeg() -> str:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 120, 40)).save(buffer, "JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


@pytest.fixture(scope="module")
def knowledge_server(tmp_path_factory):
    """The web server (fake chat, no key) with the factory building and its own place-knowledge folder."""
    if not (REPO / "twin" / "dist" / "index.html").exists():
        pytest.skip("twin/dist is missing (scripts/build_twin.sh)")
    source = DATA / "dev" / B
    if not source.exists():
        pytest.skip(f"data/dev/{B} is missing (symlink data into the worktree)")
    data = tmp_path_factory.mktemp("knowledge_data")
    shutil.copytree(source, data / "dev" / B)
    knowledge = tmp_path_factory.mktemp("knowledge_store")
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if "API_KEY" not in k and not k.startswith("ANTHROPIC")}
    env["TWIN_KNOWLEDGE_ROOT"] = str(knowledge)
    command = [sys.executable, "-m", "tests.e2e.fake_chat_server", "--data", str(data), "--port", str(port), "--env-file", str(data / "no.env")]
    proc = subprocess.Popen(command, cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/"
    try:
        for _ in range(300):  # a cold start (first import) can take more than 10 s
            if proc.poll() is not None:
                pytest.fail("web server exited early")
            try:
                urllib.request.urlopen(url, timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("web server did not start")
        yield {"url": url, "data": data / "dev" / B, "knowledge": knowledge}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


# Centre the plan on a room (as a person would pan there), so its pin is not under the card or the input.
CENTRE_ON = """(id) => {
  const s = window.__twinStore.getState();
  const space = s.model.spaceById.get(id);
  const c = window.__twinControls.current;
  const target = c.getTarget({ x: 0, y: 0, z: 0, set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; } });
  c.moveTo(space.anchor[0], target.y, -space.anchor[1], false);
}"""


def _centre(page, space_id: str) -> None:
    page.evaluate(CENTRE_ON, space_id)
    _frames(page)


def _shot(page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"))


def _frames(page) -> None:
    page.mouse.move(60, 300)
    page.mouse.wheel(0, 1)  # frames on demand
    page.wait_for_timeout(700)


@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_notes_layer_pin_card_note_here_and_undo(device, knowledge_server, chromium, playwright_instance):  # noqa: F811
    context, page = _open(chromium, playwright_instance, knowledge_server["url"], device)
    try:
        photo_note = page.evaluate(ADD_FACT, ["note", f"Valve lever: pull left first ({device})", _jpeg(), 0])
        issue = page.evaluate(ADD_FACT, ["issue", f"Valve at press 2 drips ({device})", None, 1])
        assert photo_note["photo"] and photo_note["photo"].startswith("/api/facts/photo?")

        # 1. layer off by default: no pins
        _zoom(page, 0, 0.12)
        toggle = page.locator('[data-testid="notes-toggle"]')
        assert toggle.get_attribute("aria-pressed") == "false"
        assert page.evaluate(PINS) == []
        _shot(page, f"{device}-1-layer-off")

        # 2. layer on: pins for the note (with photo) and the issue, laid out without overlaps
        toggle.click()
        shown = _zoom(page, 0, 0.12)
        pins = page.evaluate(PINS)
        by_id = {fid: pin for pin in pins for fid in pin["ids"]}
        assert photo_note["id"] in by_id and by_id[photo_note["id"]]["photo"], pins
        assert issue["id"] in by_id and by_id[issue["id"]]["kind"] == "issue", pins
        assert not shown["overlaps"], shown["overlaps"][:5]
        _shot(page, f"{device}-2-layer-on")

        # 3. tap the pin: text, author, age, photo, history
        _centre(page, photo_note["room"])
        page.locator(f'[data-testid="fact-pin"][data-fact-ids~="{photo_note["id"]}"]').click()
        entry = page.locator(f'[data-testid="fact-entry"][data-fact-id="{photo_note["id"]}"]')
        entry.wait_for(timeout=5000)
        assert entry.locator('[data-testid="fact-text"]').inner_text() == f"Valve lever: pull left first ({device})"
        meta = entry.locator('[data-testid="fact-meta"]').inner_text()
        assert "Techniker A" in meta and meta.startswith("since "), meta
        image = entry.locator('[data-testid="fact-photo"] img')
        image.wait_for(timeout=5000)
        page.wait_for_function("(el) => el.complete && el.naturalWidth > 0", arg=image.element_handle(), timeout=5000)
        page.locator('[data-testid="fact-history-toggle"]').click()
        page.wait_for_selector('[data-testid="fact-history"] li', timeout=5000)
        _shot(page, f"{device}-3-pin-card")
        entry.locator('[data-testid="fact-photo"]').click()
        page.wait_for_selector('[data-testid="photo-viewer"] img', timeout=5000)
        _shot(page, f"{device}-4-photo")
        page.keyboard.press("Escape")
        page.wait_for_selector('[data-testid="photo-viewer"]', state="detached", timeout=5000)

        # the issue's card offers "Resolved" (it goes to Wanda through the chat)
        page.locator('.card-fact .x').click()
        _centre(page, issue["room"])
        page.locator(f'[data-testid="fact-pin"][data-fact-ids~="{issue["id"]}"]').click()
        page.wait_for_selector('[data-testid="fact-resolve"]', timeout=5000)
        page.evaluate("window.__twinStore.getState().select(null)")

        # 4. "Note here" in the room card: name asked once, saved, pin appears, Undo removes it
        room = issue["room"]
        page.evaluate("([id, floor]) => window.__twinStore.getState().select({ kind: 'space', id, floor_id: floor })", [room, issue["floor"]])
        page.locator('[data-testid="note-here"]').click()
        text = f"Key for the cabinet is at the desk ({device})"
        page.locator('[data-testid="note-text"]').fill(text)
        page.locator('[data-testid="note-name"]').fill("Techniker B")
        _shot(page, f"{device}-5-note-here")
        page.locator('[data-testid="note-send"]').click()
        page.wait_for_selector('[data-testid="fact-saved"]', timeout=5000)
        new = page.evaluate("(t) => (window.__twinStore.getState().state.facts || []).find((f) => f.text === t)", text)
        assert new and new["author"] == "Techniker B" and new["anchor"]["space_id"] == room, new
        _frames(page)
        assert any(new["id"] in pin["ids"] for pin in page.evaluate(PINS)), page.evaluate(PINS)
        _shot(page, f"{device}-6-saved-undo")
        page.locator('[data-testid="fact-undo"]').click()
        page.wait_for_selector('[data-testid="fact-saved"]', state="detached", timeout=5000)
        assert page.evaluate("(t) => (window.__twinStore.getState().state.facts || []).some((f) => f.text === t)", text) is False
        _frames(page)
        assert not any(new["id"] in pin["ids"] for pin in page.evaluate(PINS))
        # the name is not asked again
        page.evaluate("([id, floor]) => window.__twinStore.getState().select({ kind: 'space', id, floor_id: floor })", [room, issue["floor"]])
        page.locator('[data-testid="note-here"]').click()
        assert page.locator('[data-testid="note-name"]').count() == 0
        page.evaluate("window.__twinStore.getState().select(null)")

        # 5. the layer switch is remembered per browser
        page.reload()
        page.wait_for_function("window.__twinStore && window.__twinStore.getState().model", timeout=30000)
        page.wait_for_timeout(1500)
        assert page.locator('[data-testid="notes-toggle"]').get_attribute("aria-pressed") == "true"
        assert not page.errors, page.errors
    finally:
        context.close()


@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_timed_closure_says_until_when(device, knowledge_server, chromium, playwright_instance):  # noqa: F811
    from building_agent.knowledge import KnowledgeStore
    from building_agent.time_words import BERLIN
    from starter_agent.building_map import BuildingMap

    bm = BuildingMap.load(knowledge_server["data"] / "building.json")
    store = KnowledgeStore(knowledge_server["knowledge"])
    tomorrow = (datetime.now(BERLIN) + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    fact = store.add(bm, kind="closure", anchor={"element_id": LIFT}, text="Lift broken", valid_to=tomorrow, author="Techniker A")
    context, page = _open(chromium, playwright_instance, knowledge_server["url"], device)
    try:
        state = page.evaluate("window.__twinStore.getState().state")
        assert LIFT in state["closed"] and LIFT in state["closed_until"], state.get("closed_until")
        # glyph tag beside the closed lift (near tier: the lift glyph has room) says until when
        _zoom(page, 0, 0.05)
        tags = page.evaluate("() => [...document.querySelectorAll('[data-zoom-kind=\"closed-tag\"]')].map((el) => el.textContent)")
        assert "Closed until tomorrow 18:00" in tags, tags
        shown = page.evaluate(SHOWN)
        assert not shown["overlaps"], shown["overlaps"][:5]
        _shot(page, f"{device}-7-closed-until")
        # the route card names it with its end
        start, goal = page.evaluate(TWO_F0_ROOMS)
        page.evaluate("([a, b]) => window.__twinStore.getState().route(a, b)", [start, goal])
        page.wait_for_timeout(800)
        avoids = page.locator('[data-testid="route-avoids"]').inner_text()
        assert "Office lift until tomorrow 18:00" in avoids, avoids
        _shot(page, f"{device}-8-route-avoids-until")
        page.evaluate("window.__twinStore.getState().clearRoute()")
        assert not page.errors, page.errors
    finally:
        store.resolve(bm, fact.id, text="test done")
        context.close()
