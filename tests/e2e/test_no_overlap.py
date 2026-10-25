"""No text on text, text on icon or icon on icon in the twin (map labels, POI glyphs, closed chips and tags, route
ends, the tap pin, the "You are here" dot), and no overlapping text inside one UI panel (cards, sheets, chips, rail).

For three kinds of building from data/train (factory, campus offices, apartment house) the audit opens the plan in
2D and 3D (desktop) and 2D (phone, Pixel 7: phones are 2D only), zooms to the far, mid and near tiers (mapZoom.ts)
and builds up the busy state step by step: plain, then a route with the "You are here" dot at its start, then a
tapped room (tap pin and its label), then a closed lift. At every step it takes the screen box of every visible map
label and icon (DOM boxes; three.js markers through the camera) and fails on any pair intersecting by more than
1 px both ways. UI chrome above the map (compass, rail, cards) may cover the map; that is not checked.

Set OVERLAP_SHOTS=<folder> to save a screenshot with the overlapping boxes outlined in red for every finding.
Needs the built page (`scripts/build_twin.sh`), Playwright and Chromium and data/train; skips otherwise.
Run: `uv run pytest -m e2e tests/e2e/test_no_overlap.py`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e.conftest import DATA, REPO, _free_port
from tests.e2e.test_here_ui import NO_AO

pytestmark = pytest.mark.e2e

BUILDINGS = {"factory": "proc-factory-train-015", "campus": "proc-campus-train-003", "apartment": "swiss-920"}
TIERS = {"far": 0.45, "mid": 0.15, "near": 0.06}  # metres per screen pixel (mapZoom.ts: near <= 0.09 < mid <= 0.3;
# far zooms out as far as "area" on floors under ~150 m)
SLACK_PX = 1.0

# Focus the lowest floor with a lift stop and zoom the camera to a scale (metres per pixel) around a point (default
# the floor's centre). 2D: orthographic zoom; 3D: dolly the perspective camera to the distance of that scale.
ZOOM_TO = """([mpp, point]) => {
  const s = window.__twinStore.getState();
  const floor = s.model.floors.find((f) => f.id === window.__auditFloor);
  if (s.focusedFloorId !== floor.id) s.focusFloor(floor.id);
  const c = window.__twinControls.current, cam = c.camera;
  const target = c.getTarget({ x: 0, y: 0, z: 0, set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; } });
  const [x, y] = point || [floor.bounds.cx, floor.bounds.cy];
  if (cam.isOrthographicCamera) c.zoomTo((cam.right - cam.left) / (mpp * innerWidth), false);
  else c.dollyTo(mpp * (cam.view && cam.view.enabled ? cam.view.fullHeight : innerHeight) / (2 * Math.tan(cam.fov * Math.PI / 360)), false);
  c.moveTo(x, target.y, -y, false);
}"""

# Pick the floor (lowest with a lift stop), two routable-looking rooms on it, a lift and a tap room.
PLAN = """() => {
  const m = window.__twinStore.getState().model;
  const lifts = [...m.connectorById.values()].filter((c) => c.kind === 'lift');
  const floors = [...m.floors].sort((a, b) => a.level - b.level);
  const liftOn = (f) => lifts.find((c) => c.space_ids.some((id) => m.spaceById.get(id)?.floor_id === f.id));
  const floor = floors.find((f) => f.level >= 0 && liftOn(f)) || floors.find(liftOn) || floors[0];
  window.__auditFloor = floor.id;
  const rooms = floor.spaces.filter((s) => s.type === 'room' && s.name && !m.connectorBySpace.has(s.id)).sort((a, b) => b.area_m2 - a.area_m2 || a.id.localeCompare(b.id));
  const lift = liftOn(floor);
  return { floor: floor.id, size: floor.bounds.size, rooms: rooms.map((r) => [r.id, r.anchor]), lift: lift ? lift.id : null };
}"""

# Every visible map label and icon (screen boxes), and the overlapping pairs.
MAP_BOXES = """() => {
  const canvas = document.querySelector('canvas');
  const W = innerWidth, H = innerHeight;
  const visible = (el) => {
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.05) return false;
    }
    return true;
  };
  // map labels and icons live in drei <Html> wrappers, which the camera moves with an inline translate3d
  const inMap = (el) => { for (let e = el; e && e !== document.body; e = e.parentElement) if (e.style && e.style.transform.includes('translate3d')) return true; return false; };
  const items = [];
  const seen = new Set();
  const add = (name, el, r) => {
    if (r.width < 1 || r.height < 1 || r.right < 0 || r.bottom < 0 || r.left > W || r.top > H) return;
    items.push({ name, el, box: { left: r.left, top: r.top, right: r.right, bottom: r.bottom } });
  };
  const selectors = '[data-zoom-kind], .label, .chip, .floor-badge, .found-dot, .walk-estimated';
  for (const el of document.querySelectorAll(selectors)) {
    if (!inMap(el) || seen.has(el)) continue;
    // one item per marker: the outermost matching element (a chip's text is part of the chip)
    if (el.parentElement && el.parentElement.closest(selectors)) continue;
    seen.add(el);
    if (!visible(el)) continue;
    const kind = el.dataset.zoomKind || el.className.split(' ')[0];
    const target = kind.startsWith('poi') && el.firstElementChild ? el.firstElementChild : el;
    add(`${kind} "${(el.textContent || el.getAttribute('title') || '').trim().slice(0, 40)}"`, el, target.getBoundingClientRect());
  }
  // three.js markers drawn at a constant size on screen (markerLayout.tsx), projected through the camera
  const scene = window.__twinScene, c = window.__twinControls.current, cam = c.camera;
  cam.updateMatrixWorld();
  const rect = canvas.getBoundingClientRect();
  const project = (x, y, z) => {
    const v = new (scene.position.constructor)(x, y, z).project(cam);
    return [rect.left + (v.x + 1) / 2 * rect.width, rect.top + (1 - v.y) / 2 * rect.height];
  };
  // metres per screen px; CameraRig renders a crop of a taller frame while a sheet covers the canvas
  const frameH = cam.view && cam.view.enabled ? cam.view.fullHeight : rect.height;
  const mpp = (wx, wy, wz) => cam.isOrthographicCamera
    ? (cam.top - cam.bottom) / cam.zoom / frameH
    : 2 * Math.hypot(cam.position.x - wx, cam.position.y - wy, cam.position.z - wz) * Math.tan(cam.fov * Math.PI / 360) / frameH;
  // the size a marker is really drawn at: its ScreenSized group scales px to metres (markerLayout.tsx)
  const drawn = (obj) => { let s = null; obj.traverse((o) => { if (s === null && o !== obj && o.scale.x !== 1 && o.scale.x === o.scale.z) s = o.scale.x; }); return s; };
  let sized = null;
  const flatBox = (x, y, z, rpx) => { // a disc of rpx screen px lying on the floor
    const r = rpx * (sized || mpp(x, y, z));
    const pts = [[r, 0], [-r, 0], [0, r], [0, -r]].map(([dx, dz]) => project(x + dx, y, z + dz));
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    return { left: Math.min(...xs), right: Math.max(...xs), top: Math.min(...ys), bottom: Math.max(...ys) };
  };
  const world = (obj) => { obj.updateWorldMatrix(true, false); const e = obj.matrixWorld.elements; return [e[12], e[13], e[14]]; };
  const marker = (name, box) => {
    const r = { ...box, width: box.right - box.left, height: box.bottom - box.top };
    add(name, null, r);
  };
  scene.traverse((obj) => {
    if (!obj.visible) return;
    if (!['here-dot', 'route-start', 'route-end', 'tap-pin'].includes(obj.name)) return;
    sized = drawn(obj);
    if (obj.name === 'route-end') { // an upright pin: its px sizes grow with the drawn scale like the discs
      const [wx, wy, wz] = world(obj);
      const k = sized ? sized / mpp(wx, wy, wz) : 1;
      const [x, y] = project(wx, wy, wz);
      marker('marker route-end', { left: x - 8 * k, right: x + 8 * k, top: y - 21.5 * k, bottom: y });
      return;
    }
    if (obj.name === 'here-dot') marker('marker here-dot', flatBox(...world(obj), 9));
    if (obj.name === 'route-start' && obj.children.length) marker('marker route-start', flatBox(...world(obj), 6));
    if (obj.name === 'tap-pin') {
      const [x, y, z] = world(obj);
      marker('marker tap-pin', flatBox(x, y, z, cam.isOrthographicCamera ? 16.5 : 11));
      if (!cam.isOrthographicCamera) { // the stalk's head (a 0.2 m sphere at 1.15 m)
        const [hx, hy] = project(x, y + 1.15, z);
        const hr = 0.2 / mpp(x, y + 1.15, z);
        marker('marker tap-head', { left: hx - hr, right: hx + hr, top: hy - hr, bottom: hy + hr });
      }
    }
  });
  const overlaps = [];
  for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) {
    const a = items[i], b = items[j];
    if (a.el && b.el && (a.el.contains(b.el) || b.el.contains(a.el))) continue;
    const dx = Math.min(a.box.right, b.box.right) - Math.max(a.box.left, b.box.left);
    const dy = Math.min(a.box.bottom, b.box.bottom) - Math.max(a.box.top, b.box.top);
    if (dx > %(slack)s && dy > %(slack)s) overlaps.push({ a: a.name, b: b.name, boxes: [a.box, b.box], dx: Math.round(dx), dy: Math.round(dy) });
  }
  return { count: items.length, names: items.map((i) => i.name).slice(0, 12), tier: window.__twinMapZoom && window.__twinMapZoom.tier, overlaps };
}""".replace("%(slack)s", str(SLACK_PX))

# Text inside one UI panel (outside the map): the line boxes of different text nodes must not intersect. Clipped by
# every ancestor that hides its overflow (ellipsis, scroll lists). A panel is the outermost positioned ancestor.
UI_BOXES = """() => {
  const W = innerWidth, H = innerHeight;
  // map labels and icons live in drei <Html> wrappers, which the camera moves with an inline translate3d
  const inMap = (el) => { for (let e = el; e && e !== document.body; e = e.parentElement) if (e.style && e.style.transform.includes('translate3d')) return true; return false; };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const texts = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.textContent.trim()) continue;
    const el = node.parentElement;
    if (!el || inMap(el) || el.closest('script, style, title, svg')) continue;
    let hidden = false, panel = null;
    let clip = { left: 0, top: 0, right: W, bottom: H };
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.05) { hidden = true; break; }
      if (cs.overflow !== 'visible' || cs.overflowX !== 'visible' || cs.overflowY !== 'visible') {
        const r = e.getBoundingClientRect();
        clip = { left: Math.max(clip.left, r.left), top: Math.max(clip.top, r.top), right: Math.min(clip.right, r.right), bottom: Math.min(clip.bottom, r.bottom) };
      }
      if (cs.position === 'fixed' || cs.position === 'absolute') panel = e;
    }
    if (hidden) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    for (const r of range.getClientRects()) {
      const box = { left: Math.max(r.left, clip.left), top: Math.max(r.top, clip.top), right: Math.min(r.right, clip.right), bottom: Math.min(r.bottom, clip.bottom) };
      if (box.right - box.left < 1 || box.bottom - box.top < 1) continue;
      texts.push({ node, panel, box, name: `${el.tagName.toLowerCase()}.${(el.className && el.className.baseVal === undefined ? el.className : '').split(' ')[0]} "${node.textContent.trim().slice(0, 30)}"` });
    }
  }
  const overlaps = [];
  for (let i = 0; i < texts.length; i++) for (let j = i + 1; j < texts.length; j++) {
    const a = texts[i], b = texts[j];
    if (a.node === b.node || a.panel !== b.panel) continue;
    const dx = Math.min(a.box.right, b.box.right) - Math.max(a.box.left, b.box.left);
    const dy = Math.min(a.box.bottom, b.box.bottom) - Math.max(a.box.top, b.box.top);
    if (dx > %(slack)s && dy > %(slack)s) overlaps.push({ a: a.name, b: b.name, boxes: [a.box, b.box], dx: Math.round(dx), dy: Math.round(dy) });
  }
  return overlaps;
}""".replace("%(slack)s", str(SLACK_PX))

OUTLINE = """(boxes) => {
  document.querySelectorAll('.audit-outline').forEach((el) => el.remove());
  for (const b of boxes) {
    const el = document.createElement('div');
    el.className = 'audit-outline';
    Object.assign(el.style, { position: 'fixed', left: b.left + 'px', top: b.top + 'px', width: (b.right - b.left) + 'px',
      height: (b.bottom - b.top) + 'px', outline: '1.5px solid red', zIndex: 99999, pointerEvents: 'none' });
    document.body.appendChild(el);
  }
}"""


@pytest.fixture(scope="module")
def train_url(tmp_path_factory):
    """The web server (fake chat) with the three train buildings."""
    if not (REPO / "twin" / "dist" / "index.html").exists():
        pytest.skip("twin/dist is missing (scripts/build_twin.sh)")
    data = tmp_path_factory.mktemp("overlap_data")
    for building in BUILDINGS.values():
        source = DATA / "train" / building
        if not source.exists():
            pytest.skip(f"data/train/{building} is missing (symlink data into the worktree)")
        shutil.copytree(source, data / "train" / building)
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if "API_KEY" not in k and not k.startswith("ANTHROPIC")}
    command = [sys.executable, "-m", "tests.e2e.fake_chat_server", "--data", str(data), "--port", str(port)]
    command += ["--env-file", str(data / "no.env")]
    proc = subprocess.Popen(command, cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/"
    try:
        for _ in range(900):  # a loaded machine needs a while
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


def _open(chromium, playwright_instance, url, device, building):
    options = (
        dict(playwright_instance.devices["Pixel 7"])
        if device == "phone"
        else {"viewport": {"width": 1280, "height": 800}, "device_scale_factor": 1}
    )
    context = chromium.new_context(**options)
    context.add_init_script(NO_AO)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(f"{url}?building=train/{building}", timeout=60000)
    page.wait_for_function(
        "window.__twinStore && window.__twinStore.getState().model && window.__twinControls && window.__twinControls.current",
        timeout=60000,
    )
    page.wait_for_timeout(2500)
    return context, page


def _settle(page, ms=1200):
    page.mouse.move(5, 400)
    page.mouse.wheel(0, 1)  # the phone renders on demand: a tiny wheel step asks for frames
    page.wait_for_timeout(ms)


def _audit(page, where: str, findings: list[str]) -> None:
    shown = page.evaluate(MAP_BOXES)
    ui = page.evaluate(UI_BOXES)
    found = [("map", o) for o in shown["overlaps"]] + [("ui", o) for o in ui]
    for scope, o in found:
        # The "You are here" dot and the tap pin are both placed by the user; a pin standing on the dot (a tap next
        # to yourself, seen from far away) is normal map behaviour, nothing can yield.
        if {o["a"], o["b"]} == {"marker here-dot", "marker tap-pin"}:
            continue
        findings.append(f"{where} [{scope}, tier {shown['tier']}]: {o['a']} / {o['b']} ({o['dx']}x{o['dy']} px)")
    if os.environ.get("OVERLAP_DEBUG"):
        print(where, shown["tier"], shown["count"], shown.get("names"), len(found))
    folder = os.environ.get("OVERLAP_SHOTS")
    if folder and (found or os.environ.get("OVERLAP_DEBUG")):
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.evaluate(OUTLINE, [box for _, o in found for box in o["boxes"]])
        page.screenshot(path=str(Path(folder) / f"{where.replace(' ', '_').replace('/', '-')}.png"))
        page.evaluate(OUTLINE, [])


CASES = [
    (kind, device, view)
    for kind in BUILDINGS
    for device, view in (("desktop", "2d"), ("desktop", "3d"), ("phone", "2d"))
]


@pytest.mark.parametrize(("kind", "device", "view"), CASES, ids=[f"{k}-{d}-{v}" for k, d, v in CASES])
def test_nothing_overlaps(kind, device, view, train_url, chromium, playwright_instance):
    building = BUILDINGS[kind]
    context, page = _open(chromium, playwright_instance, train_url, device, building)
    findings: list[str] = []
    try:
        page.evaluate("() => window.__twinStore.getState().reset()")  # the server keeps state between cases
        page.evaluate(f"window.__twinStore.getState().setViewMode('{view}')")
        page.wait_for_timeout(1500)
        plan = page.evaluate(PLAN)
        rooms = plan["rooms"]
        assert len(rooms) >= 3, plan

        # mid needs the floor to cover more than 480 px (else it is the area overview, mapZoom.ts)
        tiers = {**TIERS, "mid": max(0.095, min(0.29, plan["size"] / 560))}

        def sweep(state: str, focus=None) -> None:
            for tier, mpp in tiers.items():
                page.evaluate(ZOOM_TO, [mpp, focus if tier == "near" else None])
                _settle(page)
                _audit(page, f"{kind} {device} {view} {state} {tier}", findings)

        sweep("plain")
        # a route between two of the larger rooms, "You are here" at its start
        start, goal = rooms[0], rooms[min(3, len(rooms) - 1)]
        floor = plan["floor"]
        page.evaluate(
            "([s, p, f]) => window.__twinStore.getState().setHere({ space_id: s, floor_id: f, point: p })",
            [start[0], start[1], floor],
        )
        page.evaluate("([a, b]) => window.__twinStore.getState().route(a, b)", [start[0], goal[0]])
        page.wait_for_timeout(1500)
        sweep("route", goal[1])
        # a tapped room: the tap pin and its label
        tapped = rooms[1]
        page.evaluate(
            "([id, p, f]) => window.__twinStore.getState().select({ kind: 'space', id, floor_id: f, point: p })",
            [tapped[0], tapped[1], floor],
        )
        page.wait_for_timeout(800)
        sweep("route+tap", tapped[1])
        # a closed lift
        if plan["lift"]:
            page.evaluate("(id) => window.__twinStore.getState().setClosed(id, true)", plan["lift"])
            page.wait_for_timeout(1000)
            lift_stop = page.evaluate(
                "(id) => { const m = window.__twinStore.getState().model; const c = m.connectorById.get(id);"
                " const s = c.space_ids.map((x) => m.spaceById.get(x)).find((x) => x.floor_id === window.__auditFloor);"
                " return s ? s.anchor : null; }",
                plan["lift"],
            )
            sweep("route+tap+closed", lift_stop)
            page.evaluate("(id) => window.__twinStore.getState().setClosed(id, false)", plan["lift"])
        assert not page.errors, page.errors
    finally:
        context.close()
    assert not findings, f"{len(findings)} overlaps:\n" + "\n".join(findings[:60])
