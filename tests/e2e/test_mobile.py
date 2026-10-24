"""Mobile smoke tests: one test per requirement of docs/mobile-audit.md and docs/specs/mobile-first.md.

Run on Pixel 7 (Chromium, 412 px) and iPhone 14 (WebKit, 390 px) with touch on. Known gaps carry
`xfail(strict=False)` so the suite documents what Leonie has not built yet and starts reporting XPASS when she does.
No chat message is ever sent, so no API key is needed.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

pytestmark = pytest.mark.e2e


def audit(item: str, title: str):
    return pytest.mark.audit(item, title)


def gap(item: int):
    return pytest.mark.xfail(strict=False, reason=f"mobile audit item {item}")


# ---------- helpers ----------

# Candidate room tap point: a polygon whose centre really hits that polygon (not a control or the legend).
FIND_ROOM_POINT = """() => {
  const map = document.querySelector('#map').getBoundingClientRect();
  let best = null;
  for (const poly of document.querySelectorAll('#map [data-space]')) {
    const r = poly.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    if (x < map.left + 5 || x > map.right - 5 || y < map.top + 5 || y > map.bottom - 5) continue;
    const hit = document.elementFromPoint(x, y);
    if (!hit || hit.closest('[data-space]') !== poly) continue;
    const area = r.width * r.height;
    if (!best || area > best.area) best = { x, y, area };
  }
  return best;
}"""

# Elements the audit calls touch targets: buttons, selects, tabs, chips. Skips hidden and screen-reader-only ones.
TOUCH_TARGETS = """() => {
  const out = [];
  for (const el of document.querySelectorAll('button, select, [role=tab], .tab, .chip, .selection-chip')) {
    if (el.closest('.sr, [hidden]')) continue;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (cs.visibility === 'hidden' || cs.display === 'none' || r.width === 0 || r.height === 0) continue;
    const name = el.id || el.getAttribute('aria-label') || el.dataset.tab || el.dataset.view || el.textContent.trim().slice(0, 20) || el.className;
    out.push({ name: `${el.tagName.toLowerCase()}#${name}`, w: Math.round(r.width), h: Math.round(r.height) });
  }
  return out;
}"""

NO_SPEECH = """
  delete window.SpeechRecognition;
  delete window.webkitSpeechRecognition;
  Object.defineProperty(window, 'SpeechRecognition', { value: undefined, configurable: true });
  Object.defineProperty(window, 'webkitSpeechRecognition', { value: undefined, configurable: true });
"""

# Spies: count wake lock requests and media play() calls (the page never has to reach a real model for these).
SPIES = """
  window.__wake = 0;
  window.__plays = 0;
  const lock = { released: false, release() { return Promise.resolve(); }, addEventListener() {} };
  const wl = { request() { window.__wake++; return Promise.resolve(lock); } };
  Object.defineProperty(navigator, 'wakeLock', { value: wl, configurable: true });
  HTMLMediaElement.prototype.play = function () { window.__plays++; return Promise.resolve(); };
"""


def tap_room(page):
    point = page.evaluate(FIND_ROOM_POINT)
    assert point, "no room polygon is tappable on the plan"
    page.touchscreen.tap(point["x"], point["y"])
    page.wait_for_selector("#selection-chip:not([hidden])", timeout=3000)


def overflow(page) -> dict:
    return page.evaluate(
        "() => ({scroll: document.documentElement.scrollWidth, inner: window.innerWidth, body: document.body.scrollWidth})"
    )


def open_3d(page):
    page.tap('[data-view="3d"]')
    page.wait_for_selector("#view3d:not([hidden])", timeout=5000)
    page.wait_for_timeout(1500)


# ---------- what works today (regression guards) ----------


@audit("ok", "viewport meta")
def test_viewport_meta(open_page):
    page = open_page()
    content = page.evaluate("() => document.querySelector('meta[name=viewport]')?.content || ''")
    assert "width=device-width" in content and "initial-scale=1" in content, content


@audit("ok", "no horizontal overflow in 2D")
def test_no_overflow_2d(open_page):
    sizes = overflow(open_page())
    assert sizes["scroll"] == sizes["inner"], sizes


@audit("ok", "no horizontal overflow in 3D")
def test_no_overflow_3d(open_page):
    page = open_page()
    open_3d(page)
    sizes = overflow(page)
    assert sizes["scroll"] == sizes["inner"], sizes


@audit("ok", "no horizontal overflow in the New tab")
def test_no_overflow_new_tab(open_page):
    page = open_page()
    page.tap('.tab[data-tab="plan"]')
    page.wait_for_selector('.panel[data-panel="plan"].active')
    sizes = overflow(page)
    assert sizes["scroll"] == sizes["inner"], sizes


@audit("ok", "tapping a room selects it and shows the chip")
def test_tap_room_selects(open_page):
    page = open_page()
    tap_room(page)
    assert page.inner_text("#selection-text").startswith("Selected:")


@audit("ok", "pinch and pan change the viewBox")
def test_pinch_and_pan_change_viewbox(open_page, device):
    page = open_page()
    _, descriptor, _ = device
    read = "() => document.querySelector('#map').getAttribute('viewBox')"
    box = page.locator("#map").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    start = page.evaluate(read)
    if descriptor["default_browser_type"] == "chromium":
        cdp = page.context.new_cdp_session(page)

        def touch(kind, points):
            cdp.send(
                "Input.dispatchTouchEvent",
                {"type": kind, "touchPoints": [{"x": x, "y": y, "id": i} for i, (x, y) in enumerate(points)]},
            )

        # pan with one finger
        touch("touchStart", [(cx, cy)])
        for step in range(1, 7):
            touch("touchMove", [(cx + step * 15, cy + step * 8)])
        touch("touchEnd", [])
        page.wait_for_timeout(200)
        panned = page.evaluate(read)
        # pinch out with two fingers
        touch("touchStart", [(cx - 30, cy), (cx + 30, cy)])
        for step in range(1, 7):
            touch("touchMove", [(cx - 30 - step * 15, cy), (cx + 30 + step * 15, cy)])
        touch("touchEnd", [])
    else:
        # WebKit has no multi-touch API in Playwright: send the same pointer events the page listens to.
        page.evaluate("() => { Element.prototype.setPointerCapture = function () {}; }")

        def fire(kind, pid, x, y):
            page.evaluate(
                """([kind, pid, x, y]) => document.querySelector('#map').dispatchEvent(new PointerEvent(kind,
                    {pointerId: pid, pointerType: 'touch', clientX: x, clientY: y, bubbles: true, isPrimary: pid === 1}))""",
                [kind, pid, x, y],
            )

        fire("pointerdown", 1, cx, cy)
        for step in range(1, 7):
            fire("pointermove", 1, cx + step * 15, cy + step * 8)
        fire("pointerup", 1, cx + 90, cy + 48)
        page.wait_for_timeout(200)
        panned = page.evaluate(read)
        fire("pointerdown", 1, cx - 30, cy)
        fire("pointerdown", 2, cx + 30, cy)
        for step in range(1, 7):
            fire("pointermove", 1, cx - 30 - step * 15, cy)
            fire("pointermove", 2, cx + 30 + step * 15, cy)
        fire("pointerup", 1, cx - 120, cy)
        fire("pointerup", 2, cx + 120, cy)
    page.wait_for_timeout(200)
    zoomed = page.evaluate(read)
    assert panned != start, f"pan did not change the viewBox: {start}"
    assert zoomed != panned, f"pinch did not change the viewBox: {panned}"


@audit("ok", "mic and speaker controls present")
def test_voice_controls_present(open_page):
    page = open_page()
    assert page.locator("#mic").is_visible()
    assert page.locator("#voice-out").is_visible()


@audit("6", "no SpeechRecognition: hint shown, mic does not throw")
def test_mic_without_speech_recognition(open_page):
    page = open_page(NO_SPEECH)
    assert page.evaluate("() => !(window.SpeechRecognition || window.webkitSpeechRecognition)")
    page.touchscreen.tap(*_center(page, "#mic"))
    page.wait_for_timeout(500)
    hint = page.inner_text("#voice-note") + " " + page.inner_text("#voice-status") + " " + page.inner_text("#chat-note")
    assert "type" in hint.lower(), f"no hint about typing instead: {hint!r}"
    assert not page.errors, page.errors


@audit("6", "hands-free switch is disabled with a hint when speech is unsupported")
@gap(6)
def test_handsfree_switch_disabled_without_speech(open_page):
    page = open_page(NO_SPEECH)
    switch = page.locator("#handsfree, [data-handsfree], input[name=handsfree], label:has-text('Hands-free')").first
    assert switch.count() and switch.is_visible(), "no hands-free switch on the page yet"
    assert switch.is_disabled() or switch.get_attribute("aria-disabled") == "true"


# ---------- the audit's "must fix" and "should fix" list ----------


@audit("1", "chat input font size at least 16 px (iOS zoom)")
@gap(1)
def test_chat_input_font_size(open_page):
    size = open_page().evaluate("() => parseFloat(getComputedStyle(document.querySelector('#chat-input')).fontSize)")
    assert size >= 16, f"chat input is {size}px"


@audit("2", "audio unlocked after the first tap")
@gap(2)
def test_audio_unlock_after_first_gesture(open_page):
    page = open_page(SPIES)
    assert page.evaluate("() => window.__plays") == 0
    page.touchscreen.tap(*_center(page, "#mic"))
    page.wait_for_timeout(500)
    assert page.evaluate("() => window.__plays") >= 1, "no silent audio play() in the first user gesture"


@audit("2", "screen wake lock requested after the first tap")
@gap(2)
def test_wake_lock_after_first_gesture(open_page):
    page = open_page(SPIES)
    assert page.evaluate("() => window.__wake") == 0
    page.touchscreen.tap(*_center(page, "#mic"))
    page.wait_for_timeout(500)
    assert page.evaluate("() => window.__wake") >= 1, "navigator.wakeLock.request was never called"


@audit("3", "room popover covers at most 35 percent of the plan")
def test_popover_is_small_bottom_sheet(open_page):
    page = open_page()
    tap_room(page)
    page.wait_for_selector("#popover:not([hidden])")
    share = page.evaluate(
        """() => {
          const m = document.querySelector('#map').getBoundingClientRect();
          const p = document.querySelector('#popover').getBoundingClientRect();
          const w = Math.max(0, Math.min(m.right, p.right) - Math.max(m.left, p.left));
          const h = Math.max(0, Math.min(m.bottom, p.bottom) - Math.max(m.top, p.top));
          return (w * h) / (m.width * m.height);
        }"""
    )
    assert share <= 0.35, f"popover covers {share:.0%} of the plan"


@audit("4", "plan area at least 45 percent of the viewport height")
def test_plan_height_share(open_page):
    ratio = open_page().evaluate(
        "() => document.querySelector('#map').getBoundingClientRect().height / window.innerHeight"
    )
    assert ratio >= 0.45, f"plan is {ratio:.0%} of the viewport height"


@audit("5", "buttons, selects, tabs and chips are at least 44x44 px")
@gap(5)
def test_touch_targets(open_page):
    page = open_page()
    offenders: dict[str, str] = {}

    def collect(state: str):
        for t in page.evaluate(TOUCH_TARGETS):
            if t["w"] < 44 or t["h"] < 44:
                offenders.setdefault(t["name"], f"{t['w']}x{t['h']} ({state})")

    collect("2D")
    tap_room(page)  # popover buttons and the selection chip
    page.wait_for_selector("#popover:not([hidden])")
    collect("room tapped")
    page.tap("#popover .close-x") if page.locator("#popover .close-x").bounding_box() else None
    open_3d(page)
    collect("3D")
    assert not offenders, f"{len(offenders)} touch targets under 44 px: {offenders}"


@audit("7", "page transfer under 400 KB (gzip) on 3G")
def test_page_weight_budget(three_g_load):
    assert three_g_load["bytes"] < 400 * 1024, (
        f"{three_g_load['bytes'] / 1024:.0f} KB over {three_g_load['requests']} requests"
    )


@audit("7", "plan drawn within 10 s on 3G")
def test_load_time_budget(three_g_load):
    assert three_g_load["seconds"] < 10, f"plan drawn after {three_g_load['seconds']:.1f} s"


@audit("7", "at most 20 requests to draw the plan")
def test_request_budget(three_g_load):
    assert three_g_load["requests"] <= 20, f"{three_g_load['requests']} requests"


@audit("8", "touch-action: manipulation on the page (no double-tap zoom)")
@gap(8)
def test_touch_action_manipulation(open_page):
    values = open_page().evaluate(
        "() => [document.documentElement, document.body].map((e) => getComputedStyle(e).touchAction)"
    )
    assert any(v in ("manipulation", "none", "pan-x pan-y") for v in values), values


# ---------- 3G load measurement (Chromium only: needs the DevTools network emulation) ----------


@pytest.fixture
def three_g_load(device, base_url):
    _, descriptor, browser = device
    if descriptor["default_browser_type"] != "chromium":
        pytest.skip("network throttling needs Chromium (CDP)")
    context = browser.new_context(**descriptor)
    try:
        page = context.new_page()
        cdp = context.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        # "Fast 3G" style profile: 1.6 Mbit/s down, 750 kbit/s up, 150 ms round trip.
        cdp.send(
            "Network.emulateNetworkConditions",
            {"offline": False, "latency": 150, "downloadThroughput": 1.6e6 / 8, "uploadThroughput": 750e3 / 8},
        )
        sizes: dict[str, int] = {}
        cdp.on("Network.loadingFinished", lambda e: sizes.__setitem__(e["requestId"], int(e["encodedDataLength"])))
        start = time.monotonic()
        page.goto(base_url)
        page.wait_for_selector("#map [data-space]", state="attached", timeout=60000)
        seconds = time.monotonic() - start
        page.wait_for_timeout(500)
        yield {"bytes": sum(sizes.values()), "requests": len(sizes), "seconds": seconds}
    finally:
        context.close()


def _center(page, selector: str) -> tuple[float, float]:
    box = page.locator(selector).bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
