/** Shared types of the "Walk with me" motion module. Positions are model metres (+y = north in the data). */

export type Point = [number, number];

/** What the sensors can do right now.
 * - unsupported: no motion sensor API, or no sensor data arrives (desktop browser)
 * - needs-https: the page is not a secure context, browsers hide the sensors (use scripts/tunnel.sh)
 * - needs-permission: iOS, call requestMotionPermission() from a tap
 * - denied: the person (or the browser) said no
 * - ready: allowed, not listening yet
 * - active: listening, steps are being counted */
export type MotionStatus = "unsupported" | "needs-https" | "needs-permission" | "denied" | "ready" | "active";

/** One accelerometer reading: time in ms, accelerationIncludingGravity in m/s^2. */
export interface AccelSample {
  t: number;
  x: number;
  y: number;
  z: number;
}

/** A detected step. */
export interface StepEvent {
  /** time of the peak in ms (same clock as the samples) */
  t: number;
  /** steps per second over the recent steps (0 if unknown yet) */
  cadenceHz: number;
}

/** How a leg ends.
 * - connector: stairs or lift; the matcher waits there until next() (or a reset)
 * - pass: nothing to wait for (e.g. walk -> outside on the same floor); the matcher walks on
 * - arrival: the destination */
export type LegEnd = "connector" | "pass" | "arrival";

export interface ConnectorInfo {
  id: string;
  kind: string;
  name: string;
  toFloor: string;
  direction?: "up" | "down";
}

/** One piece of the route on one floor. */
export interface MotionLeg {
  floorId: string;
  points: Point[];
  end: LegEnd;
  connector?: ConnectorInfo;
}

/** Every position the module exposes is an estimate. Never present it as a located position. */
export interface WalkPosition {
  estimated: true;
  point: Point;
  floorId: string;
  legIndex: number;
  legCount: number;
  /** metres along the current leg */
  alongLegM: number;
  legLengthM: number;
  /** metres along the whole route (sum of legs, connectors count 0) */
  alongRouteM: number;
  routeLengthM: number;
  distanceLeftM: number;
  legLeftM: number;
  /** waiting at a stair/lift at the end of the current leg (call next() once through it) */
  atConnector: boolean;
  arrived: boolean;
  /** the heading points away from the route for several steps; the matcher holds still */
  offRoute: boolean;
  steps: number;
}

export type MatchEvent =
  | { type: "legEnded"; legIndex: number; end: LegEnd; connector?: ConnectorInfo; position: WalkPosition }
  | { type: "arrived"; position: WalkPosition };
