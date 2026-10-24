"""Semantic zoom of the 2D plan (docs/specs/semantic-zoom.md): zooming from far to near on the factory hall
(proc-factory-dev-012, floor 0) adds new kinds of information on every tier, and no two labels overlap.

- area (overview): area names ("Production", "Logistics"), no single room names, no amenity symbols
- mid: room names and amenity symbols (coffee, first aid, fire extinguisher)
- near: machine names, the second line under room names ("Production zone · 291 m²") and wide door widths

Desktop (1280x800) and phone (Pixel 7) alike: only the scale decides. Needs the built page (`scripts/build_twin.sh`),
Playwright and Chromium (`uv sync --group e2e`, `uv run playwright install chromium`) and data/dev; skips otherwise.
Run: `uv run pytest -m e2e tests/e2e/test_semantic_zoom.py`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e.conftest import DATA, REPO, _free_port

pytestmark = pytest.mark.e2e

BUILDING = "proc-factory-dev-012"

# Zoom the plan of a floor to a scale (metres per screen pixel), centred on the floor.
ZOOM_TO = """([level, mpp]) => {
  const s = window.__twinStore.getState();
  const floor = s.model.floors.find((f) => f.level === level);
  if (s.focusedFloorId !== floor.id) s.focusFloor(floor.id);
  const c = window.__twinControls.current, cam = window.__twinCamera;
  const target = c.getTarget({ x: 0, y: 0, z: 0, set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; } });
  c.zoomTo((cam.right - cam.left) / (mpp * innerWidth), false);
  c.moveTo(floor.bounds.cx, target.y, -floor.bounds.cy, false);
}"""

# What the plan shows: the zoom tier, label counts per kind, and label boxes that overlap on screen (> 1 px both ways).
SHOWN = """() => {
  const boxes = [];
  const kinds = {};
  for (const el of document.querySelectorAll('[data-zoom-kind]')) {
    const kind = el.dataset.zoomKind;
    kinds[kind] = (kinds[kind] || 0) + 1;
    const r = (kind.startsWith('poi') ? el.firstElementChild : el).getBoundingClientRect();
    if (r.width && r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight) boxes.push([kind + ' ' + el.textContent, r]);
  }
  const overlaps = [];
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i][1], b = boxes[j][1];
    if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1)
      overlaps.push(boxes[i][0] + ' / ' + boxes[j][0]);
  }
  return { tier: window.__twinMapZoom && window.__twinMapZoom.tier, kinds, overlaps };
}"""

AMENITIES = ("poi-coffee", "poi-firstaid", "poi-extinguisher", "poi-printer")


@pytest.fixture(scope="module")
def factory_url(tmp_path_factory):
    """The web server (fake chat) with only the factory building."""
    if not (REPO / "twin" / "dist" / "index.html").exists():
        pytest.skip("twin/dist is missing (scripts/build_twin.sh)")
    source = DATA / "dev" / BUILDING
    if not source.exists():
        pytest.skip(f"data/dev/{BUILDING} is missing (symlink data into the worktree)")
    data = tmp_path_factory.mktemp("zoom_data")
    shutil.copytree(source, data / "dev" / BUILDING)
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if "API_KEY" not in k and not k.startswith("ANTHROPIC")}
    command = [sys.executable, "-m", "tests.e2e.fake_chat_server", "--data", str(data), "--port", str(port), "--env-file", str(data / "no.env")]
    proc = subprocess.Popen(command, cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


@pytest.fixture(scope="module")
def chromium(playwright_instance):
    try:
        browser = playwright_instance.chromium.launch()
    except Exception as error:  # noqa: BLE001 - missing browser binaries
        pytest.skip(f"chromium not installed: {str(error)[:80]}")
    yield browser
    browser.close()


def _open(chromium, playwright_instance, url, device, reduced_motion="no-preference"):
    options = dict(playwright_instance.devices["Pixel 7"]) if device == "phone" else {"viewport": {"width": 1280, "height": 800}, "device_scale_factor": 1}
    context = chromium.new_context(**options, reduced_motion=reduced_motion)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(f"{url}?building=dev/{BUILDING}")
    page.wait_for_function(
        "window.__twinStore && window.__twinStore.getState().model && window.__twinControls && window.__twinControls.current",
        timeout=30000,
    )
    page.evaluate("window.__twinStore.getState().setViewMode('2d')")
    page.wait_for_timeout(2500)
    return context, page


def _zoom(page, level, mpp):
    page.evaluate(ZOOM_TO, [level, mpp])
    page.mouse.move(60, 300)
    page.mouse.wheel(0, 1)  # the phone renders on demand: a tiny wheel step asks for frames
    page.wait_for_timeout(900)
    return page.evaluate(SHOWN)


@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_each_zoom_level_adds_its_kinds_without_overlap(device, factory_url, chromium, playwright_instance):
    context, page = _open(chromium, playwright_instance, factory_url, device)
    try:
        area = _zoom(page, 0, 0.6)  # as far out as the plan goes
        mid = _zoom(page, 0, 0.12)
        near = _zoom(page, 0, 0.05)
        for name, shown in (("area", area), ("mid", mid), ("near", near)):
            assert shown["tier"] == name, shown
            assert not shown["overlaps"], f"{name}: overlapping labels {shown['overlaps'][:5]}"
        # 1. overview: area names instead of single room names, no amenity symbols yet
        assert area["kinds"].get("area", 0) >= 1, area
        assert area["kinds"].get("room", 0) == 0, area
        assert not any(area["kinds"].get(kind) for kind in AMENITIES), area
        # 2. mid: room names and amenity symbols, no area names
        assert mid["kinds"].get("room", 0) >= 1 and mid["kinds"].get("area", 0) == 0, mid
        assert any(mid["kinds"].get(kind) for kind in AMENITIES), mid
        assert mid["kinds"].get("sub", 0) == 0 and mid["kinds"].get("door", 0) == 0, mid
        # 3. near: machine names, a second line under room names, door widths
        assert near["kinds"].get("thing", 0) >= 1, near
        assert near["kinds"].get("sub", 0) >= 1, near
        assert near["kinds"].get("door", 0) >= 1, near
        assert not page.errors, page.errors
    finally:
        context.close()


@pytest.mark.parametrize("reduced", [False, True])
def test_new_labels_fade_in_unless_reduced_motion(reduced, factory_url, chromium, playwright_instance):
    context, page = _open(chromium, playwright_instance, factory_url, "desktop", "reduce" if reduced else "no-preference")
    try:
        _zoom(page, 0, 0.05)
        animation = page.evaluate(
            "() => { const s = getComputedStyle(document.querySelector('.zoom-fade')); return [s.animationName, s.animationDuration]; }"
        )
        if reduced:
            assert animation[0] == "none", animation
        else:
            assert animation[0] == "zoom-fade-in", animation
            assert 0.15 <= float(animation[1].rstrip("s")) <= 0.2, animation
    finally:
        context.close()


def test_room_card_lists_the_equipment(factory_url, chromium, playwright_instance):
    context, page = _open(chromium, playwright_instance, factory_url, "desktop")
    try:
        # the hall zone with the most machines: tap it through the store (as a tap on the plan does)
        space = page.evaluate(
            """() => {
              const m = window.__twinStore.getState().model;
              const counts = {};
              for (const a of m.assetById.values()) if (a.category === 'machine') counts[a.space_id] = (counts[a.space_id] || 0) + 1;
              const id = Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0];
              const s = m.spaceById.get(id);
              window.__twinStore.getState().select({ kind: 'space', id, floor_id: s.floor_id });
              return id;
            }"""
        )
        line = page.get_by_test_id("card-equipment")
        line.wait_for(timeout=5000)
        text = line.inner_text()
        assert text, space
        assert len(text.split(", ")) <= 7, text  # at most 6 entries and "+n more"
    finally:
        context.close()
