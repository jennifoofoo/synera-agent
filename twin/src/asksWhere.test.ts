// Detector for "Wanda asks where you are": run with `npm test` in twin/ (vitest).
import { expect, test } from "vitest";
import { asksWhereYouAre, lastQuestion } from "./asksWhere";

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
