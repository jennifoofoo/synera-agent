// Facts about the walk in progress, from the route's step lines only (deterministic, no agent).
// Shared by the step sheet (ui/Walk.tsx) and the hands-free voice commands (handsFree.ts).

import { useTwin, walkSteps } from "./store";

/** Walking time in whole minutes (1.2 m/s indoors, at least 1). */
export function walkMinutes(lengthM: number): number {
  return Math.max(1, Math.round(lengthM / 72));
}

/** The server's step lines name rooms as "Office 0.46 [building-F0-S046]"; the id in brackets is not for people. */
export function readable(line: string): string {
  return line.replace(/\s*\[[^\]]*\]/g, "");
}

/** Metres named in a step line ("Walk about 11 m …"). */
export function metresIn(line: string): number {
  return [...line.matchAll(/(\d+(?:\.\d+)?)\s*m\b/g)].reduce((sum, m) => sum + Number(m[1]), 0);
}

/** Metres left from step `step` on: the metres named in the remaining lines, scaled to the route length. */
export function metresLeft(steps: string[], step: number, lengthM: number | undefined): number | null {
  if (lengthM === undefined || !steps.length) return null;
  const all = steps.reduce((sum, line) => sum + metresIn(line), 0);
  const left = steps.slice(step).reduce((sum, line) => sum + metresIn(line), 0);
  return Math.round(all > 0 ? (lengthM * left) / all : lengthM * (1 - step / steps.length));
}

/** Where the walker should be at the start of step `step`: where the step before ended (or the start line). */
export function placeAt(steps: string[], step: number): string | null {
  const before = readable(steps[Math.max(0, step - 1)] ?? "").replace(/\.$/, "");
  if (step === 0) {
    const start = /^Start (?:in|at) (.+)$/i.exec(before);
    return start ? start[1] : null;
  }
  const arrived = /arrived at (.+)$/i.exec(before);
  if (arrived) return arrived[1];
  const into = /\b(?:into|to|at) (.+)$/i.exec(before);
  return into ? into[1] : null;
}

/** The current walk in plain words, or null when not walking. */
export function walkNow(): { steps: string[]; step: number; last: boolean; left: number | null } | null {
  const { walkStep, state } = useTwin.getState();
  const steps = walkSteps().map(readable);
  if (walkStep === null || !steps.length) return null;
  return { steps, step: walkStep, last: walkStep >= steps.length - 1, left: metresLeft(steps, walkStep, state?.route?.length_m) };
}
