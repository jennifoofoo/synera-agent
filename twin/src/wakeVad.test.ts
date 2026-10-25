// iPhone wake word: VAD state machine and transcript routing. Run with `npm test` in twin/.
import { expect, test } from "vitest";
import { VAD, routeTranscript, vadInit, vadStep, type Vad, type VadEvent } from "./wakeVad";

/** Feed `ms` of a constant level in 50 ms ticks; return the final state and every event with its time. */
function feed(vad: Vad, level: number, from: number, ms: number): { vad: Vad; events: [number, VadEvent][]; now: number } {
  const events: [number, VadEvent][] = [];
  let now = from;
  for (; now < from + ms; now += 50) {
    const step = vadStep(vad, level, now);
    vad = step.vad;
    if (step.event) events.push([now, step.event]);
  }
  return { vad, events, now };
}

const QUIET = 0.003;
const LOUD = 0.15;

test("a normal utterance starts after the onset and is sent after the hang time", () => {
  let run = feed(vadInit(), QUIET, 0, 1000);
  expect(run.events).toEqual([]);
  run = feed(run.vad, LOUD, run.now, 1200);
  expect(run.events).toEqual([[1150, "start"]]);
  expect(run.vad.phase).toBe("speech");
  const end = feed(run.vad, QUIET, run.now, 1000);
  expect(end.events).toHaveLength(1);
  expect(end.events[0][1]).toBe("send");
  expect(end.events[0][0] - run.now).toBeGreaterThanOrEqual(VAD.hangMs - 50);
  expect(end.vad.phase).toBe("idle");
});

test("a short bang never starts; a short word is dropped", () => {
  let run = feed(vadInit(), QUIET, 0, 500);
  run = feed(run.vad, LOUD, run.now, 100); // shorter than the onset
  run = feed(run.vad, QUIET, run.now, 1000);
  expect(run.events).toEqual([]);
  run = feed(run.vad, LOUD, run.now, 250); // starts, but under minMs of speech
  expect(run.events.map((e) => e[1])).toEqual(["start"]);
  run = feed(run.vad, QUIET, run.now, 1000);
  expect(run.events.map((e) => e[1])).toEqual(["drop"]);
});

test("short pauses inside a sentence keep it together", () => {
  let run = feed(vadInit(), QUIET, 0, 500);
  run = feed(run.vad, LOUD, run.now, 600);
  expect(run.events.map((e) => e[1])).toEqual(["start"]);
  run = feed(run.vad, QUIET, run.now, 400); // a breath
  expect(run.events).toEqual([]);
  run = feed(run.vad, LOUD, run.now, 600);
  expect(run.events).toEqual([]);
  run = feed(run.vad, QUIET, run.now, 1000);
  expect(run.events.map((e) => e[1])).toEqual(["send"]);
});

test("endless talking is cut and sent after the maximum", () => {
  let run = feed(vadInit(), QUIET, 0, 500);
  run = feed(run.vad, LOUD, run.now, VAD.maxMs + 1000);
  expect(run.events.map((e) => e[1]).slice(0, 2)).toEqual(["start", "send"]); // then the next utterance starts
  const [[startAt], [sendAt]] = run.events;
  expect(sendAt - (startAt - VAD.onsetMs)).toBeGreaterThanOrEqual(VAD.maxMs);
});

test("a noisy room raises the threshold, so its hum is not speech", () => {
  const steady = feed(vadInit(), 0.03, 0, 3000); // a hum above minLevel from the start
  expect(steady.events).toEqual([]);
  const voice = feed(steady.vad, 0.2, steady.now, 300);
  expect(voice.events.map((e) => e[1])).toEqual(["start"]);
});

test("choppy speech (syllables with dips) never teaches the floor to ignore the voice", () => {
  let vad = feed(vadInit(), QUIET, 0, 1000).vad;
  let now = 1000;
  for (let round = 0; round < 10; round++) {
    // 100 ms loud, 100 ms quiet: never long enough for an onset, over and over
    for (let i = 0; i < 2; i++, now += 50) vad = vadStep(vad, LOUD, now).vad;
    for (let i = 0; i < 2; i++, now += 50) vad = vadStep(vad, QUIET, now).vad;
  }
  expect(feed(vad, LOUD, now, 300).events.map((e) => e[1])).toEqual(["start"]);
});

test("transcript routing: wake word, armed follow-up, or ignore", () => {
  expect(routeTranscript("Hey Wanda, next.", false)).toBe("wake");
  expect(routeTranscript("hi wanda how far", false)).toBe("wake");
  expect(routeTranscript("OK Wanda!", false)).toBe("wake");
  expect(routeTranscript("Wanda", false)).toBe("wake");
  expect(routeTranscript("Hey Vanda, where is the toilet?", false)).toBe("wake");
  expect(routeTranscript("hey wonder", false)).toBe("wake");
  expect(routeTranscript("Note: the door sticks", false)).toBeNull();
  expect(routeTranscript("I wonder where it is", false)).toBeNull();
  expect(routeTranscript("Note: the door sticks", true)).toBe("armed");
  expect(routeTranscript("  ...  ", true)).toBeNull();
});
