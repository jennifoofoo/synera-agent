// Pure parts of the iPhone wake word (see wakeListen.ts): an energy voice-activity detector and the decision what
// to do with a transcript. No browser APIs here, unit tested in wakeVad.test.ts.

import { normalizeSpeech, parseWake } from "./wake";

export const VAD = {
  /** Loud for this long before it counts as speech (a door bang or a cough is shorter). */
  onsetMs: 150,
  /** Quiet for this long ends the utterance. */
  hangMs: 700,
  /** An utterance is cut (and sent) after this long. */
  maxMs: 8000,
  /** Shorter utterances (from the onset to the last loud moment) are dropped. */
  minMs: 400,
  /** Absolute RMS level (0..1) that is always quiet, whatever the room. */
  minLevel: 0.02,
  /** Loud means this many times the room's noise floor. */
  floorFactor: 2.5,
} as const;

export type VadPhase = "idle" | "onset" | "speech";
export interface Vad {
  phase: VadPhase;
  /** When the current onset or utterance began (ms). */
  since: number;
  /** Last loud moment in the utterance (ms). */
  lastLoud: number;
  /** Slowly tracked noise level of the room, only while idle. */
  floor: number;
}
/** start: speech confirmed. send: an utterance ended and should be transcribed. drop: it was too short. */
export type VadEvent = "start" | "send" | "drop" | null;

export function vadInit(): Vad {
  return { phase: "idle", since: 0, lastLoud: 0, floor: 0 };
}

export function vadThreshold(vad: Vad): number {
  return Math.max(VAD.minLevel, vad.floor * VAD.floorFactor);
}

/** The room's noise floor: falls fast to quieter readings, rises slowly (very slowly while someone talks), so a
 * steady hum is learned but a sentence does not raise the bar against itself. */
function nextFloor(vad: Vad, level: number, loud: boolean): number {
  if (!vad.floor) return Math.max(level, 1e-4);
  if (level < vad.floor) return vad.floor * 0.7 + level * 0.3;
  // Quiet readings pull it up; loud ones only during a long utterance, and barely (a hum that started later is
  // learned over a few cut utterances; the syllables of a sentence never are).
  const rise = !loud ? 0.02 : vad.phase === "speech" ? 0.002 : 0;
  return vad.floor + (level - vad.floor) * rise;
}

/** One level reading (RMS, 0..1) at time `now` (ms). Returns the next state and what happened. */
export function vadStep(vad: Vad, level: number, now: number): { vad: Vad; event: VadEvent } {
  const loud = vad.floor > 0 && level >= vadThreshold(vad); // the first reading only seeds the floor
  vad = { ...vad, floor: nextFloor(vad, level, loud) };
  switch (vad.phase) {
    case "idle":
      if (loud) return { vad: { ...vad, phase: "onset", since: now, lastLoud: now }, event: null };
      return { vad, event: null };
    case "onset":
      if (!loud) return { vad: { ...vad, phase: "idle" }, event: null };
      if (now - vad.since >= VAD.onsetMs) return { vad: { ...vad, phase: "speech", lastLoud: now }, event: "start" };
      return { vad: { ...vad, lastLoud: now }, event: null };
    case "speech": {
      const lastLoud = loud ? now : vad.lastLoud;
      if (now - vad.since >= VAD.maxMs) return { vad: { ...vad, phase: "idle", lastLoud }, event: "send" };
      if (now - lastLoud >= VAD.hangMs) {
        return { vad: { ...vad, phase: "idle", lastLoud }, event: lastLoud - vad.since >= VAD.minMs ? "send" : "drop" };
      }
      return { vad: { ...vad, lastLoud }, event: null };
    }
  }
}

/** What a transcript means: "wake" (starts with Hey Wanda; the handler strips it), "armed" (no wake word, but Wanda
 * just asked or answered, so it is the next question), or null (someone else talking: ignore). */
export function routeTranscript(text: string, armed: boolean): "wake" | "armed" | null {
  if (parseWake(text)) return "wake";
  return armed && normalizeSpeech(text) ? "armed" : null;
}
