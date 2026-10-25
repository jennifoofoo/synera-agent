// Wheel classifier with recorded-like event sequences: run with `npm test` in twin/ (vitest).
import { describe, expect, test } from "vitest";
import { createTwist, createWheelClassifier, orbitDelta, wheelDevice, type WheelSample } from "./wheelInput";

const ev = (over: Partial<WheelSample>): WheelSample => ({ deltaX: 0, deltaY: 0, deltaMode: 0, ctrlKey: false, altKey: false, timeStamp: 0, ...over });

/** A sequence at ~60 Hz (16 ms apart) through one classifier. */
function run(samples: Partial<WheelSample>[], start = 1000, step = 16) {
  const classify = createWheelClassifier();
  return samples.map((s, i) => classify(ev({ timeStamp: start + i * step, ...s })));
}

describe("Chrome on a Mac trackpad", () => {
  test("two-finger swipe straight down pans, never zooms (small, then fast integer steps, then momentum)", () => {
    const swipe = [2, 4, 9, 18, 36, 64, 96, 120, 80, 40, 20, 8, 3, 1].map((deltaY) => ({ deltaY, wheelDeltaY: -3 * deltaY }));
    expect(run(swipe).every((a) => a === "pan")).toBe(true);
  });

  test("a fast swipe without legacy deltas stays a pan once it started small", () => {
    const swipe = [3, 12, 60, 100, 140, 100, 60].map((deltaY) => ({ deltaY }));
    expect(run(swipe).every((a) => a === "pan")).toBe(true);
  });

  test("diagonal and fractional swipes pan", () => {
    expect(run([{ deltaX: 1.5, deltaY: 0.5 }, { deltaX: 4, deltaY: -2 }, { deltaX: 12.25, deltaY: -6.5 }])).toEqual(["pan", "pan", "pan"]);
    expect(wheelDevice(ev({ deltaY: 7.3333 }))).toBe("trackpad");
    expect(wheelDevice(ev({ deltaX: -3 }))).toBe("trackpad");
  });

  test("a large first step that is -3x legacy is still a trackpad", () => {
    expect(wheelDevice(ev({ deltaY: 80, wheelDeltaY: -240 }))).toBe("trackpad");
  });

  test("pinch (ctrlKey) zooms, even mid-swipe", () => {
    expect(run([{ deltaY: -1.2, ctrlKey: true }, { deltaY: -3.4, ctrlKey: true }, { deltaY: 2, ctrlKey: true }])).toEqual(["pinch", "pinch", "pinch"]);
    expect(run([{ deltaY: 4 }, { deltaY: 6 }, { deltaY: -2, ctrlKey: true }])).toEqual(["pan", "pan", "pinch"]);
  });

  test("Option + swipe orbits", () => {
    expect(run([{ deltaX: 6, altKey: true }, { deltaY: 3.5, altKey: true }])).toEqual(["orbit", "orbit"]);
  });
});

describe("Safari", () => {
  test("trackpad swipe pans", () => {
    expect(run([{ deltaY: 1 }, { deltaY: 3 }, { deltaY: 7 }, { deltaY: 15 }, { deltaY: 51 }, { deltaY: 20 }]).every((a) => a === "pan")).toBe(true);
  });

  test("gesture twist turns only past the dead zone, then follows the fingers", () => {
    const twist = createTwist(8);
    expect(twist.step(3)).toBe(0);
    expect(twist.step(-7)).toBe(0);
    expect(twist.step(10)).toBe(0); // engages here
    expect(twist.step(40)).toBeCloseTo((30 * Math.PI) / 180);
    twist.reset();
    expect(twist.step(5)).toBe(0);
  });
});

describe("mouse wheel", () => {
  test("Chrome notches (100 px, legacy 120) zoom", () => {
    expect(run([{ deltaY: 100, wheelDeltaY: -120 }, { deltaY: 100, wheelDeltaY: -120 }], 1000, 60)).toEqual(["zoom", "zoom"]);
    expect(run([{ deltaY: -100, wheelDeltaY: 120 }], 5000)).toEqual(["zoom"]);
  });

  test("Firefox line mode zooms, even right after a trackpad swipe", () => {
    expect(run([{ deltaY: 3, deltaMode: 1 }, { deltaY: -3, deltaMode: 1 }])).toEqual(["zoom", "zoom"]);
    expect(run([{ deltaY: 2 }, { deltaY: 3, deltaMode: 1 }])).toEqual(["pan", "zoom"]);
  });

  test("large whole Y steps without legacy deltas zoom", () => {
    expect(run([{ deltaY: 120 }], 2000)).toEqual(["zoom"]);
    expect(run([{ deltaY: -53 }], 2000)).toEqual(["zoom"]);
  });

  test("a notch after a pause is classified fresh", () => {
    const classify = createWheelClassifier();
    expect(classify(ev({ deltaY: 2, timeStamp: 0 }))).toBe("pan");
    expect(classify(ev({ deltaY: 100, wheelDeltaY: -120, timeStamp: 500 }))).toBe("zoom");
  });

  test("Alt + wheel orbits (no longer zooms)", () => {
    expect(run([{ deltaY: 100, wheelDeltaY: -120, altKey: true }])).toEqual(["orbit"]);
  });
});

describe("orbitDelta", () => {
  test("3D: horizontal rotates, vertical tilts", () => {
    const [az, polar] = orbitDelta(100, 0, false);
    expect(az).not.toBe(0);
    expect(polar).toBe(0);
    const [az2, polar2] = orbitDelta(0, 100, false);
    expect(az2 === 0).toBe(true);
    expect(polar2).toBeGreaterThan(0);
  });
  test("2D: no tilt, both axes rotate", () => {
    expect(orbitDelta(0, 100, true)[1]).toBe(0);
    expect(orbitDelta(0, 100, true)[0]).not.toBe(0);
  });
});
