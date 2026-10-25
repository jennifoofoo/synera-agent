// "Yes" to Wanda's guiding offer starts the page's walk: run with `npm test` in twin/ (vitest).
import { expect, test } from "vitest";
import { acceptsGuiding, offersGuiding } from "./guideYes";

const OFFERS = [
  "The nearest toilet is Toilet 0.22, about 32 metres from you. Want me to talk you through it while you walk?",
  "Toilet 0.22 is 32 m away. Do you want me to guide you there?",
  "Die nächste Küche ist Küche 1.07. Soll ich dich Schritt für Schritt begleiten?",
  "Shall I guide you there?",
];

test("a plain yes to a guiding offer starts the walk (Jennifer's 'Wanda yes guide me')", () => {
  for (const offer of OFFERS) {
    for (const yes of ["yes", "Yes.", "Wanda yes guide me", "Hey Wanda, yes please", "ja", "Ja, gerne", "okay", "sure, go"]) {
      expect(acceptsGuiding(yes, offer), `${yes} after ${offer}`).toBe(true);
    }
  }
});

test("'guide me' alone always starts the walk (the old shortcut)", () => {
  expect(acceptsGuiding("guide me", undefined)).toBe(true);
  expect(acceptsGuiding("Guide me.", "Toilet 0.22 is on the ground floor.")).toBe(true);
});

test("no walk without a guiding offer or without a plain yes", () => {
  const offer = OFFERS[0];
  expect(acceptsGuiding("yes", "The east lift will be closed for everyone. Shall I apply that?")).toBe(false);
  expect(acceptsGuiding("yes", "Toilet 0.22 is on the ground floor.")).toBe(false);
  expect(acceptsGuiding("yes", undefined)).toBe(false);
  expect(acceptsGuiding("no", offer)).toBe(false);
  expect(acceptsGuiding("yes but to the other toilet", offer)).toBe(false);
  expect(acceptsGuiding("ja aber zur anderen Küche", offer)).toBe(false);
  expect(acceptsGuiding("where is the kitchen?", offer)).toBe(false);
  expect(acceptsGuiding("yes and then tell me where the nearest coffee machine on floor two is please", offer)).toBe(false);
});

test("only the last sentence counts as the offer", () => {
  expect(offersGuiding("I can guide you there. Toilet 0.22 is 32 m away.")).toBe(false);
  expect(offersGuiding(OFFERS[1])).toBe(true);
});
