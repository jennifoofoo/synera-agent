import { describe, expect, it } from "vitest";
import { angleDiff, circularMean, HeadingSmoother, headingFromOrientation, modelBearing, modelToCompass } from "./heading";

describe("heading", () => {
  it("prefers the iOS compass and marks it absolute", () => {
    expect(headingFromOrientation({ alpha: 10, webkitCompassHeading: 45 })).toEqual({ deg: 45, absolute: true });
  });

  it("turns W3C alpha (counter-clockwise) into a clockwise heading", () => {
    expect(headingFromOrientation({ alpha: 90, absolute: true })).toEqual({ deg: 270, absolute: true });
    expect(headingFromOrientation({ alpha: 90 })?.absolute).toBe(false);
    expect(headingFromOrientation({ alpha: null })).toBeNull();
  });

  it("adds the screen angle for a phone held sideways", () => {
    expect(headingFromOrientation({ alpha: null, webkitCompassHeading: 350, screenAngle: 90 })?.deg).toBe(80);
  });

  it("averages across north without breaking", () => {
    expect(circularMean([350, 10])).toBeCloseTo(0);
    const s = new HeadingSmoother(4);
    [355, 5, 359, 1].forEach((d) => s.push(d));
    const v = s.value() ?? -1;
    expect(Math.min(v, 360 - v)).toBeLessThan(1);
    expect(circularMean([])).toBeNull();
  });

  it("model bearing (0 = +y) and compass offset", () => {
    expect(modelBearing([0, 0], [0, 5])).toBeCloseTo(0);
    expect(modelBearing([0, 0], [5, 0])).toBeCloseTo(90);
    expect(modelBearing([0, 0], [0, 0])).toBeNull();
    expect(modelToCompass(270, 120)).toBeCloseTo(30);
    expect(angleDiff(350, 10)).toBeCloseTo(20);
    expect(angleDiff(0, 180)).toBeCloseTo(180);
  });
});
