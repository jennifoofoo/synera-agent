import { describe, expect, it } from "vitest";
import fixture from "./__fixtures__/route-dev-osm-way22744230.json";
import { legsFromRoute } from "./legs";
import { requestMotionPermission, motionSupport } from "./sensors";
import { walkingTrace } from "./synthetic";
import type { MotionLeg, Point, WalkPosition } from "./types";
import { createWalkWithMe, type WalkEvents } from "./walkWithMe";

/** End to end without a phone: a real route from POST /api/route on a dev building (fixture), synthetic walking
 * samples through the real step detector into the matcher. Set MOTION_API (e.g. http://127.0.0.1:8765) to also
 * fetch the route live from a running `uv run python -m web`. */

type ApiRoute = Parameters<typeof legsFromRoute>[0];
const route = fixture as unknown as ApiRoute & { start: string; destination: string };

function distanceToPolyline(p: Point, points: Point[]): number {
  if (points.length === 1) return Math.hypot(p[0] - points[0][0], p[1] - points[0][1]);
  let best = Infinity;
  for (let i = 1; i < points.length; i++) {
    const [a, b] = [points[i - 1], points[i]];
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const len2 = dx * dx + dy * dy;
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2));
    best = Math.min(best, Math.hypot(a[0] + t * dx - p[0], a[1] + t * dy - p[1]));
  }
  return best;
}

function driveAlong(apiRoute: ApiRoute) {
  const legs: MotionLeg[] = legsFromRoute(apiRoute);
  const walk = createWalkWithMe({ scaleByCadence: false });
  const positions: WalkPosition[] = [];
  const ended: WalkEvents["legEnded"][] = [];
  let arrived = 0;
  walk.on("position", (p) => positions.push(p));
  walk.on("legEnded", (e) => {
    ended.push(e);
    walk.next(); // what the UI does after guidance spoke the next step (here: right away)
  });
  walk.on("arrived", () => arrived++);
  walk.start(apiRoute);
  // 2 steps per second for 90 s is about 126 m, more than the route
  let t = 0;
  for (let chunk = 0; chunk < 90 && !arrived; chunk++) {
    for (const sample of walkingTrace(2, { durationS: 1, startMs: t, seed: chunk + 1 })) walk.feedSample(sample);
    t += 1000;
  }
  return { legs, positions, ended, arrived, walk };
}

function check(apiRoute: ApiRoute) {
  const { legs, positions, ended, arrived } = driveAlong(apiRoute);
  expect(legs.length).toBeGreaterThan(1);
  expect(arrived).toBe(1);
  expect(ended.filter((e) => e.end === "connector").length).toBe(legs.filter((l) => l.end === "connector").length);
  let lastAlong = -1;
  for (const p of positions) {
    expect(p.estimated).toBe(true);
    // the dot always sits on the polyline of its leg and floor
    expect(distanceToPolyline(p.point, legs[p.legIndex].points)).toBeLessThan(1e-6);
    expect(p.floorId).toBe(legs[p.legIndex].floorId);
    expect(p.alongRouteM).toBeGreaterThanOrEqual(lastAlong - 1e-9);
    lastAlong = p.alongRouteM;
  }
  const last = positions[positions.length - 1];
  const end = legs[legs.length - 1].points.at(-1) as Point;
  expect(last.point[0]).toBeCloseTo(end[0]);
  expect(last.point[1]).toBeCloseTo(end[1]);
  // it moved through many distinct points, not just jumped
  expect(new Set(positions.map((p) => p.point.join(","))).size).toBeGreaterThan(50);
}

describe("real route from /api/route (dev building fixture)", () => {
  it("builds legs that end at the two stairs and the destination", () => {
    const legs = legsFromRoute(route);
    expect(legs.map((l) => l.end)).toEqual(["connector", "connector", "arrival"]);
    expect(legs[0].connector?.kind).toBe("stairs");
    expect(legs[1].connector?.toFloor).toBe("osm-way22744230-F2");
  });

  it("moves the dot along the polyline, waits at each stair, arrives", () => {
    check(route);
  });

  it("without next() it waits at the first stairs however long the person walks", () => {
    const walk = createWalkWithMe();
    walk.start(route); // first leg has length 0: the route starts in a stairwell
    for (const sample of walkingTrace(2, { durationS: 20 })) walk.feedSample(sample);
    expect(walk.position()?.atConnector).toBe(true);
    expect(walk.position()?.legIndex).toBe(0);
    walk.stop();
    expect(walk.position()).toBeNull();
  });

  const apiBase = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.MOTION_API;
  it.skipIf(!apiBase)("live: same check against a running API", async () => {
    const response = await fetch(`${apiBase}/api/route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ building: "dev/osm-way22744230", start: route.start, destination: route.destination }),
    });
    const body = (await response.json()) as { route: ApiRoute & { ok: boolean } };
    expect(body.route.ok).toBe(true);
    check(body.route);
  });
});

describe("sensors without a browser", () => {
  it("report unsupported and never throw", async () => {
    expect(motionSupport()).toBe("unsupported");
    await expect(requestMotionPermission()).resolves.toBe("unsupported");
    const walk = createWalkWithMe();
    expect(walk.start(route)).toBe("unsupported");
  });
});
