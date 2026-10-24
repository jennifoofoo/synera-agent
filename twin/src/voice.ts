// Voice in (Web Speech API, webkitSpeechRecognition on iOS Safari) and out (/api/speak with ElevenLabs, else
// the browser's own voice). Owner: chat/search session; the phone helpers at the end belong to the mobile session.

import { api } from "./api/client";
import { voiceHint } from "./ui/phoneHints";

type RecognitionResult = ArrayLike<{ transcript: string }> & { isFinal: boolean };
type Recognition = {
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
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | undefined {
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

export interface Listener {
  /** Stop listening and send what was heard so far. */
  stop: () => void;
  /** Stop listening and drop what was heard. */
  cancel: () => void;
}

/**
 * Push-to-talk: listen once. `onInterim` gets the live transcript, `onFinal` the finished sentence (only when
 * something was heard), `onEnd` always runs last, with the raw recognition error code when something went wrong
 * (word it with `voiceHint(code)`); "no-speech" and "aborted" are not errors.
 */
export function listen(
  lang: string,
  handlers: { onInterim?: (text: string) => void; onFinal: (text: string) => void; onEnd: (error?: string) => void },
): Listener {
  const Ctor = recognitionCtor();
  if (!Ctor) {
    handlers.onEnd("unsupported");
    return { stop: () => {}, cancel: () => {} };
  }
  const recognition = new Ctor();
  recognition.lang = lang;
  recognition.interimResults = true;
  recognition.continuous = false;
  let heard = "";
  let cancelled = false;
  let ended = false;
  let error: string | undefined;
  recognition.onresult = (event) => {
    heard = Array.from(event.results)
      .map((result) => result[0]?.transcript ?? "")
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
    handlers.onInterim?.(heard);
  };
  recognition.onerror = (event) => {
    if (event.error !== "no-speech" && event.error !== "aborted") error = event.error;
  };
  recognition.onend = () => {
    if (ended) return;
    ended = true;
    if (!cancelled && heard) handlers.onFinal(heard);
    handlers.onEnd(error);
  };
  try {
    recognition.start();
  } catch {
    ended = true;
    handlers.onEnd("start-failed");
  }
  return {
    stop: () => recognition.stop(),
    cancel: () => {
      cancelled = true;
      recognition.abort();
    },
  };
}

/** @deprecated kept for older callers; use `listen`. */
export function listenOnce(lang: string, onResult: (text: string) => void, onEnd: (error?: string) => void): () => void {
  return listen(lang, { onFinal: onResult, onEnd }).stop;
}

// ---- voice out ----

let audioUrl: string | null = null;

export function stopSpeaking(): void {
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

/** The reply without its final "Answer: …" line (also "**Answer:**"). For anything shown or spoken. */
export function withoutAnswerLine(reply: string): string {
  const lines = reply.trimEnd().split("\n");
  const last = lines.length - 1;
  if (last > 0 && ANSWER_LINE.test(lines[last])) lines.pop();
  else if (last === 0 && ANSWER_LINE.test(lines[0])) return lines[0].replace(/^\s*\**\s*Answer:\**\s*/i, "");
  return lines.join("\n").trimEnd();
}

/** What to say out loud: no final "Answer:" line, no ids, no markdown. */
export function spokenText(reply: string): string {
  return withoutAnswerLine(reply)
    .replace(/```[\s\S]*?```/g, " ")
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
    try {
      const blob = await api.speak(spoken, "en");
      if (blob) {
        const audio = sharedAudio();
        audioUrl = URL.createObjectURL(blob);
        audio.src = audioUrl;
        await audio.play();
        return;
      }
    } catch {
      /* fall through to the browser voice */
    }
  }
  if (!window.speechSynthesis) return;
  const utterance = new SpeechSynthesisUtterance(spoken);
  utterance.lang = "en-US";
  utterance.rate = 1;
  window.speechSynthesis.speak(utterance);
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
