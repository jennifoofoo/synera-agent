"""Wanda as a small fairy light on the orb (docs/specs/wanda-fairy.md, twin/src/ui/Omnibox.tsx and Omnibox.css).

The orb is the one voice button. Per state (idle, listening, thinking, speaking, reply) it carries the right class, its
SVG has a core and two wings, and the sparks show only while thinking. The button itself never changes size or moves
(only inner SVG parts animate, and only transform and opacity). With reduced motion nothing runs at all.

A fake SpeechRecognition and a fake speechSynthesis (whose `speaking` flag the test sets) are injected before the page
loads, /api/chat and /api/speak are stubbed: no mic, no API key, no cost. Desktop Chromium and Pixel 7.
Set WANDA_FAIRY_SHOTS=<dir> to also save screenshots of every state (bar close-up plus one full view).

Run: scripts/build_twin.sh && uv run --group e2e pytest -m e2e tests/e2e/test_wanda_fairy.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

pytestmark = pytest.mark.e2e

REPLY = "The toilet is down the hall on the left."

FAKE_VOICE = """
(() => {
  const w = window;
  const instances = [];
  class FakeRecognition {
    constructor() { this.lang = ""; this.continuous = false; this.interimResults = false; this.state = "new";
      this.onresult = null; this.onerror = null; this.onend = null; instances.push(this); }
    start() { this.state = "live"; }
    stop() { this._end(); }
    abort() { this._end(); }
    _end() { if (this.state !== "live") return; this.state = "ended"; setTimeout(() => this.onend && this.onend(), 0); }
  }
  w.SpeechRecognition = FakeRecognition;
  w.webkitSpeechRecognition = FakeRecognition;
  w.__liveMics = () => instances.filter((r) => r.state === "live").length;
  const synth = {
    speaking: false, pending: false, paused: false,
    speak(u) { setTimeout(() => u && u.onend && u.onend(), 0); },
    cancel() { this.speaking = false; },
    getVoices() { return []; }, pause() {}, resume() {}, addEventListener() {}, removeEventListener() {},
  };
  Object.defineProperty(w, "speechSynthesis", { value: synth, configurable: true });
})();
"""

# Desktop 40 px; on touch (pointer: coarse) the orb is a 48 px tap target. Measured on the base before the fairy.
ORB_SIZE = {"desktop": 40.0, "pixel7": 48.0}

ORB = ".ob-fabs .wanda-orb"

PROBE = """(sel) => {
  const orb = document.querySelector(sel);
  const r = orb.getBoundingClientRect();
  const shown = (el) => !!el && getComputedStyle(el).display !== 'none' && getComputedStyle(el).visibility !== 'hidden'
    && Number(getComputedStyle(el).opacity) > 0 && el.getBoundingClientRect().width > 0;
  const sparks = [...orb.querySelectorAll('.wf-spark')];
  return {
    cls: orb.className, x: r.x, y: r.y, w: r.width, h: r.height,
    core: shown(orb.querySelector('svg.wf .wf-core')),
    wings: orb.querySelectorAll('svg.wf .wf-wings').length,
    wingShapes: orb.querySelectorAll('svg.wf .wf-wings .wf-wing').length,
    sparks: sparks.length, sparksShown: sparks.filter(shown).length,
    mic: shown(orb.querySelector('svg.wf .wf-mic')),
    label: orb.getAttribute('aria-label'),
  };
}"""

ANIMATIONS = """(sel) => document.querySelector(sel).getAnimations({ subtree: true }).map((a) => ({
  name: a.animationName || a.transitionProperty || '', target: (a.effect && a.effect.target && a.effect.target.getAttribute('class')) || '',
  props: a.effect && a.effect.getKeyframes ? [...new Set(a.effect.getKeyframes().flatMap((k) => Object.keys(k)))]
    .filter((k) => !['offset', 'computedOffset', 'easing', 'composite'].includes(k)) : [],
  onButton: a.effect && a.effect.target === document.querySelector(sel),
}))"""


@pytest.fixture(scope="module")
def chromium(playwright_instance):
    try:
        browser = playwright_instance.chromium.launch()
    except Exception as error:  # noqa: BLE001 - missing browser binary
        pytest.skip(f"chromium not installed (playwright install chromium): {str(error)[:80]}")
    yield browser
    browser.close()


def _context_options(playwright_instance, profile: str) -> dict:
    if profile == "pixel7":
        return dict(playwright_instance.devices["Pixel 7"])
    return {"viewport": {"width": 1100, "height": 720}}


@pytest.fixture(params=["desktop", "pixel7"])
def profile(request):
    return request.param


@pytest.fixture
def open_twin(chromium, playwright_instance, base_url, profile):
    contexts = []

    def _open(reduced: bool = False):
        context = chromium.new_context(**_context_options(playwright_instance, profile))
        contexts.append(context)
        context.add_init_script(FAKE_VOICE)
        page = context.new_page()
        if reduced:
            page.emulate_media(reduced_motion="reduce")
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.route(
            "**/api/chat",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"reply": REPLY, "backend": "fake"})
            ),
        )
        page.route("**/api/speak", lambda route: route.fulfill(status=503, body="no voice"))
        page.goto(base_url)
        page.wait_for_function(
            "() => !!(window.__twinStore && window.__twinStore.getState().model && document.querySelector('.ob-fabs .ob-talk'))",
            timeout=20000,
        )
        page.wait_for_timeout(800)
        return page

    yield _open
    for context in contexts:
        context.close()


def _wait_mode(page, mode: str) -> None:
    page.wait_for_function(
        "([sel, mode]) => document.querySelector(sel)?.classList.contains(mode)", arg=[ORB, mode], timeout=10000
    )


def drive(page):
    """Walk the orb through all five states; yields (state, probe) after each one has settled."""
    _wait_mode(page, "idle")
    yield "idle"
    page.evaluate("() => window.__twinStore.setState({ chatBusy: true })")
    _wait_mode(page, "thinking")
    yield "thinking"
    page.evaluate(
        """(reply) => {
          window.__twinStore.setState({ chatBusy: false, chat: [
            { id: 90001, role: 'user', text: 'where is the toilet' }, { id: 90002, role: 'agent', text: reply }] });
          window.speechSynthesis.speaking = true;
        }""",
        REPLY,
    )
    _wait_mode(page, "speaking")
    yield "speaking"
    page.evaluate("() => { window.speechSynthesis.speaking = false; }")
    _wait_mode(page, "reply")
    yield "reply"
    page.click(ORB)
    page.wait_for_function("() => window.__liveMics() === 1", timeout=10000)
    _wait_mode(page, "listening")
    yield "listening"


def _shots(page, profile: str, state: str) -> None:
    folder = os.environ.get("WANDA_FAIRY_SHOTS")
    if not folder:
        return
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(400)
    box = page.locator(".ob-fabs").bounding_box()
    viewport = page.viewport_size
    pad = 20
    x, y = max(0, box["x"] - pad), max(0, box["y"] - pad)
    clip = {
        "x": x,
        "y": y,
        "width": min(viewport["width"] - x, box["width"] + 2 * pad),
        "height": min(viewport["height"] - y, box["height"] + 2 * pad),
    }
    page.screenshot(path=str(out / f"{profile}-{state}-bar.png"), clip=clip, animations="allow")
    # the orb alone, zoomed by the device pixel ratio
    orb = page.locator(ORB).bounding_box()
    page.screenshot(
        path=str(out / f"{profile}-{state}-orb.png"),
        clip={"x": orb["x"] - 10, "y": orb["y"] - 10, "width": orb["width"] + 20, "height": orb["height"] + 20},
        animations="allow",
        scale="device",
    )
    if state in ("idle", "thinking"):
        page.screenshot(path=str(out / f"{profile}-{state}-full.png"), animations="allow")


def test_fairy_states(open_twin, profile):
    page = open_twin()
    first = None
    for state in drive(page):
        probe = page.evaluate(PROBE, ORB)
        assert state in probe["cls"].split(), (state, probe)
        assert probe["core"], (state, probe)
        assert probe["wings"] == 2, (state, probe)  # two pairs, left and right
        assert probe["wingShapes"] == 4, (state, probe)
        assert probe["sparks"] == 3, (state, probe)
        assert probe["sparksShown"] == (3 if state == "thinking" else 0), (state, probe)
        assert probe["mic"], (state, probe)  # still reads as "tap to talk"
        # The button never changes size and never moves under the finger.
        assert (probe["w"], probe["h"]) == (ORB_SIZE[profile], ORB_SIZE[profile]), (state, probe)
        if first is None:
            first = probe
        assert (round(probe["x"], 1), round(probe["y"], 1)) == (round(first["x"], 1), round(first["y"], 1)), (
            state,
            probe,
        )
        # Only inner parts animate, and only transform and opacity.
        for anim in page.evaluate(ANIMATIONS, ORB):
            if anim["name"] in ("box-shadow", "--wanda-level"):
                continue  # the existing voice-level glow transition on the button (set from audioLevel.ts)
            assert not anim["onButton"], (state, anim)
            assert set(anim["props"]) <= {"transform", "opacity"}, (state, anim)
        if state == "thinking":
            assert page.evaluate(ANIMATIONS, ORB), "the sparks should circle while thinking"
        _shots(page, profile, state)
    assert page.errors == [], page.errors


def test_fairy_reduced_motion(open_twin, profile):
    page = open_twin(reduced=True)
    for state in drive(page):
        page.wait_for_timeout(300)
        running = page.evaluate(ANIMATIONS, ORB)
        assert running == [], (state, running)
        probe = page.evaluate(PROBE, ORB)
        assert probe["wings"] == 2 and probe["core"], (state, probe)
        assert probe["sparksShown"] == (3 if state == "thinking" else 0), (state, probe)
        assert (probe["w"], probe["h"]) == (ORB_SIZE[profile], ORB_SIZE[profile]), (state, probe)
    assert page.errors == [], page.errors
