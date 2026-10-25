// Wake word table: run with `npm test` in twin/ (vitest).
import { expect, test } from "vitest";
import { parseWake } from "./wake";

// [what the recogniser wrote, the question that remains]
const POSITIVES: [string, string][] = [
  ["Hey Wanda", ""],
  ["hey wanda where is the toilet", "where is the toilet"],
  ["Hey, Wanda! Where is the toilet?", "where is the toilet"],
  ["hi wanda", ""],
  ["ok wanda what's next", "what's next"],
  ["Okay Wanda, how far", "how far"],
  ["hallo wanda", ""],
  ["Wanda", ""],
  ["wanda where is the kitchen", "where is the kitchen"],
  ["Evander", ""],
  ["Evander where is the toilet", "where is the toilet"],
  ["E Wander", ""],
  ["e wander where is the coffee machine", "where is the coffee machine"],
  ["hey evander", ""],
  ["hey evander where is the toilet", "where is the toilet"],
  ["Ivanda", ""],
  ["a wanda", ""],
  ["hey wonder", ""],
  ["hey wonder where is the exit", "where is the exit"],
  ["hey wanda's", ""],
  ["Hey Wanda's where is the lift", "where is the lift"],
  ["vanda", ""],
  ["wonda", ""],
  ["Wander", ""],
  ["juanda", ""],
  ["hey vanda", ""],
  ["hey vanda next", "next"],
  ["hey e wander", ""],
  ["hey wenda where is room 3", "where is room 3"],
];

const NEGATIVES = [
  "wonderful",
  "wonderful view from here",
  "wander around the hall",
  "I wonder where the toilet is",
  "i wonder",
  "where is the wander",
  "where is the toilet",
  "and the coffee machine?",
  "how far is it",
  "next",
  "Amanda is in the kitchen",
  "hey where is the toilet",
  "hey what's up",
  "hey wendy",
  "the wanda is here",
  "",
  "   ",
];

for (const [said, rest] of POSITIVES) {
  test(`wakes: ${JSON.stringify(said)}`, () => {
    expect(parseWake(said)).toEqual({ rest });
  });
}

for (const said of NEGATIVES) {
  test(`does not wake: ${JSON.stringify(said)}`, () => {
    expect(parseWake(said)).toBeNull();
  });
}
