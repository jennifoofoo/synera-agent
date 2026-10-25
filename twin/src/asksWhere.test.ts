// Detector for "Wanda asks where you are": run with `npm test` in twin/ (vitest).
import { expect, test } from "vitest";
import { asksWhereYouAre, lastQuestion, waitsForPlace } from "./asksWhere";

const POSITIVES = [
  "Where are you?",
  "Which room are you in?",
  "Which room are you in on Ground floor?",
  "I can find the nearest coffee machine, but I need your position first. Where are you?",
  "I need a starting point. Which room are you in?\nAnswer: unknown",
  "Where are you now?",
  "Where are you right now? Tap the map or tell me the room.",
  "What room are you in?",
  "To route you I need to know: where are you standing?",
  "**Which room are you in?**",
  "Wo bist du?",
  "In welchem Raum bist du gerade?",
  "Ich brauche deinen Standort. Wo befindest du dich?",
  "In welchem Raum sind Sie?",
];

const NEGATIVES = [
  "",
  "The nearest coffee machine is in Kitchen 1.30, 12 m away.",
  "Where is the coffee machine? It is in the kitchen.",
  "Do you want me to guide you there?",
  "Where are you going?",
  "Where are you heading next?",
  "Wo bist du hin unterwegs?",
  "You are in Kitchen 1.30. Shall I start the route?",
  "Which room do you want to go to?",
  "Where are you? I found you in Kitchen 1.30. Want directions?",
];

test.each(POSITIVES)("asks where: %s", (reply) => {
  expect(asksWhereYouAre(reply)).toBe(true);
});

test.each(NEGATIVES)("does not ask where: %s", (reply) => {
  expect(asksWhereYouAre(reply)).toBe(false);
});

test("null and undefined are no question", () => {
  expect(asksWhereYouAre(null)).toBe(false);
  expect(asksWhereYouAre(undefined)).toBe(false);
});

test("lastQuestion takes the final question, without the Answer line", () => {
  expect(lastQuestion("Okay. Where are you?\nAnswer: none")).toBe("where are you?");
  expect(lastQuestion("No question here.")).toBe("");
});

const BUG_REPLY =
  "I can't see a spot marked on the map yet. Could you tap the room you're in on the plan, or tell me its name or number? Then I'll find the closest toilet for you.";

test("needs_position from the server makes Wanda wait for a place, whatever the text", () => {
  expect(waitsForPlace({ reply: "Okay.", needs_position: true }, "Hello")).toBe(true);
});

test("the demo bug: 'tap the room you're in' after a where question waits for a place", () => {
  expect(waitsForPlace({ reply: BUG_REPLY }, "Where is the nearest toilet?")).toBe(true);
  expect(waitsForPlace({ reply: BUG_REPLY }, "Wo ist die nächste Toilette?")).toBe(true);
});

test("the text fallback needs a routing question from the person", () => {
  expect(waitsForPlace({ reply: BUG_REPLY }, "Tell me a joke")).toBe(false);
});

test("no wait for an error, a plain answer or a question about something else", () => {
  expect(waitsForPlace({ reply: "Which room are you in?", error: "agent" }, "Where is the toilet?")).toBe(false);
  expect(waitsForPlace({ reply: "The nearest toilet is WC 0.12, 14 m away." }, "Where is the nearest toilet?")).toBe(false);
  expect(waitsForPlace({ reply: "There are two toilets. Which one do you want, WC 0.12 or WC 1.04?" }, "Where is the toilet?")).toBe(false);
  expect(waitsForPlace({ reply: "Shall I guide you there?" }, "Where is the nearest toilet?")).toBe(false);
  expect(waitsForPlace(null, "Where is the toilet?")).toBe(false);
});

test("the old heuristic still counts without the flag", () => {
  expect(waitsForPlace({ reply: "Where are you?" }, "anything")).toBe(true);
});
