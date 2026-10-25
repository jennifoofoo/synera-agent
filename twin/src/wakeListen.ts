// "Hey Wanda" where continuous speech recognition is not dependable (iPhone/Safari, continuousRecognitionLikely()
// false). Used only while hands-free is on; handsFree.ts starts and stops it in place of its recognition loop.
// The mic level feeds an energy VAD (wakeVad.ts). A MediaRecorder runs all the time while listening (recycled every
// few seconds of silence, so the start of "Hey" is never cut off); when an utterance ends, its recording goes to
// POST /api/transcribe (ElevenLabs Scribe). A transcript that starts with the wake word, or any transcript while
// Wanda is waiting for the next question, goes to the same handler as the Chrome path (handleUtterance).
// Never listens while Wanda speaks (no hearing herself), while push-to-talk runs (paused: the mic is released), or
// while the page is hidden.

import { useTwin } from "./store";
import { earcon, isSpeaking, onBeforePlay, speechPending } from "./voice";
import { voiceHint } from "./ui/phoneHints";
import { parseWake } from "./wake";
import { routeTranscript, vadInit, vadStep, type Vad } from "./wakeVad";

const TICK_MS = 50;
/** While idle, a fresh recorder replaces the old one after this long (bounds the leading silence sent). */
const RECYCLE_MS = 2500;
/** After Wanda stops speaking, wait this long before listening again (her last word echoes). */
const AFTER_SPEECH_MS = 500;
/** After Wanda answered (or said "I'm here."), the next utterance needs no wake word within this window. */
const ARMED_MS = 8000;
/** How long to wait for an answer to start speaking before giving up on the follow-up window. */
const WAIT_FOR_SPEECH_MS = 2000;

type AudioCtor = new () => AudioContext;
type Handler = (text: string) => void | Promise<void>;

/** getUserMedia, MediaRecorder and Web Audio all exist (iOS 14.3+ Safari has them). */
export function wakeListenSupported(): boolean {
  if (typeof window === "undefined" || !window.isSecureContext) return false;
  const w = window as unknown as { AudioContext?: AudioCtor; webkitAudioContext?: AudioCtor; MediaRecorder?: unknown };
  return !!navigator.mediaDevices?.getUserMedia && !!w.MediaRecorder && !!(w.AudioContext ?? w.webkitAudioContext);
}

function recorderType(): string | undefined {
  for (const type of ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", "audio/ogg"]) {
    try {
      if (MediaRecorder.isTypeSupported(type)) return type;
    } catch {
      /* old Safari: no isTypeSupported */
    }
  }
  return undefined;
}

let context: AudioContext | null = null;
let stream: MediaStream | null = null;
let source: MediaStreamAudioSourceNode | null = null;
let analyser: AnalyserNode | null = null;
let recorder: MediaRecorder | null = null;
let chunks: Blob[] = [];
let recorderStarted = 0;
let timer = 0;
let running = false;
let run = 0;
let vad: Vad = vadInit();
let handler: Handler = () => {};
let quietSince = 0; // Wanda last stopped speaking
let armedUntil = 0;
let pendingArm: { at: number; spoke: boolean; force: boolean } | null = null;

function newRecorder(): void {
  if (!stream) return;
  const type = recorderType();
  let next: MediaRecorder;
  try {
    next = new MediaRecorder(stream, type ? { mimeType: type, audioBitsPerSecond: 64000 } : undefined);
  } catch {
    next = new MediaRecorder(stream);
  }
  const own: Blob[] = [];
  next.ondataavailable = (event) => {
    if (event.data.size) own.push(event.data);
  };
  chunks = own;
  recorder = next;
  recorderStarted = Date.now();
  try {
    next.start();
  } catch {
    recorder = null;
  }
}

/** Stop the current recorder; `keep` gets its audio once it has flushed. A new recorder starts at once. */
function cycleRecorder(keep?: (blob: Blob) => void): void {
  const old = recorder;
  const own = chunks;
  recorder = null;
  if (old && old.state !== "inactive") {
    old.onstop = keep ? () => keep(new Blob(own, { type: old.mimeType || own[0]?.type || "audio/mp4" })) : null;
    try {
      old.stop();
    } catch {
      /* already stopped */
    }
  }
  if (running) newRecorder();
}

function level(): number {
  if (!analyser) return 0;
  const data = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(data);
  let sum = 0;
  for (const byte of data) {
    const v = (byte - 128) / 128;
    sum += v * v;
  }
  return Math.sqrt(sum / data.length);
}

const armed = (at: number) => at < armedUntil;

function setHeard(heard: string): void {
  useTwin.setState({ handsFreeStatus: "heard", handsFreeHeard: heard, handsFreeSpoken: true });
}

async function transcribe(blob: Blob, startedAt: number): Promise<void> {
  const mine = run;
  const type = (blob.type || "audio/mp4").split(";")[0];
  let text = "";
  try {
    const response = await fetch("/api/transcribe", { method: "POST", headers: { "Content-Type": type }, body: blob });
    if (!response.ok) {
      if (response.status === 503) console.warn("Hey Wanda on this phone needs ELEVENLABS_API_KEY on the server.");
      return;
    }
    text = String(((await response.json()) as { text?: string }).text ?? "");
  } catch {
    return; // offline or the server is gone: the next utterance tries again
  }
  if (mine !== run || !running) return; // hands-free went off meanwhile
  const route = routeTranscript(text, armed(startedAt));
  if (!route) return;
  armedUntil = 0;
  const wake = parseWake(text);
  if (wake) earcon();
  setHeard(wake ? wake.rest : text);
  pendingArm = { at: Date.now(), spoke: false, force: !!wake && !wake.rest }; // bare "Hey Wanda": always wait for the question
  void handler(text);
}

function tick(): void {
  if (!running) return;
  const now = Date.now();
  if (context && context.state !== "running") void context.resume().catch(() => {});
  const state = useTwin.getState();
  const busy = isSpeaking() || speechPending();
  if (busy) quietSince = 0;
  else quietSince ||= now;

  // The follow-up window: once Wanda has answered and is quiet again, the next question needs no wake word.
  if (pendingArm) {
    if (busy || state.chatBusy) pendingArm.spoke = true;
    else if (pendingArm.spoke && now - quietSince >= AFTER_SPEECH_MS) {
      const force = pendingArm.force;
      pendingArm = null;
      if (state.followUp || force) {
        armedUntil = now + ARMED_MS;
        setHeard("");
      } else if (state.handsFreeStatus === "heard") useTwin.setState({ handsFreeStatus: "listening" });
    } else if (!pendingArm.spoke && now - pendingArm.at > WAIT_FOR_SPEECH_MS) pendingArm = null;
  }
  if (armedUntil && now >= armedUntil) {
    armedUntil = 0;
    if (useTwin.getState().handsFreeStatus === "heard") useTwin.setState({ handsFreeStatus: "listening", handsFreeHeard: "" });
  }

  // Not while Wanda speaks or just stopped (her own voice), nor while the agent thinks. While she speaks the mic is
  // released: an open capture on iOS turns the reply down or sends it to the earpiece.
  if (busy) releaseMic();
  if (busy || now - quietSince < AFTER_SPEECH_MS || state.chatBusy) {
    if (vad.phase !== "idle") {
      vad = { ...vad, phase: "idle" };
      cycleRecorder(); // drop what was recorded
    }
    return;
  }
  if (!stream) {
    acquireMic();
    return;
  }
  if (!recorder) newRecorder();
  const step = vadStep(vad, level(), now);
  const startedAt = vad.since;
  vad = step.vad;
  if (step.event === "send") cycleRecorder((blob) => void transcribe(blob, startedAt));
  else if (step.event === "drop") cycleRecorder();
  else if (vad.phase === "idle" && now - recorderStarted > RECYCLE_MS) cycleRecorder();
}

let acquiring = false;

function acquireMic(): void {
  if (acquiring || stream || !running || !context) return;
  acquiring = true;
  const mine = run;
  void navigator.mediaDevices
    .getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
    .then((media) => {
      acquiring = false;
      if (mine !== run || !running || !context || stream) {
        media.getTracks().forEach((track) => track.stop());
        return;
      }
      stream = media;
      source = context.createMediaStreamSource(media);
      analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      vad = { ...vadInit(), floor: vad.floor };
      newRecorder();
    })
    .catch((error: { name?: string }) => {
      acquiring = false;
      if (mine !== run) return;
      stopWakeListen();
      const code = error?.name === "NotAllowedError" ? "not-allowed" : "audio-capture";
      useTwin.setState({ handsFree: false, handsFreeNotice: voiceHint(code) });
    });
}

/** Stop recording and close the capture (the listener keeps running and takes the mic again when it may). */
function releaseMic(): void {
  if (!stream) return;
  const media = stream;
  stream = null; // first, so cycleRecorder does not start a new recorder on it
  cycleRecorder();
  try {
    source?.disconnect();
  } catch {
    /* already gone */
  }
  source = null;
  analyser = null;
  media.getTracks().forEach((track) => track.stop());
  vad = { ...vad, phase: "idle" };
}

/** Start listening for "Hey Wanda" (call from the hands-free switch; the first call should be inside a tap). */
export function startWakeListen(onUtterance: Handler): void {
  handler = onUtterance;
  if (running) return;
  running = true;
  run++;
  vad = vadInit();
  quietSince = 0;
  try {
    const w = window as unknown as { AudioContext?: AudioCtor; webkitAudioContext?: AudioCtor };
    const Ctor = (w.AudioContext ?? w.webkitAudioContext) as AudioCtor;
    if (!context || context.state === "closed") context = new Ctor();
    void context.resume().catch(() => {}); // inside the tap on iOS
  } catch {
    context = null;
  }
  acquireMic(); // inside the tap: the permission prompt
  window.clearInterval(timer);
  timer = window.setInterval(tick, TICK_MS);
}

/** Stop listening and release the microphone (push-to-talk needs it; iOS allows one capture at a time). */
export function stopWakeListen(): void {
  if (!running && !stream) return;
  running = false;
  run++;
  window.clearInterval(timer);
  armedUntil = 0;
  pendingArm = null;
  releaseMic();
  vad = vadInit();
}

// A reply is about to play: let go of the mic first (the tick takes it again once she is quiet).
onBeforePlay(() => {
  if (running) releaseMic();
});

if (typeof window !== "undefined") {
  // For browser tests: is the wake listener running (and holding the mic)?
  (window as unknown as { __wakeListen: unknown }).__wakeListen = {
    running: () => running,
    supported: wakeListenSupported,
    debug: () => ({ level: Math.round(level() * 1000), floor: Math.round(vad.floor * 1000), mic: !!stream, acquiring, phase: vad.phase, armed: armedUntil > Date.now(), speaking: isSpeaking(), pending: speechPending() }),
  };
}
