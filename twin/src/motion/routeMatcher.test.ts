import { describe, expect, it } from "vitest";
import { RouteMatcher } from "./routeMatcher";
import type { MotionLeg } from "./types";

// Two legs: 10 m east on F0, stairs, then 6 m north on F1.
const legs: MotionLeg[] = [
  {
    floorId: "F0",
    points: [
      [0, 0],
      [10, 0],
    ],
    end: "connector",
    connector: { id: "V1", kind: "stairs", name: "Stairs 1", toFloor: "F1", direction: "up" },
  },
  {
    floorId: "F1",
    points: [
      [10, 1],
      [10, 7],
    ],
    end: "arrival",
  },
];

const walk = (m: RouteMatcher, n: number, len = 1, heading: number | null = null) =>
  Array.from({ length: n }, () => m.step(len, heading)).flat();

describe("route matcher", () => {
  it("advances along the leg by step length, every position is estimated", () => {
    const m = new RouteMatcher(legs);
    expect(m.start()).toEqual([]);
    walk(m, 4, 0.75);
    const p = m.position();
    expect(p.estimated).toBe(true);
    expect(p.point[0]).toBeCloseTo(3);
    expect(p.point[1]).toBeCloseTo(0);
    expect(p.distanceLeftM).toBeCloseTo(13);
    expect(p.steps).toBe(4);
  });

  it("stops at the stairs, reports legEnded once and waits for next()", () => {
    const m = new RouteMatcher(legs);
    const events = walk(m, 14);
    expect(events.filter((e) => e.type === "legEnded")).toHaveLength(1);
    const ended = events.find((e) => e.type === "legEnded");
    expect(ended?.type === "legEnded" && ended.connector?.name).toBe("Stairs 1");
    const p = m.position();
    expect(p.atConnector).toBe(true);
    expect(p.point).toEqual([10, 0]);
    expect(p.legIndex).toBe(0);
    m.next();
    expect(m.position().legIndex).toBe(1);
    expect(m.position().point).toEqual([10, 1]);
    expect(m.position().atConnector).toBe(false);
  });

  it("arrives at the end and stops moving", () => {
    const m = new RouteMatcher(legs);
    walk(m, 10);
    m.next();
    const events = walk(m, 8);
    expect(events.filter((e) => e.type === "arrived")).toHaveLength(1);
    expect(m.position().arrived).toBe(true);
    expect(m.position().point).toEqual([10, 7]);
    expect(m.position().distanceLeftM).toBe(0);
  });

  it("crosses a pass boundary without waiting", () => {
    const m = new RouteMatcher([
      { floorId: "F0", points: [[0, 0], [3, 0]], end: "pass" },
      { floorId: "F0", points: [[3, 0], [3, 4]], end: "arrival" },
    ]);
    const events = walk(m, 5);
    expect(events.map((e) => e.type)).toEqual(["legEnded"]);
    expect(m.position().legIndex).toBe(1);
    expect(m.position().point[1]).toBeCloseTo(2);
  });

  it("starts at the connector when the route begins in a stairwell (zero-length first leg)", () => {
    const m = new RouteMatcher([{ ...legs[0], points: [[0, 0]] }, legs[1]]);
    const events = m.start();
    expect(events.map((e) => e.type)).toEqual(["legEnded"]);
    expect(m.position().atConnector).toBe(true);
  });

  it("resets to a distance or a point on the route", () => {
    const m = new RouteMatcher(legs);
    m.resetTo({ distanceAlong: 12 });
    expect(m.position().legIndex).toBe(1);
    expect(m.position().point[1]).toBeCloseTo(3);
    m.resetTo({ point: [4.2, 3] });
    expect(m.position().legIndex).toBe(0);
    expect(m.position().point[0]).toBeCloseTo(4.2);
    m.resetTo({ point: [4.2, 3], floorId: "F1" });
    expect(m.position().legIndex).toBe(1);
    expect(m.position().point[1]).toBeCloseTo(3);
  });

  it("a reset back from the arrival walks again", () => {
    const m = new RouteMatcher(legs);
    m.resetTo({ distanceAlong: 16 });
    expect(m.position().arrived).toBe(true);
    m.resetTo({ distanceAlong: 11 });
    expect(m.position().arrived).toBe(false);
    walk(m, 1);
    expect(m.position().alongRouteM).toBeCloseTo(12);
  });

  it("holds still after the person turned around, and goes on when the heading agrees again", () => {
    const m = new RouteMatcher(legs); // first leg runs east = 90 deg
    walk(m, 2, 1, 90);
    walk(m, 5, 1, 270);
    const p = m.position();
    expect(p.offRoute).toBe(true);
    // the first two steps against the route still counted (benefit of the doubt), the rest did not
    expect(p.alongRouteM).toBeCloseTo(4);
    walk(m, 1, 1, 80);
    expect(m.position().offRoute).toBe(false);
    expect(m.position().alongRouteM).toBeCloseTo(5);
  });

  it("uses northOffsetDeg for rotated buildings", () => {
    const m = new RouteMatcher(legs, { northOffsetDeg: 90 }); // +y points east, so model east is compass south
    walk(m, 5, 1, 180);
    expect(m.position().offRoute).toBe(false);
    expect(m.position().alongRouteM).toBeCloseTo(5);
  });

  it("ignores heading when none is given", () => {
    const m = new RouteMatcher(legs);
    walk(m, 3, 1, null);
    expect(m.position().alongRouteM).toBeCloseTo(3);
  });

  it("recalibrates the step length when the person confirms the stairs earlier, clamped", () => {
    const m = new RouteMatcher(legs);
    walk(m, 8); // estimate 8 m, the stairs are at 10 m
    m.confirmLegEnd();
    expect(m.calibrationFactor).toBeCloseTo(1.25);
    expect(m.position().atConnector).toBe(true);
    m.next();
    walk(m, 4);
    expect(m.position().alongLegM).toBeCloseTo(5);
  });

  it("recalibrates down when the person arrives later than the estimate, never below 0.7", () => {
    const m = new RouteMatcher([{ floorId: "F0", points: [[0, 0], [40, 0]], end: "arrival" }]);
    walk(m, 20); // 20 m estimated
    m.resetTo({ distanceAlong: 10 }, true); // really only 10 m
    expect(m.calibrationFactor).toBeCloseTo(0.7);
  });

  it("does not recalibrate on a short distance", () => {
    const m = new RouteMatcher(legs);
    walk(m, 2);
    m.resetTo({ distanceAlong: 4 }, true);
    expect(m.calibrationFactor).toBe(1);
  });

  it("ignores bad step lengths and needs a leg with points", () => {
    const m = new RouteMatcher(legs);
    expect(m.step(Number.NaN)).toEqual([]);
    expect(m.step(-1)).toEqual([]);
    expect(m.position().steps).toBe(0);
    expect(() => new RouteMatcher([])).toThrow();
  });
});
