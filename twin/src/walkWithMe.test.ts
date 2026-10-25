import { describe, expect, it } from "vitest";
import fixture from "./motion/__fixtures__/route-dev-osm-way22744230.json";
import { RouteMatcher } from "./motion/routeMatcher";
import { legsFromRoute } from "./motion/legs";
import { buildPlan, stepFor } from "./walkWithMe";

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
