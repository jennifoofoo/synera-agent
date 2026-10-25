// Voice in (Web Speech API, webkitSpeechRecognition on iOS Safari) and out (/api/speak with ElevenLabs, else
// the browser's own voice). Owner: chat/search session; the phone helpers at the end belong to the mobile session.

import { api } from "./api/client";
import { voiceHint } from "./ui/phoneHints";

export type RecognitionResult = ArrayLike<{ transcript: string }> & { isFinal: boolean };
export type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { resultIndex: number; results: ArrayLike<RecognitionResult> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};
export type RecognitionCtor = new () => Recognition;

export function recognitionCtor(): RecognitionCtor | undefined {
  if (typeof window === "undefined") return undefined;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

export function speechInputAvailable(): boolean {
  return !!recognitionCtor();
}

/** Why the mic cannot work here, in words for the person holding the phone; null when it can. */
export function speechInputProblem(): string | null {
  if (typeof window !== "undefined" && !window.isSecureContext) return voiceHint();
  if (!recognitionCtor()) return voiceHint();
  return null;
}

/** Continuous listening that works well enough for an open mic after a reply: Chrome/Edge/Android, not Safari or
 * anything on iOS (every browser there is WebKit, and its recognition stops and starts unreliably). */
export function continuousRecognitionLikely(): boolean {
  if (typeof window === "undefined" || !window.isSecureContext || !recognitionCtor()) return false;
  const ua = navigator.userAgent;
  const iOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const safari = /AppleWebKit/.test(ua) && !/Chrome|Chromium|Edg|OPR|Android/.test(ua);
  return !iOS && !safari;
}

export interface Listener {
  /** Stop listening and send what was heard so far (within a short grace for the final words). */
  stop: () => void;
  /** Stop listening and drop what was heard. */
  cancel: () => void;
}

// After stop(), wait this long for the engine's final result or onend; iOS Safari often sends neither.
const STOP_GRACE_MS = 450;
// Safety net: a listen that never ends on its own (iOS sometimes hangs) is stopped after this.
const MAX_LISTEN_MS = 30_000;

/**
 * Push-to-talk: listen once. `onInterim` gets the live transcript, `onFinal` the finished sentence (only when
 * something was heard), `onEnd` always runs last and exactly once, with the raw recognition error code when
 * something went wrong (word it with `voiceHint(code)`); "no-speech" and "aborted" are not errors.
 * The listener ends itself: it never waits on the engine's onend, and always aborts the recognition so the mic
 * is released (iOS keeps it open after stop() until onend, which may never come).
 */
export function listen(
  lang: string,
  handlers: { onInterim?: (text: string) => void; onFinal: (text: string) => void; onEnd: (error?: string) => void },
): Listener {
  const Ctor = recognitionCtor();
  if (!Ctor) {
    // Async, so the caller has stored the returned listener before onEnd clears it.
    window.setTimeout(() => handlers.onEnd("unsupported"), 0);
    return { stop: () => {}, cancel: () => {} };
  }
  const recognition = new Ctor();
  recognition.lang = lang;
  recognition.interimResults = true;
  recognition.continuous = false;
  let heard = "";
  let stopping = false;
  let finished = false;
  let error: string | undefined;
  let graceTimer = 0;

  const finish = (send: boolean) => {
    if (finished) return;
    finished = true;
    liveListeners.delete(cancelListen);
    window.clearTimeout(graceTimer);
    window.clearTimeout(maxTimer);
    recognition.onresult = null;
    recognition.onerror = null;
    recognition.onend = null;
    try {
      recognition.abort();
    } catch {
      /* already ended */
    }
    if (send && heard) handlers.onFinal(heard);
    handlers.onEnd(error);
  };
  const stop = () => {
    if (finished || stopping) return;
    stopping = true;
    try {
      recognition.stop();
    } catch {
      /* not started */
    }
    graceTimer = window.setTimeout(() => finish(true), STOP_GRACE_MS);
  };
  const maxTimer = window.setTimeout(stop, MAX_LISTEN_MS);
  const cancelListen = () => finish(false);
  liveListeners.add(cancelListen);

  recognition.onresult = (event) => {
    const results = Array.from(event.results);
    heard = results
      .map((result) => result[0]?.transcript ?? "")
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
    handlers.onInterim?.(heard);
    if (stopping && results.length > 0 && results[results.length - 1].isFinal) finish(true);
  };
  recognition.onerror = (event) => {
    if (event.error !== "no-speech" && event.error !== "aborted") error = event.error;
    finish(true);
  };
  recognition.onend = () => finish(true);
  try {
    recognition.start();
  } catch {
    error = "start-failed";
    window.setTimeout(() => finish(false), 0);
  }
  return { stop, cancel: cancelListen };
}

/** @deprecated kept for older callers; use `listen`. */
export function listenOnce(lang: string, onResult: (text: string) => void, onEnd: (error?: string) => void): () => void {
  return listen(lang, { onFinal: onResult, onEnd }).stop;
}

// ---- voice out ----

let audioUrl: string | null = null;
let pending = 0;

/** True while speak() is still fetching the server voice (the reply has not started playing yet). */
export function speechPending(): boolean {
  return pending > 0;
}

// ---- iOS playback guards: release the mic before a reply plays, retry a refused play(), tap to hear ----

const beforePlayHooks = new Set<() => void>();
const liveListeners = new Set<() => void>();

/** Run `hook` right before a reply starts playing (wakeListen.ts releases its microphone there). */
export function onBeforePlay(hook: () => void): () => void {
  beforePlayHooks.add(hook);
  return () => beforePlayHooks.delete(hook);
}

function beforePlay(): void {
  if (!continuousRecognitionLikely()) for (const cancel of [...liveListeners]) cancel(); // Chrome keeps barge-in
  for (const hook of beforePlayHooks) {
    try {
      hook();
    } catch {
      /* a hook must never stop the reply */
    }
  }
}

/** Play, and when the browser refuses (iOS NotAllowedError after a mic session), wait a moment and try once more.
 * True when one of the two attempts played. */
export async function playWithRetry(play: () => Promise<void>, retryMs = 300): Promise<boolean> {
  try {
    await play();
    return true;
  } catch {
    /* refused: try once more */
  }
  await new Promise((resolve) => setTimeout(resolve, retryMs));
  try {
    await play();
    return true;
  } catch {
    return false;
  }
}

let blockedUrl: string | null = null;
const blockedListeners = new Set<() => void>();

function setBlockedReply(url: string | null): void {
  if (blockedUrl === url) return;
  blockedUrl = url;
  for (const listener of blockedListeners) listener();
}

/** A reply the browser refused to play: the page shows "Tap to hear Wanda" while this is true. */
export function replyBlocked(): boolean {
  return blockedUrl !== null;
}
export function subscribeReplyBlocked(listener: () => void): () => void {
  blockedListeners.add(listener);
  return () => blockedListeners.delete(listener);
}

/** Call inside a tap: play the refused reply now (a tap always may). */
export function playBlockedReply(): void {
  const url = blockedUrl;
  setBlockedReply(null);
  if (!url || audioUrl !== url) return;
  beforePlay();
  const audio = sharedAudio();
  audio.src = url;
  void audio.play().catch(() => setBlockedReply(url));
}

export function stopSpeaking(): void {
  setBlockedReply(null);
  const audio = sharedAudio();
  audio.pause();
  if (audioUrl) {
    audio.removeAttribute("src");
    URL.revokeObjectURL(audioUrl);
  }
  audioUrl = null;
  window.speechSynthesis?.cancel();
}

/** True while a reply is being spoken (server audio or browser voice). */
export function isSpeaking(): boolean {
  return (!!audioUrl && !sharedAudio().paused) || !!window.speechSynthesis?.speaking;
}

const ANSWER_LINE = /^\s*\**\s*Answer:/i;
const ID_TOKEN = /\s*[([]?`?\b[A-Za-z][\w.]*(?:-[\w.]+){2,}`?[)\]]?/g;
/** A square-bracketed reference with a digit in it ("[plan-89323a15-F0-S002]", "[space S002]", "[F0-S002, F0-S003]"),
 * never a markdown link text ("[Room 1](…)"). Nobody says square brackets out loud. */
const BRACKET_REF = /\s*\[[^\]\n]*\d[^\]\n]*\](?!\()/g;

/** The reply without its final "Answer: …" line (also "**Answer:**"). For anything shown or spoken. */
export function withoutAnswerLine(reply: string): string {
  const lines = reply.trimEnd().split("\n");
  const last = lines.length - 1;
  if (last > 0 && ANSWER_LINE.test(lines[last])) lines.pop();
  else if (last === 0 && ANSWER_LINE.test(lines[0])) return lines[0].replace(/^\s*\**\s*Answer:\**\s*/i, "");
  return lines.join("\n").trimEnd();
}

/** Text for display: raw ids such as "Project Room [plan-89323a15-F0-S002]" lose the id ("Project Room"). */
export function withoutIds(text: string): string {
  return text
    .replace(BRACKET_REF, "")
    .replace(ID_TOKEN, (token) => (/\d/.test(token) ? "" : token))
    .replace(/\(\s*\)|\[\s*\]/g, "")
    .replace(/[ \t]+/g, " ")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim();
}

/** What to say out loud: no final "Answer:" line, no ids, no markdown. */
export function spokenText(reply: string): string {
  return withoutAnswerLine(reply)
    .replace(/```[\s\S]*?```/g, " ")
    .replace(BRACKET_REF, "")
    .replace(ID_TOKEN, (token) => (/\d/.test(token) ? "" : token))
    .replace(/[*_`#>|]+/g, "")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/\(\s*\)/g, "")
    .replace(/[ \t]+/g, " ")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim();
}

/** Speak a reply: ElevenLabs through the server when configured, otherwise the browser voice. */
export async function speak(text: string, serverVoice: boolean): Promise<void> {
  stopSpeaking();
  const spoken = spokenText(text);
  if (!spoken) return;
  if (serverVoice) {
    pending++;
    try {
      const blob = await api.speak(spoken, "en");
      if (blob) {
        const audio = sharedAudio();
        const url = URL.createObjectURL(blob);
        audioUrl = url;
        beforePlay(); // iOS: no recognition or open mic while she talks (that mutes or reroutes the reply)
        const played = await playWithRetry(() => {
          if (audioUrl !== url) return Promise.resolve(); // stopped or replaced meanwhile
          audio.src = url;
          return audio.play();
        });
        if (!played && audioUrl === url) setBlockedReply(url); // "Tap to hear Wanda" instead of silence
        return;
      }
    } catch {
      /* fall through to the browser voice */
    } finally {
      pending--;
    }
  }
  if (!window.speechSynthesis) return;
  const utterance = new SpeechSynthesisUtterance(spoken);
  utterance.lang = "en-US";
  utterance.rate = 1;
  window.speechSynthesis.speak(utterance);
}

// ---- earcon ----

let earconContext: AudioContext | null = null;

/** Create the audio context inside a tap (browsers start it suspended otherwise). */
export function primeEarcon(): void {
  try {
    earconContext ??= new AudioContext();
    void earconContext.resume();
  } catch {
    /* no Web Audio */
  }
}

/** A short, soft two-note "I'm listening" chime (Web Audio, no file). */
export function earcon(): void {
  const context = earconContext;
  if (!context) return;
  void context.resume();
  const start = context.currentTime + 0.01;
  [660, 990].forEach((frequency, index) => {
    const osc = context.createOscillator();
    const gain = context.createGain();
    const at = start + index * 0.09;
    osc.type = "sine";
    osc.frequency.value = frequency;
    gain.gain.setValueAtTime(0, at);
    gain.gain.linearRampToValueAtTime(0.08, at + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.16);
    osc.connect(gain).connect(context.destination);
    osc.start(at);
    osc.stop(at + 0.18);
  });
}

// ===== Phone helpers (owner: mobile session): audio unlock and screen wake lock =====

// 0.05 s of silence as an 8 kHz mono WAV; playing it inside the first tap unlocks audio on iOS Safari.
const SILENT_WAV =
  "data:audio/wav;base64,UklGRrQBAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YZABAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA";

let unlockedAudio: HTMLAudioElement | null = null;

/** The one audio element, unlocked by the first tap. Reuse it for spoken replies (set src, play) so iOS
 * lets it play later without a fresh gesture. */
export function sharedAudio(): HTMLAudioElement {
  if (!unlockedAudio) {
    unlockedAudio = new Audio();
    unlockedAudio.setAttribute("playsinline", "");
  }
  return unlockedAudio;
}

/** Call once at start-up: the first pointer/key gesture plays a silent WAV on the shared element and warms
 * up speechSynthesis, so later replies can play after an await (iOS needs one gesture-started playback). */
export function installAudioUnlock(): void {
  // iOS counts a touch as a user gesture only on touchend / pointerup / click, not on pointerdown, so listen to all
  // of them and stop only once a play() really went through (a refused one is tried again on the next tap).
  const events = ["pointerdown", "pointerup", "touchend", "click", "keydown"] as const;
  let done = false;
  let warmed = false;
  const stop = () => {
    done = true;
    for (const type of events) window.removeEventListener(type, unlock, true);
  };
  const unlock = () => {
    if (done) return;
    const audio = sharedAudio();
    if (audioUrl) return stop(); // a reply is already playing on the element: it is unlocked
    audio.muted = false;
    audio.src = SILENT_WAV;
    try {
      const played = audio.play();
      if (played) played.then(stop, () => {});
      else stop();
    } catch {
      /* not allowed yet: next tap */
    }
    if (!warmed) {
      try {
        const warm = new SpeechSynthesisUtterance(" ");
        warm.volume = 0;
        window.speechSynthesis?.speak(warm);
        warmed = true;
      } catch {
        /* no browser voice */
      }
    }
  };
  for (const type of events) window.addEventListener(type, unlock, true);
  // iOS can lose the unlock after a mic session (tap-to-talk, the wake word): every later tap re-primes the element
  // with the silent clip while nothing plays, so the next reply may start after an await again.
  const reprime = () => {
    if (!done || pending > 0 || blockedUrl || liveListeners.size || isSpeaking()) return;
    const audio = sharedAudio();
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl); // the last reply has ended
      audioUrl = null;
    }
    audio.src = SILENT_WAV;
    void audio.play()?.catch(() => {});
  };
  for (const type of ["touchend", "click"] as const) window.addEventListener(type, reprime, true);
}

type WakeSentinel = { release: () => Promise<void>; addEventListener: (type: "release", listener: () => void) => void };
const awakeReasons = new Set<string>();
let sentinel: WakeSentinel | null = null;
let requesting = false;

async function syncWakeLock(): Promise<void> {
  const nav = navigator as Navigator & { wakeLock?: { request: (type: "screen") => Promise<WakeSentinel> } };
  if (!nav.wakeLock) return;
  const want = awakeReasons.size > 0 && document.visibilityState === "visible";
  if (want && !sentinel) {
    if (requesting) return;
    requesting = true;
    try {
      const lock = await nav.wakeLock.request("screen");
      sentinel = lock;
      lock.addEventListener("release", () => {
        if (sentinel === lock) sentinel = null;
      });
      if (awakeReasons.size === 0) void syncWakeLock(); // the reason ended while the request was pending
    } catch {
      /* refused (battery saver, not visible, no gesture): try again on the next change or tap */
    } finally {
      requesting = false;
    }
  } else if (!want && sentinel) {
    const lock = sentinel;
    sentinel = null;
    await lock.release().catch(() => {});
  }
}

/** Keep the screen on while any reason is active ("listening", "guiding"). The browser drops the lock when the
 * tab is hidden; it is taken again when the page becomes visible. Safe to call often. */
export function keepAwake(reason: string, on: boolean): void {
  if (on) awakeReasons.add(reason);
  else awakeReasons.delete(reason);
  void syncWakeLock();
}

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => void syncWakeLock());
  // Guiding starts after an awaited reply, outside the tap. If the browser refused the lock then (it may want a
  // user gesture), the next tap while guiding takes it.
  document.addEventListener("pointerup", () => awakeReasons.size > 0 && !sentinel && void syncWakeLock(), true);
}

/** Read a typed or chip reply aloud when the speaker toggle is on (spoken questions are read out in Omnibox). */
export function speakIfOn(reply: { reply: string } | null | undefined, voiceOut: boolean, speechAvailable: boolean): void {
  if (reply && voiceOut) void speak(reply.reply, speechAvailable);
}
