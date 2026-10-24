"""Mobile smoke tests for the twin page (twin/), worker profile: the phone layout, route flow, guide card, chat with
the keyboard, audio unlock, wake lock, landscape and safe areas. Requirements: docs/mobile-audit.md (written for the
old page, re-checked against twin/) and twin/MOBILE.md.

Pixel 7 (Chromium, 412 px) and iPhone 14 (WebKit, 390 px) with touch on. The chat turn is faked
(tests/e2e/fake_chat_server.py), so no API key is needed and no real chat message is ever sent. The guided walk is
injected into the store (the real one needs the model); the keyboard is simulated through a fake visualViewport.
Needs twin/dist (scripts/build_twin.sh). Run: scripts/mobile_smoke.sh
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

pytestmark = pytest.mark.e2e


def audit(item: str, title: str):
    return pytest.mark.audit(item, title)


# ---------- page probes ----------

# Store access: wait_for_function would call a returned function, so never return useTwin itself.
STATE = "() => { const s = window.__twinStore.getState(); return { selection: s.selection, topInset: s.topInset, bottomInset: s.bottomInset, position: s.state && s.state.position, route: s.state && s.state.route && s.state.route.ok, directions: !!s.directions }; }"

BOX = """(sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect();
  return r.width && r.height ? { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height } : null; }"""

# Visible buttons, inputs and selects under 44 px whose tap area (probed 21 px around the centre) is not 44 px either.
SMALL_TARGETS = """() => {
  const out = [];
  for (const el of document.querySelectorAll('button, select, input, [role=radio]')) {
    if (el.closest('[hidden], .omnibox.collapsed .omnibox-input')) continue;
    if (el.classList.contains('sheet-handle')) continue; // keyboard path; touch drags the whole grip
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0' || r.width === 0 || r.height === 0) continue;
    if (r.right < 0 || r.bottom < 0 || r.left > innerWidth || r.top > innerHeight) continue;
    if (el.tagName === 'SELECT' && cs.opacity === '0') continue;
    if (el.tagName === 'INPUT' && el.type === 'checkbox') { const label = el.closest('label'); if (label && label.getBoundingClientRect().height >= 44) continue; }
    if (r.width >= 44 && r.height >= 44) continue;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const probes = [[cx, cy - 21], [cx, cy + 21], [cx - 21, cy], [cx + 21, cy]];
    const ok = probes.every(([x, y]) => { const hit = document.elementFromPoint(x, y); return hit && (hit === el || el.contains(hit) || (el.tagName === 'SELECT' && hit.closest('label') === el.closest('label'))); });
    if (ok) continue;
    const name = el.getAttribute('aria-label') || el.textContent.trim().slice(0, 20) || el.className;
    out.push(`${el.tagName.toLowerCase()} "${name}" ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  return out;
}"""

# Screen box (client px) of world points on the focused floor, through the scene camera.
PROJECT = """(points) => {
  const cam = window.__twinCamera; cam.updateMatrixWorld();
  const rect = document.querySelector('canvas').getBoundingClientRect();
  const V = cam.position.constructor; let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
  for (const [x, z] of points) { const v = new V(x, 0, -z).project(cam);
    const px = rect.left + (v.x + 1) / 2 * rect.width, py = rect.top + (1 - v.y) / 2 * rect.height;
    minX = Math.min(minX, px); maxX = Math.max(maxX, px); minY = Math.min(minY, py); maxY = Math.max(maxY, py); }
  return { left: minX, top: minY, right: maxX, bottom: maxY };
}"""

FLOOR_CORNERS = """() => { const s = window.__twinStore.getState(); const f = s.model.floorById.get(s.focusedFloorId);
  const b = f.bounds; return [[b.minX, b.minY], [b.maxX, b.maxY], [b.minX, b.maxY], [b.maxX, b.minY]]; }"""

ROUTE_POINTS = """() => { const s = window.__twinStore.getState(); const r = s.state && s.state.route; if (!r || !r.segments) return [];
  return r.segments.filter((g) => g.floor_id === s.focusedFloorId).flatMap((g) => g.points); }"""

# A fake visualViewport whose height the test sets (window.__kb(px) = a keyboard that tall, 0 = closed).
FAKE_KEYBOARD = """
(() => {
  const vv = new EventTarget();
  vv.scale = 1; vv.offsetTop = 0; vv.offsetLeft = 0; vv.pageTop = 0;
  Object.defineProperty(vv, 'height', { get: () => window.__vvh ?? window.innerHeight });
  Object.defineProperty(vv, 'width', { get: () => window.innerWidth });
  Object.defineProperty(window, 'visualViewport', { value: vv, configurable: true });
  window.__kb = (h) => { window.__vvh = h ? window.innerHeight - h : undefined; vv.dispatchEvent(new Event('resize')); };
})();
"""

# Spies: wake lock requests/releases and media play() calls. window.__refuse = n refuses the next n play() calls
# (iOS refuses a play() outside a gesture it accepts).
SPIES = """
  window.__wake = 0; window.__released = 0; window.__plays = 0; window.__refuse = 0;
  const wl = { request() { window.__wake++; const lock = { _l: [], release() { window.__released++; this._l.forEach((f) => f()); return Promise.resolve(); }, addEventListener(t, f) { this._l.push(f); } }; return Promise.resolve(lock); } };
  Object.defineProperty(navigator, 'wakeLock', { value: wl, configurable: true });
  HTMLMediaElement.prototype.play = function () { window.__plays++; if (window.__refuse > 0) { window.__refuse--; return Promise.reject(new DOMException('no gesture', 'NotAllowedError')); } return Promise.resolve(); };
"""


def box(page, selector: str):
    return page.evaluate(BOX, selector)


def state(page) -> dict:
    return page.evaluate(STATE)


def tap_room(page, avoid: str | None = None) -> str:
    """Tap a grid of spots on the plan until one selects a room (not `avoid`); returns the room id."""
    size = page.viewport_size
    for fy in (0.35, 0.45, 0.3, 0.4, 0.5, 0.25, 0.55):
        for fx in (0.5, 0.35, 0.65, 0.4, 0.6, 0.3, 0.7):
            page.touchscreen.tap(size["width"] * fx, size["height"] * fy)
            page.wait_for_timeout(200)
            sel = state(page)["selection"]
            if sel and sel["kind"] in ("space", "point"):
                room = sel["id"] if sel["kind"] == "space" else sel.get("space_id")
                if room and room != avoid:
                    page.wait_for_timeout(600)  # sheet animation and camera
                    return room
                page.evaluate("() => window.__twinStore.getState().select(null)")
                page.wait_for_timeout(150)
    pytest.fail("no tap selected a room")


def set_position(page) -> str:
    room = tap_room(page)
    page.get_by_role("button", name="I'm here").tap()
    page.wait_for_function("() => !!window.__twinStore.getState().state?.position", timeout=8000)
    page.evaluate("() => window.__twinStore.getState().select(null)")
    page.wait_for_timeout(300)
    return room


def open_route(page) -> tuple[str, str]:
    here = set_position(page)
    to = tap_room(page, avoid=here)
    page.get_by_role("button", name="Route", exact=True).tap()
    page.wait_for_function("() => !!window.__twinStore.getState().state?.route?.ok", timeout=8000)
    page.wait_for_timeout(1200)  # the camera frames the route
    return here, to


def inject_guide(page, here: str, to: str) -> None:
    page.evaluate(
        """([a, b]) => { const st = window.__twinStore; st.getState().closeDirections(true);
           st.setState({ state: { ...st.getState().state, guide: { active: true, step_index: 1, step_count: 4,
             leg: { from_space_id: a, to_space_id: b, points: [], segments: [] }, target_space_id: b } } }); }""",
        [here, to],
    )
    page.wait_for_timeout(600)


def end_guide(page) -> None:
    page.evaluate("() => { const st = window.__twinStore; st.setState({ state: { ...st.getState().state, guide: null } }); }")
    page.wait_for_timeout(300)


def overflow(page) -> dict:
    return page.evaluate("() => ({scroll: document.documentElement.scrollWidth, inner: window.innerWidth})")


def overlaps(a, b) -> bool:
    return a["left"] < b["right"] and a["right"] > b["left"] and a["top"] < b["bottom"] and a["bottom"] > b["top"]


# ---------- load ----------


@audit("ok", "viewport meta with viewport-fit=cover")
def test_viewport_meta(open_page):
    content = open_page(wait_plan=False).evaluate("() => document.querySelector('meta[name=viewport]')?.content || ''")
    assert "width=device-width" in content and "initial-scale=1" in content and "viewport-fit=cover" in content, content


@audit("ok", "worker profile, 2D only, no 3D toggle")
def test_worker_profile_2d(open_page):
    page = open_page()
    s = page.evaluate("() => { const s = window.__twinStore.getState(); return [s.profile, s.viewMode]; }")
    assert s == ["worker", "2d"], s
    assert page.locator(".rail-view").count() == 0


@audit("ok", "no horizontal overflow, no errors (portrait and landscape)")
@pytest.mark.parametrize("landscape", [False, True], ids=["portrait", "landscape"])
def test_no_overflow_no_errors(open_page, landscape):
    page = open_page(landscape=landscape)
    sizes = overflow(page)
    assert sizes["scroll"] <= sizes["inner"], sizes
    assert not page.errors, page.errors
    assert not page.console_errors, page.console_errors


@audit("1", "chat input at least 16 px (no iOS zoom)")
def test_chat_input_font_size(open_page):
    page = open_page()
    page.get_by_role("button", name="Chat").tap()
    page.wait_for_timeout(300)
    size = page.evaluate("() => parseFloat(getComputedStyle(document.querySelector('.omnibox-input input')).fontSize)")
    assert size >= 16, f"chat input is {size}px"


@audit("8", "touch-action: manipulation (no double-tap zoom)")
def test_touch_action_manipulation(open_page):
    values = open_page().evaluate("() => [document.documentElement, document.body].map((e) => getComputedStyle(e).touchAction)")
    assert any(v in ("manipulation", "none") for v in values), values


# ---------- room tap: card, label, framing ----------


@audit("3", "room tap: bottom card with Route and I'm here, plan stays visible")
def test_room_tap_card(open_page):
    page = open_page()
    tap_room(page)
    assert page.get_by_role("button", name="Route", exact=True).is_visible()
    assert page.get_by_role("button", name="I'm here").is_visible()
    sheet = box(page, ".phone-sheet")
    assert sheet["height"] <= page.viewport_size["height"] * 0.45 + 1, sheet


@audit("fix1", "tapped room has its name on the plan, no other label on it")
def test_selected_room_label(open_page):
    page = open_page()
    room = tap_room(page)
    page.wait_for_timeout(400)
    labels = page.evaluate(
        """(id) => [...document.querySelectorAll('.label')].map((e) => { const r = e.getBoundingClientRect();
            return { id: e.dataset.labelSpace, left: r.left, top: r.top, right: r.right, bottom: r.bottom }; })""",
        room,
    )
    own = [label for label in labels if label["id"] == room]
    assert len(own) == 1, f"{len(own)} labels for the tapped room {room}"
    others = [label for label in labels if label["id"] != room and overlaps(label, own[0])]
    assert not others, f"labels on the tapped room's label: {others}"


@audit("fix2", "fitted plan stays between header and bottom card")
def test_plan_between_header_and_card(open_page):
    page = open_page()
    tap_room(page)
    page.evaluate("() => window.__twinStore.getState().requestCamera({ kind: 'home' })")
    page.wait_for_timeout(1500)
    header = box(page, ".phone-back")
    sheet = box(page, ".phone-sheet")
    assert state(page)["topInset"] >= header["bottom"], "topInset does not cover the header"
    plan = page.evaluate(PROJECT, page.evaluate(FLOOR_CORNERS))
    assert plan["top"] >= header["bottom"] - 2, f"plan top {plan['top']:.0f} is under the header ({header['bottom']:.0f})"
    assert plan["bottom"] <= sheet["top"] + 2, f"plan bottom {plan['bottom']:.0f} is under the card ({sheet['top']:.0f})"


# ---------- route, directions, guide ----------


@audit("route", "Route opens directions; the route sits between top and bottom sheet")
def test_route_flow(open_page):
    page = open_page()
    open_route(page)
    top = box(page, ".directions")
    sheet = box(page, ".phone-sheet")
    assert top and sheet, "directions panel or summary card missing"
    assert page.get_by_role("button", name="Start", exact=True).is_visible()
    route = page.evaluate(PROJECT, page.evaluate(ROUTE_POINTS))
    middle = (route["top"] + route["bottom"]) / 2
    assert top["bottom"] - 2 <= middle <= sheet["top"] + 2, f"route centre {middle:.0f} not between {top['bottom']:.0f} and {sheet['top']:.0f}"
    rail = box(page, ".floorrail")
    assert rail and rail["top"] >= top["bottom"] and rail["height"] >= 44, f"floor rail {rail} under or squeezed by the directions sheet"
    assert not page.evaluate(SMALL_TARGETS), page.evaluate(SMALL_TARGETS)
    page.get_by_role("button", name="Close directions").tap()
    page.wait_for_timeout(500)
    assert not state(page)["directions"]
    assert state(page)["topInset"] >= box(page, ".phone-back")["bottom"], "topInset not back to the header after closing"


@audit("route", "guide card: Back/Next/Stop reachable, 44 px, inside the screen")
def test_guide_card(open_page):
    page = open_page()
    here, to = open_route(page)
    inject_guide(page, here, to)
    page.locator(".phone-sheet").tap()  # peek -> open
    page.wait_for_timeout(400)
    height = page.viewport_size["height"]
    for name in ("Back", "Next", "Stop"):
        button = page.locator(".card-guide .card-actions button", has_text=name)
        b = button.bounding_box()
        assert b and b["height"] >= 44 and b["y"] + b["height"] <= height, f"{name}: {b}"
    assert not page.evaluate(SMALL_TARGETS), page.evaluate(SMALL_TARGETS)


@audit("2", "wake lock while guiding, released after")
def test_wake_lock_while_guiding(open_page):
    page = open_page(SPIES)
    here, to = open_route(page)
    before = page.evaluate("() => window.__wake")
    inject_guide(page, here, to)
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__wake") > before, "no wake lock request while guiding"
    end_guide(page)
    assert page.evaluate("() => window.__released") >= 1, "wake lock not released after guiding"


@audit("2", "audio unlocked on the first tap, retried when refused")
def test_audio_unlock(open_page):
    page = open_page(SPIES + "window.__refuse = 1000;")  # the browser refuses every play() in the first tap
    assert page.evaluate("() => window.__plays") == 0
    page.touchscreen.tap(page.viewport_size["width"] / 2, page.viewport_size["height"] / 2)
    page.wait_for_timeout(300)
    first = page.evaluate("() => window.__plays")
    assert first >= 1, "no silent play() in the first tap"
    page.evaluate("() => { window.__refuse = 0; }")
    page.touchscreen.tap(page.viewport_size["width"] / 2, page.viewport_size["height"] / 3)
    page.wait_for_timeout(300)
    second = page.evaluate("() => window.__plays")
    assert second > first, "a refused unlock is not tried again on the next tap"
    page.touchscreen.tap(page.viewport_size["width"] / 2, page.viewport_size["height"] / 3)
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__plays") == second, "unlock keeps playing after it went through"


# ---------- chat and keyboard ----------


@audit("kb", "chat with keyboard: input above it, card hidden, layout back after")
@pytest.mark.parametrize("landscape", [False, True], ids=["portrait", "landscape"])
def test_chat_keyboard(open_page, landscape):
    page = open_page(FAKE_KEYBOARD, landscape=landscape)
    tap_room(page)
    page.get_by_role("button", name="Chat").tap()
    page.wait_for_timeout(300)
    keyboard = 200 if landscape else 336
    page.evaluate(f"() => window.__kb({keyboard})")
    page.wait_for_timeout(400)
    visible = page.viewport_size["height"] - keyboard
    field = box(page, ".omnibox-input")
    assert page.evaluate("() => document.activeElement && document.activeElement.tagName") == "INPUT"
    assert field and field["bottom"] <= visible + 1 and field["top"] >= 0, f"input {field} vs visible height {visible}"
    assert box(page, ".phone-sheet") is None, "the card stays open behind/over the keyboard"
    dock = box(page, ".dock")
    assert dock["top"] >= box(page, ".phone-back")["bottom"], "the dock reaches under the header"
    page.evaluate("() => { window.__kb(0); document.activeElement && document.activeElement.blur(); }")
    page.wait_for_timeout(500)
    assert box(page, ".phone-sheet") is not None, "the card does not come back after the keyboard closes"
    dock = box(page, ".dock")
    assert dock["bottom"] <= page.viewport_size["height"] and page.viewport_size["height"] - dock["bottom"] < 40, dock


# ---------- landscape and safe areas ----------


@audit("land", "landscape: floor rail on the left, clear of the dock, header and pill")
def test_landscape_rail(open_page):
    page = open_page(landscape=True)
    tap_room(page)
    rail, dock, back = box(page, ".floorrail"), box(page, ".dock"), box(page, ".phone-back")
    assert rail["left"] < page.viewport_size["width"] / 3, f"rail not on the left: {rail}"
    assert not overlaps(rail, dock) and not overlaps(rail, back), (rail, dock, back)
    clipped = page.evaluate("() => { const r = document.querySelector('.floorrail'); return r.scrollHeight - r.clientHeight; }")
    assert clipped <= 1 or rail["height"] >= 2 * 44, f"rail squeezed: {rail}"
    pill = box(page, ".pill")
    assert pill is None or not overlaps(rail, pill), (rail, pill)


@audit("safe", "notch and home bar: chrome stays inside the safe area")
@pytest.mark.parametrize("landscape", [False, True], ids=["portrait", "landscape"])
def test_safe_areas(open_page, landscape):
    page = open_page(landscape=landscape)
    # Playwright has no notch: set the variables Phone.css reads from env(safe-area-inset-*).
    insets = {"t": 0, "b": 21, "l": 47, "r": 47} if landscape else {"t": 47, "b": 34, "l": 0, "r": 0}
    page.evaluate(
        "(i) => { const a = document.querySelector('.app'); for (const [k, v] of Object.entries(i)) a.style.setProperty('--safe-' + k, v + 'px'); }",
        insets,
    )
    here, to = open_route(page)
    width, height = page.viewport_size["width"], page.viewport_size["height"]
    checks = [".phone-back", ".phone-search", ".floorrail", ".dock", ".dir-fields", ".directions .x", ".pill"]
    for selector in checks:
        b = box(page, selector)
        assert b, f"{selector} missing"
        assert b["left"] >= insets["l"] and b["right"] <= width - insets["r"], f"{selector} under the side notch: {b}"
        assert b["top"] >= insets["t"] or selector == ".directions", f"{selector} under the top notch: {b}"
        assert b["bottom"] <= height - insets["b"], f"{selector} under the home bar: {b}"
    page.get_by_role("button", name="Close directions").tap()
    page.wait_for_timeout(400)
    for selector in (".phone-back", ".floorrail"):
        b = box(page, selector)
        assert b and b["left"] >= insets["l"] and b["top"] >= insets["t"] and b["right"] <= width - insets["r"], f"{selector}: {b}"


@audit("5", "touch targets at least 44 px (load, room card)")
def test_touch_targets(open_page):
    page = open_page()
    assert not page.evaluate(SMALL_TARGETS), page.evaluate(SMALL_TARGETS)
    tap_room(page)
    assert not page.evaluate(SMALL_TARGETS), page.evaluate(SMALL_TARGETS)
