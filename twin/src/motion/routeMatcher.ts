import { angleDiff, modelBearing, modelToCompass } from "./heading";
import { clamp } from "./stepDetector";
import type { ConnectorInfo, MatchEvent, MotionLeg, Point, WalkPosition } from "./types";

/** Snaps counted steps to a known route: the state is the distance along the route. Pure, no DOM.
 *
 * - Each step advances by its length times the calibration factor.
 * - It never walks past the end of a leg that ends at stairs or a lift: it waits there (`atConnector`) until
 *   next() or a reset. A `pass` leg end is crossed without waiting, `arrival` ends the walk.
 * - Optional heading check: if the heading differs from the route direction by more than `turnaroundDeg` for
 *   `turnaroundSteps` steps in a row, the steps stop advancing and `offRoute` is set.
 * - Everything it exposes is `estimated: true`. */

export interface RouteMatcherOptions {
  northOffsetDeg: number;
  turnaroundDeg: number;
  /** the n-th step in a row against the route direction (and every one after it) does not advance */
  turnaroundSteps: number;
  /** a correction only recalibrates after at least this many estimated metres */
  minCalibrationM: number;
  calibrationRange: [number, number];
}

export const DEFAULT_MATCHER_OPTIONS: RouteMatcherOptions = {
  northOffsetDeg: 0,
  turnaroundDeg: 100,
  turnaroundSteps: 3,
  minCalibrationM: 5,
  calibrationRange: [0.7, 1.3],
};

export type ResetTarget = { distanceAlong: number } | { point: Point; floorId?: string };

interface PreparedLeg extends MotionLeg {
  lengths: number[]; // cumulative, lengths[0] = 0
  length: number;
  offset: number; // distance along the route where this leg starts
}

const EPS = 1e-6;

export class RouteMatcher {
  private readonly o: RouteMatcherOptions;
  private readonly legs: PreparedLeg[];
  private readonly total: number;
  private legIndex = 0;
  private along = 0;
  private endedLeg = -1; // the leg whose end was already reported
  private atConnector = false;
  private arrived = false;
  private againstCount = 0;
  private offRoute = false;
  private stepCount = 0;
  private calibration = 1;
  private anchorRouteM = 0;
  private walkedSinceAnchor = 0; // estimated metres (after calibration) since the last anchor

  constructor(legs: MotionLeg[], options: Partial<RouteMatcherOptions> = {}) {
    this.o = { ...DEFAULT_MATCHER_OPTIONS, ...options };
    const usable = legs.filter((leg) => leg.points.length > 0);
    if (!usable.length) throw new Error("RouteMatcher needs at least one leg with a point");
    let offset = 0;
    this.legs = usable.map((leg, i) => {
      const lengths = [0];
      for (let k = 1; k < leg.points.length; k++) {
        const [ax, ay] = leg.points[k - 1];
        const [bx, by] = leg.points[k];
        lengths.push(lengths[k - 1] + Math.hypot(bx - ax, by - ay));
      }
      const length = lengths[lengths.length - 1];
      const prepared = { ...leg, end: i === usable.length - 1 ? "arrival" : leg.end, lengths, length, offset };
      offset += length;
      return prepared;
    });
    this.total = offset;
  }

  /** Report the state at the start: a first leg of length 0 that ends at stairs is already at its connector. */
  start(): MatchEvent[] {
    return this.settle();
  }

  get calibrationFactor(): number {
    return this.calibration;
  }

  set calibrationFactor(value: number) {
    this.calibration = clamp(value, ...this.o.calibrationRange);
  }

  /** One step of `lengthM` metres; `headingDeg` (compass, smoothed) is optional and only used for the turnaround check. */
  step(lengthM: number, headingDeg: number | null = null): MatchEvent[] {
    if (!Number.isFinite(lengthM) || lengthM <= 0) return [];
    this.stepCount++;
    if (this.arrived || this.atConnector) return []; // waiting at stairs/lift or done: steps do not move the dot
    const metres = lengthM * this.calibration;
    if (headingDeg !== null && Number.isFinite(headingDeg)) {
      const routeDeg = this.routeDirection();
      if (routeDeg !== null && angleDiff(headingDeg, routeDeg) > this.o.turnaroundDeg) {
        this.againstCount++;
        if (this.againstCount >= this.o.turnaroundSteps) {
          this.offRoute = true;
          return [];
        }
      } else {
        this.againstCount = 0;
        this.offRoute = false;
      }
    }
    this.walkedSinceAnchor += metres;
    this.along += metres;
    return this.settle();
  }

  /** The person is through the stairs/lift (or says "next"): jump to the start of the next leg. */
  next(): MatchEvent[] {
    if (this.arrived) return [];
    if (this.legIndex >= this.legs.length - 1) {
      this.along = this.leg.length;
      return this.settle();
    }
    this.moveTo(this.legIndex + 1, 0);
    this.anchor();
    return this.settle();
  }

  /** "I'm here", a drag of the dot or a spoken position. With `calibrate`, the gap between the estimate and the
   * correction since the last anchor rescales the step length (simple ratio, clamped). */
  resetTo(target: ResetTarget, calibrate = false): MatchEvent[] {
    const routeM = "distanceAlong" in target ? clamp(target.distanceAlong, 0, this.total) : this.project(target);
    if (calibrate) this.recalibrate(routeM);
    const { legIndex, along } = this.locate(routeM);
    this.moveTo(legIndex, along);
    this.arrived = false;
    this.anchor();
    return this.settle();
  }

  /** The person confirms she is at the end of the current leg (e.g. "I'm at the stairs"): recalibrates. */
  confirmLegEnd(): MatchEvent[] {
    return this.resetTo({ distanceAlong: this.leg.offset + this.leg.length }, true);
  }

  position(): WalkPosition {
    const leg = this.leg;
    const alongRouteM = leg.offset + this.along;
    return {
      estimated: true,
      point: this.pointAt(leg, this.along),
      floorId: leg.floorId,
      legIndex: this.legIndex,
      legCount: this.legs.length,
      alongLegM: this.along,
      legLengthM: leg.length,
      alongRouteM,
      routeLengthM: this.total,
      distanceLeftM: Math.max(0, this.total - alongRouteM),
      legLeftM: Math.max(0, leg.length - this.along),
      atConnector: this.atConnector,
      arrived: this.arrived,
      offRoute: this.offRoute,
      steps: this.stepCount,
    };
  }

  connectorAhead(): ConnectorInfo | undefined {
    return this.leg.end === "connector" ? this.leg.connector : undefined;
  }

  // ---------- internals ----------

  private get leg(): PreparedLeg {
    return this.legs[this.legIndex];
  }

  private moveTo(legIndex: number, along: number): void {
    if (legIndex !== this.legIndex || along < this.legs[legIndex].length - EPS) this.endedLeg = -1;
    this.legIndex = legIndex;
    this.along = along;
    this.atConnector = false;
    this.againstCount = 0;
    this.offRoute = false;
  }

  private anchor(): void {
    this.anchorRouteM = this.leg.offset + this.along;
    this.walkedSinceAnchor = 0;
  }

  private recalibrate(trueRouteM: number): void {
    if (this.walkedSinceAnchor < this.o.minCalibrationM) return;
    const trueDelta = trueRouteM - this.anchorRouteM;
    if (trueDelta <= 0) return;
    const ratio = clamp(trueDelta / this.walkedSinceAnchor, ...this.o.calibrationRange);
    this.calibrationFactor = this.calibration * ratio;
  }

  /** Handle leg ends after the position moved; may cross several `pass` ends at once. */
  private settle(): MatchEvent[] {
    const events: MatchEvent[] = [];
    for (;;) {
      const leg = this.leg;
      if (this.along < leg.length - EPS) break;
      const overflow = Math.max(0, this.along - leg.length);
      this.along = leg.length;
      if (leg.end === "arrival") {
        if (!this.arrived) {
          this.arrived = true;
          events.push({ type: "arrived", position: this.position() });
        }
        break;
      }
      if (leg.end === "connector") {
        this.atConnector = true;
        if (this.endedLeg !== this.legIndex) {
          this.endedLeg = this.legIndex;
          events.push({ type: "legEnded", legIndex: this.legIndex, end: "connector", connector: leg.connector, position: this.position() });
        }
        break;
      }
      // pass: report and walk on into the next leg
      if (this.endedLeg !== this.legIndex) {
        events.push({ type: "legEnded", legIndex: this.legIndex, end: "pass", position: this.position() });
      }
      this.legIndex++;
      this.along = overflow;
      this.endedLeg = -1;
    }
    return events;
  }

  private locate(routeM: number): { legIndex: number; along: number } {
    for (let i = 0; i < this.legs.length; i++) {
      const leg = this.legs[i];
      if (routeM <= leg.offset + leg.length + EPS || i === this.legs.length - 1) {
        // a point exactly at a leg end belongs to that leg (waits at its connector); skip zero-length pass legs
        return { legIndex: i, along: clamp(routeM - leg.offset, 0, leg.length) };
      }
    }
    return { legIndex: this.legs.length - 1, along: this.legs[this.legs.length - 1].length };
  }

  /** Distance along the route of the route point nearest to `point` (only legs on `floorId` if given). */
  private project(target: { point: Point; floorId?: string }): number {
    let best = Infinity;
    let bestM = this.leg.offset + this.along;
    for (const leg of this.legs) {
      if (target.floorId && leg.floorId !== target.floorId) continue;
      const pts = leg.points;
      if (pts.length === 1) {
        const d = Math.hypot(pts[0][0] - target.point[0], pts[0][1] - target.point[1]);
        if (d < best - EPS) [best, bestM] = [d, leg.offset];
        continue;
      }
      for (let k = 1; k < pts.length; k++) {
        const [ax, ay] = pts[k - 1];
        const [bx, by] = pts[k];
        const segLen = leg.lengths[k] - leg.lengths[k - 1];
        const t = segLen < EPS ? 0 : clamp(((target.point[0] - ax) * (bx - ax) + (target.point[1] - ay) * (by - ay)) / (segLen * segLen), 0, 1);
        const d = Math.hypot(ax + t * (bx - ax) - target.point[0], ay + t * (by - ay) - target.point[1]);
        if (d < best - EPS) [best, bestM] = [d, leg.offset + leg.lengths[k - 1] + t * segLen];
      }
    }
    return bestM;
  }

  private pointAt(leg: PreparedLeg, along: number): Point {
    const pts = leg.points;
    if (pts.length === 1 || along <= 0) return [pts[0][0], pts[0][1]];
    for (let k = 1; k < pts.length; k++) {
      if (along <= leg.lengths[k] + EPS || k === pts.length - 1) {
        const segLen = leg.lengths[k] - leg.lengths[k - 1];
        const t = segLen < EPS ? 1 : clamp((along - leg.lengths[k - 1]) / segLen, 0, 1);
        return [pts[k - 1][0] + t * (pts[k][0] - pts[k - 1][0]), pts[k - 1][1] + t * (pts[k][1] - pts[k - 1][1])];
      }
    }
    return [pts[pts.length - 1][0], pts[pts.length - 1][1]];
  }

  /** Compass bearing of the route about 2 m ahead of the current point, or null at a zero-length spot. */
  private routeDirection(): number | null {
    const leg = this.leg;
    const from = this.pointAt(leg, this.along);
    const ahead = Math.min(leg.length, this.along + 2);
    const bearing = ahead - this.along > 0.05 ? modelBearing(from, this.pointAt(leg, ahead)) : null;
    return bearing === null ? null : modelToCompass(bearing, this.o.northOffsetDeg);
  }
}
