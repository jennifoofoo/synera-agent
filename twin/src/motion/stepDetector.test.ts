import { describe, expect, it } from "vitest";
import { detectSteps, StepDetector, stepLength } from "./stepDetector";
import { shakeTrace, standingTrace, walkingTrace } from "./synthetic";

describe("step detection", () => {
  it("counts 2 Hz walking with noise", () => {
    const steps = detectSteps(walkingTrace(2, { durationS: 10, noise: 0.4 }));
    // 20 bounces; the filter needs a moment to settle, the bout releases from its third step
    expect(steps.length).toBeGreaterThanOrEqual(17);
    expect(steps.length).toBeLessThanOrEqual(21);
    expect(steps[steps.length - 1].cadenceHz).toBeCloseTo(2, 0);
  });

  it("counts slow (1.2 Hz) and fast (2.8 Hz) walking", () => {
    const slow = detectSteps(walkingTrace(1.2, { durationS: 10, seed: 3 }));
    expect(slow.length).toBeGreaterThanOrEqual(10);
    expect(slow.length).toBeLessThanOrEqual(13);
    const fast = detectSteps(walkingTrace(2.8, { durationS: 10, seed: 4 }));
    expect(fast.length).toBeGreaterThanOrEqual(24);
    expect(fast.length).toBeLessThanOrEqual(29);
  });

  it("counts no steps while standing still", () => {
    expect(detectSteps(standingTrace({ durationS: 20, noise: 0.3 }))).toHaveLength(0);
  });

  it("limits steps from a shake burst", () => {
    const steps = detectSteps(shakeTrace({ durationS: 3 }));
    expect(steps.length).toBeLessThanOrEqual(2);
  });

  it("limits steps when a shake interrupts standing", () => {
    const trace = [
      ...standingTrace({ durationS: 3 }),
      ...shakeTrace({ durationS: 2, startMs: 3000 }),
      ...standingTrace({ durationS: 3, startMs: 5000 }),
    ];
    expect(detectSteps(trace).length).toBeLessThanOrEqual(2);
  });

  it("keeps at least 300 ms between steps", () => {
    const steps = detectSteps(walkingTrace(2.5, { durationS: 8 }));
    for (let i = 1; i < steps.length; i++) expect(steps[i].t - steps[i - 1].t).toBeGreaterThanOrEqual(300);
  });

  it("needs a bout of three steps, a single bump is not a step", () => {
    const detector = new StepDetector();
    const trace = [...standingTrace({ durationS: 2 }), ...walkingTrace(2, { durationS: 0.6, startMs: 2000 }), ...standingTrace({ durationS: 4, startMs: 2600 })];
    expect(trace.flatMap((s) => detector.push(s))).toHaveLength(0);
  });

  it("ignores broken samples", () => {
    const detector = new StepDetector();
    expect(detector.push({ t: 0, x: Number.NaN, y: 0, z: 9.8 })).toEqual([]);
  });
});

describe("step length", () => {
  it("is 0.7 m at a normal cadence and clamps to 0.5..0.9", () => {
    expect(stepLength(1.8)).toBeCloseTo(0.7);
    expect(stepLength(2.4)).toBeGreaterThan(0.7);
    expect(stepLength(10)).toBe(0.9);
    expect(stepLength(0.2)).toBe(0.5);
    expect(stepLength(0)).toBe(0.7);
    expect(stepLength(2.4, 0.7, false)).toBe(0.7);
  });
});
