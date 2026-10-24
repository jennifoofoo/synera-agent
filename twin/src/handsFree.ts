// Hands-free voice with the wake word "Hey Wanda" (owner: hands-free session).
// While store.handsFree is on, one continuous speech recognition runs (Chrome's webkitSpeechRecognition) and is
// restarted with backoff whenever it ends. Only utterances that start with the wake word count. Walking commands
// (next, back, repeat, how far, stop, where am I; English and German) run locally and instantly from the route's
// step lines; anything else goes to the agent through the normal chat path (ask with voice) and the reply is spoken.
// Saying the wake word while Wanda speaks stops her (barge-in); everything else heard while she speaks is ignored,
// so her own voice cannot trigger a command.

import { useTwin } from "./store";
import { voiceHint } from "./ui/phoneHints";
import { earcon, isSpeaking, keepAwake, recognitionCtor, speak, stopSpeaking, type Recognition, type RecognitionResult } from "./voice";
import { placeAt, walkMinutes, walkNow } from "./walkInfo";
import { ABOUT_THERE, walkWithMeDriving } from "./walkWithMe";

export type Command = "next" | "back" | "repeat" | "howFar" | "stop" | "where";

const BASE_BACKOFF_MS = 250;
const MAX_BACKOFF_MS = 8000;
/** After a bare "Hey Wanda", the next utterance is the command if it comes within this time. */
const ARMED_MS = 5000;
const FATAL = new Set(["not-allowed", "service-not-allowed", "audio-capture"]);
const LANG_PREF = "twin.handsFreeLang";

function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}'\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// "hey wanda", "hi wanda", "hallo wanda", "hey wonder", and a bare "wanda"/"wonda"/"wander" at the very start.
const WAKE = /^(?:(?:hey|hi|hallo|hello|ok|okay) ?(?:wanda|wonda|wander|wonder|vanda)|wanda|wonda|wander)\b ?/;

/** The text after the wake word, or null when the utterance does not start with it. */
export function parseWake(text: string): { rest: string } | null {
  const said = normalize(text);
  const match = WAKE.exec(said);
  return match ? { rest: said.slice(match[0].length).trim() } : null;
}

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
  const said = normalize(text)
    .replace(/^(?:please|bitte) /, "")
    .replace(/ (?:please|bitte)$/, "");
  return COMMANDS.find(([, pattern]) => pattern.test(said))?.[0] ?? null;
}

function say(text: string): void {
  void speak(text, useTwin.getState().speechAvailable);
}

function setStatus(handsFreeStatus: "listening" | "heard" | "thinking", handsFreeHeard = ""): void {
  useTwin.setState({ handsFreeStatus, handsFreeHeard });
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

/** What to do with a command spoken after the wake word. */
export async function handleUtterance(text: string): Promise<void> {
  const command = parseCommand(text);
  if (command && (walkNow() || command === "stop")) {
    setStatus("listening");
    runLocal(command);
    return;
  }
  const state = useTwin.getState();
  if (state.chatBusy) return;
  if (!state.chatAvailable) {
    setStatus("listening");
    say("Asking is off on this server.");
    return;
  }
  stopSpeaking();
  setStatus("thinking", text);
  const reply = await state.ask(text, true);
  if (useTwin.getState().handsFree) setStatus("listening");
  if (reply) say(reply.reply);
}

// ---- the recognition loop ----

let recognition: Recognition | null = null;
let restartTimer = 0;
let backoff = BASE_BACKOFF_MS;
let paused = false;
let armedUntil = 0;
let armTimer = 0;
// Per recognition session, by result index: seen once, began while Wanda spoke, chimed, finished.
let session = { seen: new Set<number>(), duringSpeech: new Set<number>(), chimed: new Set<number>(), done: new Set<number>() };

function language(): string {
  try {
    return localStorage.getItem(LANG_PREF) || "en-US";
  } catch {
    return "en-US";
  }
}

const enabled = () => useTwin.getState().handsFree;
const armed = () => Date.now() < armedUntil;

function arm(): void {
  armedUntil = Date.now() + ARMED_MS;
  window.clearTimeout(armTimer);
  setStatus("heard");
  armTimer = window.setTimeout(() => {
    armedUntil = 0;
    if (useTwin.getState().handsFreeStatus === "heard") setStatus("listening");
  }, ARMED_MS);
}

function disarm(): void {
  armedUntil = 0;
  window.clearTimeout(armTimer);
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
    }
    const wake = parseWake(raw);
    if (wake) {
      if (speaking) stopSpeaking(); // barge-in
      session.duringSpeech.delete(index); // spoken over Wanda on purpose: it counts
      if (!session.chimed.has(index)) {
        session.chimed.add(index);
        earcon();
      }
      setStatus("heard", wake.rest);
    } else if (armed() && !session.duringSpeech.has(index) && raw) {
      setStatus("heard", raw);
    }
    if (!result.isFinal) continue;
    session.done.add(index);
    if (wake && wake.rest) {
      disarm();
      void handleUtterance(wake.rest);
    } else if (wake) {
      arm();
    } else if (armed() && !session.duringSpeech.has(index) && raw) {
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
  session = { seen: new Set(), duringSpeech: new Set(), chimed: new Set(), done: new Set() };
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
