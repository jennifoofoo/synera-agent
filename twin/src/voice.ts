// Voice in (Web Speech API) and out (/api/speak with ElevenLabs, else the browser's own voice).

import { api } from "./api/client";

type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

export function speechInputAvailable(): boolean {
  const w = window as unknown as { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown };
  return !!(w.SpeechRecognition || w.webkitSpeechRecognition);
}

export function listenOnce(lang: string, onResult: (text: string) => void, onEnd: (error?: string) => void): () => void {
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  if (!Ctor) {
    onEnd("Voice input needs Chrome or Safari.");
    return () => {};
  }
  const recognition = new Ctor();
  recognition.lang = lang;
  recognition.interimResults = false;
  recognition.continuous = false;
  let finished = false;
  recognition.onresult = (event) => {
    const text = Array.from(event.results)
      .map((result) => result[0]?.transcript ?? "")
      .join(" ")
      .trim();
    if (text) onResult(text);
  };
  recognition.onerror = (event) => {
    finished = true;
    onEnd(event.error === "not-allowed" ? "Microphone access was denied." : event.error === "no-speech" ? undefined : event.error);
  };
  recognition.onend = () => {
    if (!finished) onEnd();
    finished = true;
  };
  recognition.start();
  return () => recognition.stop();
}

let audio: HTMLAudioElement | null = null;

export function stopSpeaking(): void {
  audio?.pause();
  audio = null;
  window.speechSynthesis?.cancel();
}

/** Speak a reply: ElevenLabs through the server when configured, otherwise the browser voice. */
export async function speak(text: string, serverVoice: boolean, lang = "en"): Promise<void> {
  stopSpeaking();
  const spoken = text.replace(/^Answer:.*$/m, "").trim() || text;
  if (serverVoice) {
    try {
      const blob = await api.speak(spoken, lang);
      if (blob) {
        audio = new Audio(URL.createObjectURL(blob));
        await audio.play();
        return;
      }
    } catch {
      /* fall through to the browser voice */
    }
  }
  if (!window.speechSynthesis) return;
  const utterance = new SpeechSynthesisUtterance(spoken);
  utterance.lang = lang === "de" ? "de-DE" : "en-US";
  utterance.rate = 0.95;
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
  const unlock = () => {
    window.removeEventListener("pointerdown", unlock, true);
    window.removeEventListener("keydown", unlock, true);
    const audio = sharedAudio();
    audio.muted = false;
    audio.src = SILENT_WAV;
    void audio.play().catch(() => {});
    try {
      const warm = new SpeechSynthesisUtterance(" ");
      warm.volume = 0;
      window.speechSynthesis?.speak(warm);
    } catch {
      /* no browser voice */
    }
  };
  window.addEventListener("pointerdown", unlock, true);
  window.addEventListener("keydown", unlock, true);
}

type WakeSentinel = { release: () => Promise<void>; addEventListener: (type: "release", listener: () => void) => void };
const awakeReasons = new Set<string>();
let sentinel: WakeSentinel | null = null;

async function syncWakeLock(): Promise<void> {
  const nav = navigator as Navigator & { wakeLock?: { request: (type: "screen") => Promise<WakeSentinel> } };
  if (!nav.wakeLock) return;
  const want = awakeReasons.size > 0 && document.visibilityState === "visible";
  if (want && !sentinel) {
    try {
      const lock = await nav.wakeLock.request("screen");
      sentinel = lock;
      lock.addEventListener("release", () => {
        if (sentinel === lock) sentinel = null;
      });
    } catch {
      /* refused (battery saver, not visible): try again on the next change */
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
}
