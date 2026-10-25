"""Voice: wake word stripping on push-to-talk, "I'm here." for the bare wake word, follow-up listening, and hands-free
negatives (twin/src/handsFree.ts, twin/src/wake.ts, docs/specs/voice-handsfree.md).

A fake SpeechRecognition and a fake speechSynthesis are injected before the page loads; /api/chat and /api/speak are
stubbed by Playwright, so no mic, no API key and no cost. Desktop Chromium only (follow-up listening is off on
Safari/iOS by design). Skips without Playwright, chromium, data/dev or twin/dist.

Run: scripts/build_twin.sh && uv run pytest -m e2e tests/e2e/test_voice_followup.py
"""

from __future__ import annotations

import json
import time

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from playwright.sync_api import TimeoutError as PlaywrightTimeout

pytestmark = pytest.mark.e2e

REPLY = "The toilet is down the hall on the left."

# Each recognition session keeps its own results list; every new utterance gets the next resultIndex (interim, then
# final). One-shot sessions (continuous = false) end after the final result, like Chrome.
FAKE_VOICE = """
(() => {
  const w = window;
  const instances = [];
  class FakeRecognition {
    constructor() {
      this.lang = ""; this.continuous = false; this.interimResults = false;
      this.onresult = null; this.onerror = null; this.onend = null;
      this.results = []; this.state = "new";
      instances.push(this);
    }
    start() { if (this.state !== "new") throw new Error("InvalidStateError"); this.state = "live"; }
    stop() { this._end(); }
    abort() { this._end(); }
    _end() {
      if (this.state !== "live") return;
      this.state = "ended";
      setTimeout(() => this.onend && this.onend(), 0);
    }
    _say(text) {
      const index = this.results.length;
      const result = (isFinal) => Object.assign([{ transcript: text, confidence: 0.9 }], { isFinal });
      this.results.push(result(false));
      this.onresult && this.onresult({ resultIndex: index, results: this.results.slice() });
      this.results[index] = result(true);
      this.onresult && this.onresult({ resultIndex: index, results: this.results.slice() });
      if (!this.continuous) setTimeout(() => this._end(), 0);
    }
  }
  w.SpeechRecognition = FakeRecognition;
  w.webkitSpeechRecognition = FakeRecognition;
  const live = () => instances.filter((r) => r.state === "live");
  w.__say = (text) => { const mics = live(); if (!mics.length) return false; mics[mics.length - 1]._say(text); return true; };
  w.__liveMics = () => live().length;

  const spoken = [];
  w.__spoken = spoken;
  const synth = {
    speaking: false, pending: false, paused: false, timer: 0,
    speak(u) {
      if (!u.text.trim()) return; // the audio unlock warm-up
      spoken.push(u.text);
      this.speaking = true;
      clearTimeout(this.timer);
      this.timer = setTimeout(() => { this.speaking = false; u.onend && u.onend(); }, 400);
    },
    cancel() { clearTimeout(this.timer); this.speaking = false; },
    getVoices() { return []; }, pause() {}, resume() {}, addEventListener() {}, removeEventListener() {},
  };
  Object.defineProperty(w, "speechSynthesis", { value: synth, configurable: true });
})();
"""


@pytest.fixture(scope="module")
def chromium(playwright_instance):
    try:
        browser = playwright_instance.chromium.launch()
    except Exception as error:  # noqa: BLE001 - missing browser binary
        pytest.skip(f"chromium not installed (playwright install chromium): {str(error)[:80]}")
    yield browser
    browser.close()


@pytest.fixture
def twin(chromium, base_url):
    """The twin on desktop with fake voice; returns (page, chat_messages) where chat_messages collects the bodies of
    every /api/chat call."""
    context = chromium.new_context(viewport={"width": 1100, "height": 720})
    context.add_init_script(FAKE_VOICE)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    chats: list[dict] = []

    def on_chat(route):
        chats.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"reply": REPLY, "backend": "fake"}))

    page.route("**/api/chat", on_chat)
    page.route("**/api/speak", lambda route: route.fulfill(status=503, body="no voice"))
    page.goto(base_url)
    page.wait_for_function(
        "() => !!(window.__twinStore && window.__twinStore.getState().model && document.querySelector('.ob-talk'))",
        timeout=20000,
    )
    page.wait_for_timeout(500)
    yield page, chats
    assert page.errors == [], page.errors
    context.close()


def wait_until(page, predicate, timeout_s: float = 25.0) -> None:
    """Generous: headless WebGL keeps the page's main thread busy, so page timers run late."""
    end = time.time() + timeout_s
    while time.time() < end:
        if predicate():
            return
        page.wait_for_timeout(100)
    state = page.evaluate(
        "() => { const s = window.__twinStore.getState(); return { followUpOpen: s.followUpOpen, followUp: s.followUp,"
        " handsFree: s.handsFree, status: s.handsFreeStatus, busy: s.chatBusy, mics: window.__liveMics(),"
        " notice: s.handsFreeNotice, secure: window.isSecureContext, vis: document.visibilityState, spoken: window.__spoken, speaking: window.speechSynthesis.speaking }; }"
    )
    raise AssertionError(f"condition not met in time: {state}")


def wait_mic(page) -> None:
    try:
        page.wait_for_function("() => window.__liveMics() === 1", timeout=15000)
    except PlaywrightTimeout:
        wait_until(page, lambda: False, 0)  # fails with the store state in the message


def talk_and_say(page, text: str) -> None:
    page.click(".ob-talk")
    wait_mic(page)
    assert page.evaluate("(t) => window.__say(t)", text)


def follow_up_open(page) -> bool:
    return page.evaluate("() => window.__twinStore.getState().followUpOpen && window.__liveMics() > 0")


def test_ptt_strips_misheard_wake_word(twin):
    page, chats = twin
    talk_and_say(page, "hey evander where is the toilet")
    wait_until(page, lambda: len(chats) == 1)
    assert chats[0]["message"] == "where is the toilet"
    assert chats[0]["voice"] is True


def test_ptt_bare_wake_word_says_im_here_and_keeps_listening(twin):
    page, chats = twin
    talk_and_say(page, "Hey Wanda")
    wait_until(page, lambda: "I'm here." in page.evaluate("() => window.__spoken"))
    page.wait_for_timeout(500)
    assert chats == []
    # It keeps listening: the question comes next, without wake word or button.
    wait_until(page, lambda: follow_up_open(page))
    assert page.evaluate("(t) => window.__say(t)", "where is the exit")
    wait_until(page, lambda: len(chats) == 1)
    assert chats[0]["message"] == "where is the exit"
    assert chats[0]["voice"] is True


def test_follow_up_after_spoken_reply_then_silence_closes(twin):
    page, chats = twin
    talk_and_say(page, "where is the toilet")
    wait_until(page, lambda: len(chats) == 1)
    wait_until(page, lambda: REPLY in page.evaluate("() => window.__spoken"))
    # After the reply has been spoken the mic opens by itself and says so.
    wait_until(page, lambda: follow_up_open(page))
    # the Wanda voice bar says it in its caption (.wb-text); the expanded bar keeps the status line (.ob-followup)
    assert "Listening" in page.locator(".ob-followup, .wb-text").first.inner_text()
    assert page.evaluate("(t) => window.__say(t)", "and the coffee machine?")
    wait_until(page, lambda: len(chats) == 2)
    assert chats[1]["message"] == "and the coffee machine?"
    assert chats[1]["voice"] is True
    # That reply opens the window again; silence closes it after about 8 s (not sooner) and nothing is sent.
    wait_until(page, lambda: follow_up_open(page))
    opened = time.time()
    page.wait_for_timeout(6000)
    assert follow_up_open(page), "the window closed too early"
    wait_until(page, lambda: not page.evaluate("() => window.__twinStore.getState().followUpOpen"))
    page.wait_for_timeout(max(0.0, 9.0 - (time.time() - opened)) * 1000)
    assert page.evaluate("() => window.__liveMics()") == 0
    assert len(chats) == 2


def test_follow_up_setting_off_keeps_mic_closed(twin):
    page, chats = twin
    page.evaluate(
        "() => { localStorage.setItem('twin.followUp', 'off'); window.__twinStore.setState({ followUp: false }); }"
    )
    talk_and_say(page, "where is the toilet")
    wait_until(page, lambda: REPLY in page.evaluate("() => window.__spoken"))
    page.wait_for_timeout(1500)
    assert not page.evaluate("() => window.__twinStore.getState().followUpOpen")
    assert page.evaluate("() => window.__liveMics()") == 0
    assert len(chats) == 1


NEGATIVES = [
    "wonderful",
    "wander around the hall",
    "I wonder where the toilet is",
    "where is the wander",
    "where is the coffee machine",
    "how far is it",
]


def test_hands_free_negatives_do_not_trigger_then_follow_up(twin):
    page, chats = twin
    page.evaluate("() => window.__twinStore.getState().setHandsFree(true)")
    wait_mic(page)
    for said in NEGATIVES:
        assert page.evaluate("(t) => window.__say(t)", said)
        page.wait_for_timeout(150)
    page.wait_for_timeout(500)
    assert chats == []
    assert page.evaluate("() => window.__spoken") == []
    # Control: the misheard wake word does trigger, and a follow-up works without it.
    assert page.evaluate("(t) => window.__say(t)", "E Wander where is the toilet")
    wait_until(page, lambda: len(chats) == 1)
    assert chats[0]["message"] == "where is the toilet"
    wait_until(page, lambda: REPLY in page.evaluate("() => window.__spoken"))
    wait_until(page, lambda: page.evaluate("() => window.__twinStore.getState().followUpOpen"))
    assert page.evaluate("(t) => window.__say(t)", "and the coffee machine?")
    wait_until(page, lambda: len(chats) == 2)
    assert chats[1]["message"] == "and the coffee machine?"
    assert chats[1]["voice"] is True


VISIBLE_COUNT = """(selector) => [...document.querySelectorAll(selector)].filter((el) => {
  const r = el.getBoundingClientRect(), st = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none';
}).length"""

START_WALK = """async () => {
  const store = window.__twinStore;
  const spaces = store.getState().building.spaces.map((s) => s.id);
  for (let i = 1; i < spaces.length && i < 40; i++) {
    await store.getState().route(spaces[0], spaces[i]);
    if (store.getState().state?.route?.ok) { store.getState().startWalk(); return true; }
  }
  return false;
}"""


def test_hands_free_control_shown_once(twin):
    """One voice entry point: the bottom bar has only the orb (no hands-free or stop button next to it), the step
    sheet has the one hands-free button while walking, and at most one "Say Hey Wanda" line shows."""
    page, _ = twin
    page.evaluate("() => window.__twinStore.getState().setHandsFree(true)")
    page.wait_for_timeout(800)
    assert page.evaluate(VISIBLE_COUNT, ".hf-btn") == 0
    assert page.evaluate(VISIBLE_COUNT, ".hf-status") <= 1
    assert page.evaluate(VISIBLE_COUNT, ".ob-fabs .wb-stop") == 0
    assert page.evaluate(VISIBLE_COUNT, ".ob-fabs .ob-talk") == 1

    assert page.evaluate(START_WALK), "no route found to walk"
    page.wait_for_function("() => !!document.querySelector('.card-walk')", timeout=15000)
    page.wait_for_function("() => window.__twinStore.getState().handsFree", timeout=15000)
    page.wait_for_timeout(800)
    assert page.evaluate(VISIBLE_COUNT, ".hf-btn") == 1
    assert page.evaluate(VISIBLE_COUNT, ".card-walk .hf-btn") == 1
    assert page.evaluate(VISIBLE_COUNT, ".hf-status") <= 1
    # While walking the bar's caption never repeats the step: only that Wanda listens or speaks, or nothing.
    caption = page.evaluate("() => document.querySelector('.wb-text')?.textContent ?? ''")
    assert caption in ("", "Listening…", "Speaking…"), caption

    # After something was said, the hint does not come back.
    assert page.evaluate("(t) => window.__say(t)", "hey wanda repeat")
    page.wait_for_timeout(1500)
    assert page.evaluate(VISIBLE_COUNT, ".hf-status") == 0 or "Hey Wanda" not in page.inner_text(".hf-status")
    assert page.evaluate(VISIBLE_COUNT, ".hf-btn") == 1
