import { describe, expect, it } from "vitest";
import fixture from "./motion/__fixtures__/route-dev-osm-way22744230.json";
import { RouteMatcher } from "./motion/routeMatcher";
import { legsFromRoute } from "./motion/legs";
import { buildPlan, stepFor, stepStart } from "./walkWithMe";

type ApiRoute = Parameters<typeof legsFromRoute>[0];
const route = fixture as unknown as ApiRoute;

// The step lines POST /api/route returns for the fixture route (dev/osm-way22744230, stairwell to toilet).
const LINES = [
  "Start in Stairwell N0317D on Ground floor.",
  "Use Stairs 2 (stairs) to Basement 1.",
  "Walk about 3 m through the door into Corridor -1355B.",
  "Walk about 15 m through the door into Corridor -1355.",
  "Walk about 7 m through the door into Corridor -1354.",
  "Walk about 13 m through the door into Corridor -1351.",
  "Walk about 21 m through the door into Stairwell -1311A.",
  "Use Stairs 1 (stairs) to Floor 2.",
  "Walk about 0 m through the opening into Corridor N2333.",
  "Walk about 6 m through the door into Corridor N2332.",
  "Walk about 2 m through the door into Toilet N2320A.",
  "Walk about 1 m. You have arrived at Toilet N2320A on Floor 2.",
];

describe("walk with me: steps follow the estimate", () => {
  const plan = buildPlan(LINES, route);
  const matcher = () => new RouteMatcher(legsFromRoute(route));

  it("maps the rides to the stairs and spreads the walk steps over each floor", () => {
    expect(plan.steps.map((step) => step.kind)).toEqual(["start", "ride", "walk", "walk", "walk", "walk", "walk", "ride", "walk", "walk", "walk", "walk"]);
    expect(plan.rideStep).toEqual([1, 7]);
    const basement = plan.steps.slice(2, 7);
    for (let i = 1; i < basement.length; i++) expect(basement[i].startM).toBeCloseTo(basement[i - 1].endM, 6);
    expect(plan.steps[7].startM).toBeCloseTo(basement[4].endM, 6); // the ride sits where the basement walk ends
  });

  it("waits on the ride step at the first stairs, walks through the steps, arrives on the last", () => {
    const m = matcher();
    m.start();
    expect(stepFor(plan, m.position())).toBe(1); // starts in a stairwell: "Use Stairs 2" right away
    m.next();
    expect(stepFor(plan, m.position())).toBe(2);
    const seen = new Set<number>();
    for (let i = 0; i < 200 && !m.position().atConnector; i++) {
      m.step(0.7);
      seen.add(stepFor(plan, m.position())!);
    }
    expect([...seen].sort((a, b) => a - b)).toEqual([2, 3, 4, 5, 6, 7]); // every walk step, then the ride
    m.next();
    for (let i = 0; i < 100 && !m.position().arrived; i++) m.step(0.7);
    expect(m.position().arrived).toBe(true);
    expect(stepFor(plan, m.position())).toBe(LINES.length - 1);
  });

  it("never runs backwards on its own: steps only grow while walking", () => {
    const m = matcher();
    m.start();
    m.next();
    let last = 0;
    for (let i = 0; i < 60; i++) {
      m.step(0.7);
      const step = stepFor(plan, m.position())!;
      expect(step).toBeGreaterThanOrEqual(last);
      last = step;
    }
  });
});

describe("step guide without motion: Next puts the dot at the end of the step just done", () => {
  const legs = legsFromRoute(route);
  const [ground, basement, top] = legs;
  const distToLine = (p: [number, number], pts: [number, number][]) => {
    if (pts.length === 1) return Math.hypot(p[0] - pts[0][0], p[1] - pts[0][1]);
    let best = Infinity;
    for (let i = 1; i < pts.length; i++) {
      const [a, b] = [pts[i - 1], pts[i]];
      const dx = b[0] - a[0];
      const dy = b[1] - a[1];
      const l2 = dx * dx + dy * dy;
      const t = l2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) : 0;
      best = Math.min(best, Math.hypot(a[0] + t * dx - p[0], a[1] + t * dy - p[1]));
    }
    return best;
  };
  const at = (step: number) => stepStart(LINES, route, step)!;

  it("starts at the route start and ends at the destination", () => {
    expect(at(0)).toEqual({ point: ground.points[0], floorId: ground.floorId });
    expect(at(LINES.length - 1)).toEqual({ point: top.points[top.points.length - 1], floorId: top.floorId });
  });

  it("a ride step waits at the stairs on the floor it leaves, the step after it starts on the new floor", () => {
    expect(at(1).floorId).toBe(ground.floorId);
    expect(at(2)).toEqual({ point: basement.points[0], floorId: basement.floorId });
    expect(at(7)).toEqual({ point: basement.points[basement.points.length - 1], floorId: basement.floorId });
    expect(at(8)).toEqual({ point: top.points[0], floorId: top.floorId });
  });

  it("every step start lies on the route line, moving forward step by step, on the plan's metres", () => {
    const plan = buildPlan(LINES, route);
    let previous: [number, number] | null = null;
    for (let step = 2; step <= 6; step++) {
      const p = at(step);
      expect(p.floorId).toBe(basement.floorId);
      expect(distToLine(p.point, basement.points)).toBeLessThan(1e-6);
      if (step > 2) {
        const m = new RouteMatcher(legs);
        m.resetTo({ distanceAlong: plan.steps[step].startM }); // same metres as Walk with me
        expect(m.position().point[0]).toBeCloseTo(p.point[0], 6);
        expect(m.position().point[1]).toBeCloseTo(p.point[1], 6);
      }
      if (previous) expect(Math.hypot(p.point[0] - previous[0], p.point[1] - previous[1])).toBeGreaterThan(1);
      previous = p.point;
    }
  });

  it("Walk with me reset to the step start shows the same point, also across a floor change", () => {
    for (const step of [2, 4, 8, 10]) {
      const p = at(step);
      const m = new RouteMatcher(legs);
      m.resetTo({ point: p.point, floorId: p.floorId });
      expect(m.position().floorId).toBe(p.floorId);
      expect(m.position().point[0]).toBeCloseTo(p.point[0], 6);
      expect(m.position().point[1]).toBeCloseTo(p.point[1], 6);
    }
  });

  it("clamps the step and needs a route line", () => {
    expect(stepStart(LINES, route, 99)).toEqual(at(LINES.length - 1));
    expect(stepStart(LINES, { segments: [], floor_changes: [] }, 1)).toBeNull();
  });
});
