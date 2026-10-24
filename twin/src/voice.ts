// Voice in (Web Speech API, webkitSpeechRecognition on iOS Safari) and out (/api/speak with ElevenLabs, else
// the browser's own voice). Owner: chat/search session; the phone session may add audio unlock / wake lock here.

import { api } from "./api/client";

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

const isApple = () => typeof navigator !== "undefined" && /iPhone|iPad|iPod|Macintosh/.test(navigator.userAgent);
const isIOS = () =>
  typeof navigator !== "undefined" &&
  (/iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.userAgent.includes("Macintosh") && navigator.maxTouchPoints > 1));

export function speechInputAvailable(): boolean {
  return !!recognitionCtor();
}

/** Why the mic cannot work here, in words for the person holding the phone; null when it can. */
export function speechInputProblem(): string | null {
  if (typeof window !== "undefined" && !window.isSecureContext) {
    return "Voice needs a secure (https) link. Open the tunnel link, or type instead.";
  }
  if (!recognitionCtor()) {
    return isIOS() ? "Voice input needs Safari on iPhone. Type instead." : "Voice input isn't available in this browser. Try Safari or Chrome, or type instead.";
  }
  return null;
}

function errorMessage(error: string): string | undefined {
  if (error === "no-speech" || error === "aborted") return undefined;
  if (error === "not-allowed") {
    return isIOS()
      ? "Microphone is blocked. On iPhone: Settings › Apps › Safari › Microphone › Allow, then reload."
      : isApple()
        ? "Microphone is blocked. Allow it in Safari › Settings for This Website, then try again."
        : "Microphone is blocked. Allow it in the site settings, then try again.";
  }
  if (error === "service-not-allowed") {
    return isIOS()
      ? "Voice input is off. On iPhone: Settings › Siri › turn on Siri (or Dictation), then try again."
      : "Speech recognition isn't allowed here. Type instead.";
  }
  if (error === "audio-capture") return "No microphone found.";
  if (error === "network") return "Speech recognition needs a network connection.";
  return `Voice input stopped (${error}).`;
}

export interface Listener {
  /** Stop listening and send what was heard so far. */
  stop: () => void;
  /** Stop listening and drop what was heard. */
  cancel: () => void;
}

/**
 * Push-to-talk: listen once. `onInterim` gets the live transcript, `onFinal` the finished sentence (only when
 * something was heard), `onEnd` always runs last, with a message when something went wrong.
 */
export function listen(
  lang: string,
  handlers: { onInterim?: (text: string) => void; onFinal: (text: string) => void; onEnd: (error?: string) => void },
): Listener {
  const Ctor = recognitionCtor();
  if (!Ctor) {
    handlers.onEnd(speechInputProblem() ?? undefined);
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
    error = errorMessage(event.error);
  };
  recognition.onend = () => {
    if (ended) return;
    ended = true;
    if (!cancelled && heard) handlers.onFinal(heard);
    handlers.onEnd(error);
  };
  try {
    recognition.start();
  } catch (problem) {
    ended = true;
    handlers.onEnd(`Voice input could not start (${(problem as Error).message}).`);
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

// One audio element, reused: iOS only lets an element play after it was started inside a tap once.
let audio: HTMLAudioElement | null = null;
let audioUrl: string | null = null;
let unlocked = false;
const SILENT_WAV = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";

function audioElement(): HTMLAudioElement {
  if (!audio) audio = new Audio();
  return audio;
}

/** Call inside a tap (mic, send): lets later replies play on iOS Safari. Safe to call often. */
export function unlockAudio(): void {
  if (unlocked || typeof window === "undefined") return;
  unlocked = true;
  const element = audioElement();
  element.src = SILENT_WAV;
  void element.play().catch(() => {
    unlocked = false;
  });
  // The browser voice needs the same: an empty utterance inside the gesture.
  try {
    window.speechSynthesis?.speak(new SpeechSynthesisUtterance(""));
  } catch {
    /* no browser voice */
  }
}

export function stopSpeaking(): void {
  if (audio) {
    audio.pause();
    audio.removeAttribute("src");
  }
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audioUrl = null;
  window.speechSynthesis?.cancel();
}

/** True while a reply is being spoken (server audio or browser voice). */
export function isSpeaking(): boolean {
  return (!!audio && !audio.paused && !!audioUrl) || !!window.speechSynthesis?.speaking;
}

const ID_TOKEN = /\s*[([]?`?\b[A-Za-z][\w.]*(?:-[\w.]+){2,}`?[)\]]?/g;

/**
 * What to say out loud: no ids, no markdown, and the final "Answer:" line only when the text before it does
 * not already say it.
 */
export function spokenText(reply: string): string {
  const lines = reply.trim().split("\n");
  let answer = "";
  const lastIndex = lines.length - 1;
  if (lastIndex >= 0 && /^\s*\**Answer:\**/i.test(lines[lastIndex])) {
    answer = lines[lastIndex].replace(/^\s*\**Answer:\**\s*/i, "").trim();
    lines.pop();
  }
  const clean = (text: string) =>
    text
      .replace(/```[\s\S]*?```/g, " ")
      .replace(ID_TOKEN, (token) => (/\d/.test(token) ? "" : token))
      .replace(/[*_`#>|]+/g, "")
      .replace(/^\s*[-•]\s+/gm, "")
      .replace(/\(\s*\)/g, "")
      .replace(/[ \t]+/g, " ")
      .replace(/\s+([.,;:!?])/g, "$1")
      .trim();
  const body = clean(lines.join("\n"));
  const said = clean(answer);
  if (!body) return said;
  if (!said || body.toLowerCase().includes(said.toLowerCase())) return body;
  return `${body}\n${said}`;
}

/** Speak a reply: ElevenLabs through the server when configured, otherwise the browser voice. */
export async function speak(text: string, serverVoice: boolean, lang = "en"): Promise<void> {
  stopSpeaking();
  const spoken = spokenText(text);
  if (!spoken) return;
  if (serverVoice) {
    try {
      const blob = await api.speak(spoken, lang);
      if (blob) {
        const element = audioElement();
        audioUrl = URL.createObjectURL(blob);
        element.src = audioUrl;
        await element.play();
        return;
      }
    } catch {
      /* fall through to the browser voice */
    }
  }
  if (!window.speechSynthesis) return;
  const utterance = new SpeechSynthesisUtterance(spoken);
  utterance.lang = lang === "de" ? "de-DE" : "en-US";
  utterance.rate = 1;
  window.speechSynthesis.speak(utterance);
}
