// The route as the follow-cam walks it (Guide me): the legs per floor stretch with their metres along the route, and
// the plan of which walk step covers which metres (buildPlan from walkWithMe.ts, the same split "Walk with me" uses).
// Pure geometry, no store writes. Used by FollowCam.tsx (the dot and the camera) and FollowRoute.tsx (badge).

import type { Route } from "../api/types";
import { legsFromRoute } from "../motion";
import { walkSteps } from "../store";
import { readable } from "../walkInfo";
import { buildPlan } from "../walkWithMe";

export interface FollowLeg {
  floorId: string;
  /** model metres, +y = north */
  xs: number[];
  ys: number[];
  /** cumulative metres along this leg at each point */
  cum: number[];
  /** metres along the route where this leg starts (connectors count 0, like the motion module) */
  startM: number;
  lengthM: number;
  group: number;
}

export interface FollowPath {
  legs: FollowLeg[];
  plan: ReturnType<typeof buildPlan>;
  lengthM: number;
}

/** A point on the path, written into a reused object (no allocation per frame). */
export interface PathPoint {
  x: number;
  y: number;
  floorId: string;
  leg: number;
  alongLeg: number;
}

export function newPathPoint(): PathPoint {
  return { x: 0, y: 0, floorId: "", leg: 0, alongLeg: 0 };
}

export function buildFollowPath(route: Route): FollowPath | null {
  if (!route.ok || !route.segments?.length) return null;
  const plan = buildPlan(walkSteps().map(readable), route);
  const legs: FollowLeg[] = [];
  let offset = 0;
  legsFromRoute(route)
    .filter((leg) => leg.points.length > 0)
    .forEach((leg, index) => {
      const xs = leg.points.map((p) => p[0]);
      const ys = leg.points.map((p) => p[1]);
      const cum = [0];
      for (let i = 1; i < xs.length; i++) cum.push(cum[i - 1] + Math.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1]));
      const lengthM = cum[cum.length - 1];
      legs.push({ floorId: leg.floorId, xs, ys, cum, startM: offset, lengthM, group: plan.legGroup[index] ?? 0 });
      offset += lengthM;
    });
  return legs.length ? { legs, plan, lengthM: offset } : null;
}

/** The point `alongLeg` metres into leg `leg` (clamped to the leg). */
export function pointOnLeg(path: FollowPath, leg: number, alongLeg: number, out: PathPoint): PathPoint {
  const l = path.legs[leg];
  const s = Math.max(0, Math.min(l.lengthM, alongLeg));
  let i = 1;
  while (i < l.cum.length - 1 && l.cum[i] < s) i++;
  if (l.xs.length === 1) {
    out.x = l.xs[0];
    out.y = l.ys[0];
  } else {
    const t = (s - l.cum[i - 1]) / Math.max(1e-6, l.cum[i] - l.cum[i - 1]);
    out.x = l.xs[i - 1] + (l.xs[i] - l.xs[i - 1]) * t;
    out.y = l.ys[i - 1] + (l.ys[i] - l.ys[i - 1]) * t;
  }
  out.floorId = l.floorId;
  out.leg = leg;
  out.alongLeg = s;
  return out;
}

/** The point `alongM` metres along the route, inside the stretch `group` (between two stairs/lifts): at a floor
 * change the same metre exists on both floors, the group says which one. */
export function pointOnPath(path: FollowPath, alongM: number, group: number, out: PathPoint): PathPoint {
  let first = -1;
  let last = -1;
  for (let i = 0; i < path.legs.length; i++) {
    if (path.legs[i].group !== group) continue;
    if (first < 0) first = i;
    last = i;
  }
  if (first < 0) {
    first = 0;
    last = path.legs.length - 1;
  }
  let leg = last;
  for (let i = first; i <= last; i++) {
    const l = path.legs[i];
    if (alongM <= l.startM + l.lengthM + 1e-6) {
      leg = i;
      break;
    }
  }
  return pointOnLeg(path, leg, alongM - path.legs[leg].startM, out);
}

const ahead = newPathPoint();
const behind = newPathPoint();

/** Camera azimuth (camera-controls theta) that puts the camera behind a walker at `p` looking `lookM` metres ahead
 * along the leg. Null when the leg is too short to tell a direction. */
export function behindAzimuth(path: FollowPath, p: PathPoint, lookM: number): number | null {
  const l = path.legs[p.leg];
  if (!l || l.lengthM < 0.2) return null;
  pointOnLeg(path, p.leg, p.alongLeg + lookM, ahead);
  pointOnLeg(path, p.leg, p.alongLeg, behind);
  let dx = ahead.x - behind.x;
  let dy = ahead.y - behind.y;
  if (Math.hypot(dx, dy) < 0.3) {
    // at the end of the leg: the direction of the last stretch into it
    pointOnLeg(path, p.leg, p.alongLeg - lookM, behind);
    dx = p.x - behind.x;
    dy = p.y - behind.y;
    if (Math.hypot(dx, dy) < 0.05) return null;
  }
  // World: x = model x, z = -model y. camera-controls puts the camera at target + r(sin θ, ·, cos θ); behind the
  // walking direction (dx, -dy) means (sin θ, cos θ) = -(dx, -dy) / |.|.
  return Math.atan2(-dx, dy);
}

/** Shortest signed angle from a to b. */
export function angleTo(a: number, b: number): number {
  let d = (b - a) % (2 * Math.PI);
  if (d > Math.PI) d -= 2 * Math.PI;
  if (d < -Math.PI) d += 2 * Math.PI;
  return d;
}
