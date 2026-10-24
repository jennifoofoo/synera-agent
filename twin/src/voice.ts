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
