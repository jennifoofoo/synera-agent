// Hands-free voice with the wake word "Hey Wanda" (owner: hands-free session).
// While store.handsFree is on, one continuous speech recognition runs (Chrome's webkitSpeechRecognition) and is
// restarted with backoff whenever it ends. Only utterances that start with the wake word count. Walking commands
// (next, back, repeat, how far, stop, where am I; English and German) run locally and instantly from the route's
// step lines; anything else goes to the agent through the normal chat path (ask with voice) and the reply is spoken.
// Saying the wake word while Wanda speaks stops her (barge-in); everything else heard while she speaks is ignored,
// so her own voice cannot trigger a command.
// Follow-up listening (setting store.followUp, default on): after Wanda finishes speaking a voice reply (hands-free or
// push-to-talk turn), the mic stays open for FOLLOW_UP_MS without wake word or button. Hands-free arms its running
// recognition; otherwise one short listen runs. Not on Safari/iOS (no dependable continuous recognition there).

import { voiceHint } from "./ui/phoneHints";
import { handsFreeMuted, useTwin } from "./store";
import {
  continuousRecognitionLikely,
  earcon,
  isSpeaking,
  keepAwake,
  listen,
  recognitionCtor,
  speak,
  speechPending,
  stopSpeaking,
  type Listener,
  type Recognition,
  type RecognitionResult,
} from "./voice";
import { normalizeSpeech, parseWake } from "./wake";
import { placeAt, walkMinutes, walkNow } from "./walkInfo";
import { ABOUT_THERE, walkWithMeDriving } from "./walkWithMe";

export type Command = "next" | "back" | "repeat" | "howFar" | "stop" | "where";

const BASE_BACKOFF_MS = 250;
const MAX_BACKOFF_MS = 8000;
/** After a bare "Hey Wanda", the next utterance is the command if it comes within this time. */
const ARMED_MS = 5000;
/** Follow-up listening: how long the mic stays open after Wanda finished speaking. */
const FOLLOW_UP_MS = 8000;
/** Quiet time after the reply audio ended before the mic opens (no echo of Wanda's last word). */
const AFTER_SPEECH_MS = 450;
/** How long to wait for a reply to start speaking at all (the step sheet speaks a moment after "next"). */
const WAIT_FOR_SPEECH_MS = 1500;
const FATAL = new Set(["not-allowed", "service-not-allowed", "audio-capture"]);
const LANG_PREF = "twin.handsFreeLang";

export { parseWake };

const COMMANDS: [Command, RegExp][] = [
  ["next", /^(?:next(?: step)?|weiter|ok|okay|done|fertig|bin da|ich bin da|i'?m here|i am here|i'?m there|go on|continue)$/],
  ["back", /^(?:back|go back|previous(?: step)?|zurück|zurueck)$/],
  ["repeat", /^(?:again|repeat(?: that)?|say (?:it|that) again|noch ?mal|wiederholen|wiederhole|wiederhol das)$/],
  ["howFar", /^(?:how far(?: is it)?(?: still)?(?: to go)?|how much further|wie weit(?: noch| ist es(?: noch)?)?)$/],
  ["stop", /^(?:stop|stopp|end|ende|beenden|cancel|end guidance|abbrechen)$/],
  ["where", /^(?:where am i|wo bin ich)$/],
];

/** A local walking command, or null for anything else (that goes to the agent). */
export function parseCommand(text: string): Command | null {
  const said = normalizeSpeech(text)
    .replace(/^(?:please|bitte) /, "")
    .replace(/ (?:please|bitte)$/, "");
  return COMMANDS.find(([, pattern]) => pattern.test(said))?.[0] ?? null;
}

function say(text: string): Promise<void> {
  return speak(text, useTwin.getState().speechAvailable);
}

function setStatus(handsFreeStatus: "listening" | "heard" | "thinking", handsFreeHeard = ""): void {
  useTwin.setState(handsFreeStatus === "listening" ? { handsFreeStatus, handsFreeHeard } : { handsFreeStatus, handsFreeHeard, handsFreeSpoken: true });
}

/** Run a walking command on the walk in progress. */
function runLocal(command: Command): void {
  const state = useTwin.getState();
  const walk = walkNow();
  if (!walk) {
    if (command === "stop") stopSpeaking();
    return;
  }
  const { steps, step, last, left } = walk;
  switch (command) {
    case "next":
      if (last) {
        state.stopWalk();
        void state.clearRoute();
        say(walkWithMeDriving() ? ABOUT_THERE : "You're there.");
      } else state.setWalkStep(step + 1); // the step sheet reads the new step out
      return;
    case "back":
      if (step > 0) state.setWalkStep(step - 1);
      else say(steps[0]);
      return;
    case "repeat":
      say(steps[step]);
      return;
    case "howFar": {
      if (left === null) say(`${steps.length - step} steps left.`);
      else {
        const minutes = walkMinutes(left);
        say(`${walkWithMeDriving() ? "About " : ""}${left} metres left, about ${minutes} minute${minutes === 1 ? "" : "s"}.`);
      }
      return;
    }
    case "stop":
      state.stopWalk();
      void state.clearRoute();
      say("Guidance ended.");
      return;
    case "where": {
      const place = placeAt(steps, step);
      say(place ? `You should be at ${place}.` : steps[step]);
      return;
    }
  }
}

/** What to do with a command spoken after the wake word, or in the follow-up window. A leading wake word is
 * dropped; the wake word alone answers "I'm here." and keeps listening for the question. */
export async function handleUtterance(text: string): Promise<void> {
  const wake = parseWake(text);
  if (wake && !wake.rest) {
    imHere();
    return;
  }
  if (wake) text = wake.rest;
  const command = parseCommand(text);
  if (command && (walkNow() || command === "stop")) {
    setStatus("listening");
    runLocal(command);
    followUpAfterSpeech();
    return;
  }
  const state = useTwin.getState();
  if (state.chatBusy) return;
  if (!state.chatAvailable) {
    setStatus("listening");
    void say("Asking is off on this server.");
    return;
  }
  stopSpeaking();
  setStatus("thinking", text);
  const reply = await state.ask(text, true);
  if (useTwin.getState().handsFree) setStatus("listening");
  if (reply) void say(reply.reply);
  followUpAfterSpeech(); // also after a walking word the store handled (the step sheet speaks the step)
}

/** The wake word alone (hands-free or push-to-talk): "I'm here." and listen for the question. */
export function imHere(): void {
  const { voiceOut, handsFree } = useTwin.getState();
  if (voiceOut || handsFree) {
    void say("I'm here.");
    followUpAfterSpeech({ force: true });
  } else {
    cancelFollowUp();
    followTimer = window.setTimeout(() => openFollowUp(true), AFTER_SPEECH_MS);
  }
}

// ---- follow-up listening ----

const FOLLOW_UP_PREF = "twin.followUp";

/** The "Follow-up listening" setting (default on), remembered per browser. */
export function followUpPref(): boolean {
  try {
    return localStorage.getItem(FOLLOW_UP_PREF) !== "off";
  } catch {
    return true;
  }
}
export function setFollowUpPref(on: boolean): void {
  try {
    localStorage.setItem(FOLLOW_UP_PREF, on ? "on" : "off");
  } catch {
    /* private mode: not remembered */
  }
  useTwin.setState({ followUp: on });
  if (!on) cancelFollowUp();
}

let followRun = 0;
let followTimer = 0;
let followListener: Listener | null = null;

/** Close the follow-up window (or stop waiting for it): a tap on Talk, barge-in, mute. */
export function cancelFollowUp(): void {
  followRun++;
  window.clearTimeout(followTimer);
  const listener = followListener;
  followListener = null;
  listener?.cancel();
  if (followUpArmed) disarm();
  if (useTwin.getState().followUpOpen) useTwin.setState({ followUpOpen: false, followUpHeard: "" });
}

/** After a voice reply: wait until Wanda has finished speaking, then open the mic for the next question.
 * Opens only when something was really spoken (or `force`, for the bare wake word). */
export function followUpAfterSpeech(opts: { force?: boolean } = {}): void {
  cancelFollowUp();
  const run = followRun;
  const begun = Date.now();
  let spoke = false;
  let quietSince = 0;
  const tick = () => {
    if (run !== followRun) return;
    const now = Date.now();
    if (isSpeaking() || speechPending()) {
      spoke = true;
      quietSince = 0;
    } else if (spoke || opts.force) {
      quietSince ||= now;
      if (now - quietSince >= AFTER_SPEECH_MS) return openFollowUp(!!opts.force);
    } else if (now - begun > WAIT_FOR_SPEECH_MS) return; // nothing was said: no follow-up
    followTimer = window.setTimeout(tick, 100);
  };
  tick();
}

function followUpAllowed(force: boolean): boolean {
  const state = useTwin.getState();
  if (!force && !state.followUp) return false;
  if (!state.handsFree && handsFreeMuted()) return false; // the person muted Wanda's mic
  if (!continuousRecognitionLikely() || document.visibilityState === "hidden") return false;
  return !state.chatBusy && !paused; // paused: push-to-talk is listening
}

function openFollowUp(force: boolean): void {
  if (!followUpAllowed(force)) return;
  earcon();
  useTwin.setState({ followUpOpen: true, followUpHeard: "" });
  if (useTwin.getState().handsFree) {
    arm(FOLLOW_UP_MS, true);
    return;
  }
  const run = followRun;
  let heard = "";
  let echo = false;
  const listener = listen("en-US", {
    onInterim: (said) => {
      if (isSpeaking()) echo = true; // Wanda (or the step sheet) spoke over it: never send that
      if (echo || followListener !== listener) return;
      heard = said;
      useTwin.setState({ followUpHeard: said });
    },
    onFinal: (said) => {
      if (!echo && followListener === listener && run === followRun) void handleUtterance(said);
    },
    onEnd: () => {
      if (followListener !== listener) return;
      followListener = null;
      window.clearTimeout(followTimer);
      useTwin.setState({ followUpOpen: false, followUpHeard: "" });
    },
  });
  followListener = listener;
  // Silence: close quietly. Someone is talking: let the sentence finish (listen ends itself).
  followTimer = window.setTimeout(() => {
    if (followListener === listener && !heard) cancelFollowUp();
  }, FOLLOW_UP_MS);
}

// ---- the recognition loop ----

let recognition: Recognition | null = null;
let restartTimer = 0;
let backoff = BASE_BACKOFF_MS;
let paused = false;
let armedUntil = 0;
let armTimer = 0;
// Per recognition session, by result index: seen once, began while Wanda spoke, chimed, finished.
// "unarmed": began before the wake word or the follow-up window, so it never counts as the command.
let session = newSession();

function newSession() {
  return { seen: new Set<number>(), duringSpeech: new Set<number>(), unarmed: new Set<number>(), chimed: new Set<number>(), done: new Set<number>() };
}

function language(): string {
  try {
    return localStorage.getItem(LANG_PREF) || "en-US";
  } catch {
    return "en-US";
  }
}

const enabled = () => useTwin.getState().handsFree;
const armed = () => Date.now() < armedUntil;

let followUpArmed = false;

function arm(ms = ARMED_MS, followUp = false): void {
  armedUntil = Date.now() + ms;
  followUpArmed = followUp;
  window.clearTimeout(armTimer);
  setStatus("heard");
  armTimer = window.setTimeout(() => {
    armedUntil = 0;
    if (useTwin.getState().handsFreeStatus === "heard") setStatus("listening");
    if (followUpArmed) endFollowUpWindow();
  }, ms);
}

function disarm(): void {
  armedUntil = 0;
  window.clearTimeout(armTimer);
  if (followUpArmed) endFollowUpWindow();
}

function endFollowUpWindow(): void {
  followUpArmed = false;
  if (useTwin.getState().followUpOpen) useTwin.setState({ followUpOpen: false, followUpHeard: "" });
}

function fail(message: string): void {
  halt();
  useTwin.setState({ handsFree: false, handsFreeNotice: message });
  window.setTimeout(() => {
    if (useTwin.getState().handsFreeNotice === message) useTwin.setState({ handsFreeNotice: null });
  }, 8000);
}

function onResult(results: ArrayLike<RecognitionResult>, from: number): void {
  for (let index = from; index < results.length; index++) {
    if (session.done.has(index)) continue;
    const result = results[index];
    const raw = (result[0]?.transcript ?? "").trim();
    const speaking = isSpeaking();
    if (!session.seen.has(index)) {
      session.seen.add(index);
      if (speaking) session.duringSpeech.add(index);
      if (!armed()) session.unarmed.add(index);
    }
    const wake = parseWake(raw);
    if (wake) {
      if (speaking) stopSpeaking(); // barge-in
      if (!armed()) cancelFollowUp(); // no follow-up window opening behind the new question
      session.duringSpeech.delete(index); // spoken over Wanda on purpose: it counts
      if (!session.chimed.has(index)) {
        session.chimed.add(index);
        earcon();
      }
      setStatus("heard", wake.rest);
    } else if (armed() && !session.duringSpeech.has(index) && !session.unarmed.has(index) && raw) {
      setStatus("heard", raw);
      if (followUpArmed) useTwin.setState({ followUpHeard: raw });
    }
    if (!result.isFinal) continue;
    session.done.add(index);
    if (wake && wake.rest) {
      disarm();
      void handleUtterance(wake.rest);
    } else if (wake) {
      arm();
    } else if (armed() && !session.duringSpeech.has(index) && !session.unarmed.has(index) && raw) {
      disarm();
      void handleUtterance(raw);
    }
  }
}

function start(): void {
  window.clearTimeout(restartTimer);
  if (!enabled() || paused || recognition || document.visibilityState === "hidden") return;
  const Ctor = recognitionCtor();
  if (!Ctor || !window.isSecureContext) {
    fail(voiceHint());
    return;
  }
  const current = new Ctor();
  current.lang = language();
  current.continuous = true;
  current.interimResults = true;
  session = newSession();
  current.onresult = (event) => {
    backoff = BASE_BACKOFF_MS;
    onResult(event.results, event.resultIndex);
  };
  current.onerror = (event) => {
    if (FATAL.has(event.error)) fail(voiceHint(event.error));
    else if (event.error !== "no-speech" && event.error !== "aborted") backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
  };
  current.onend = () => {
    if (recognition === current) recognition = null;
    schedule();
  };
  recognition = current;
  try {
    current.start();
  } catch {
    recognition = null;
    backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
    schedule();
  }
}

function schedule(): void {
  window.clearTimeout(restartTimer);
  if (enabled() && !paused) restartTimer = window.setTimeout(start, backoff);
}

function halt(): void {
  window.clearTimeout(restartTimer);
  disarm();
  const current = recognition;
  recognition = null;
  if (!current) return;
  current.onresult = null;
  current.onerror = null;
  current.onend = null;
  try {
    current.abort();
  } catch {
    /* already ended */
  }
}

/** Push-to-talk needs the mic: hands-free steps aside while it runs. */
export function pauseHandsFree(on: boolean): void {
  if (on) cancelFollowUp();
  paused = on;
  if (on) halt();
  else start();
}

let installed = false;

/** Call once at start-up: follows store.handsFree and the page's visibility. */
export function installHandsFree(): void {
  if (installed) return;
  installed = true;
  useTwin.subscribe((state, before) => {
    if (state.handsFree === before.handsFree) return;
    keepAwake("hands-free", state.handsFree);
    backoff = BASE_BACKOFF_MS;
    if (state.handsFree) start();
    else halt();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") halt();
    else start();
  });
}
