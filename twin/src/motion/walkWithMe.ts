import type { Route } from "../api/types";
import { HeadingSmoother, type HeadingReading } from "./heading";
import { legsFromRoute } from "./legs";
import { RouteMatcher, type ResetTarget, type RouteMatcherOptions } from "./routeMatcher";
import { listenToSensors, motionSupport } from "./sensors";
import { DEFAULT_STEP_LENGTH_M, StepDetector, stepLength, type StepDetectorOptions } from "./stepDetector";
import { gaussian, seededRandom, walkingSample } from "./synthetic";
import type { AccelSample, ConnectorInfo, LegEnd, MatchEvent, MotionLeg, MotionStatus, StepEvent, WalkPosition } from "./types";

/** "Walk with me": sensors -> step detector -> route matcher, with a tiny event emitter for the UI.
 * Every position it hands out is an estimate (`estimated: true`); the UI must say "about" / "estimated". */

export interface WalkWithMeOptions {
  /** base step length in metres before calibration (default 0.7) */
  stepLengthM: number;
  /** faster cadence -> a bit longer steps (clamped 0.5 to 0.9 m) */
  scaleByCadence: boolean;
  /** use the compass to notice a turnaround (only with an absolute heading) */
  headingCheck: boolean;
  /** report "unsupported" if no sensor sample arrives within this time after start (desktop browsers) */
  noDataTimeoutMs: number;
  matcher: Partial<RouteMatcherOptions>;
  detector: Partial<StepDetectorOptions>;
}

const DEFAULTS: WalkWithMeOptions = {
  stepLengthM: DEFAULT_STEP_LENGTH_M,
  scaleByCadence: true,
  headingCheck: true,
  noDataTimeoutMs: 3000,
  matcher: {},
  detector: {},
};

export interface WalkEvents {
  position: WalkPosition;
  step: StepEvent & { lengthM: number };
  legEnded: { legIndex: number; end: LegEnd; connector?: ConnectorInfo; position: WalkPosition };
  arrived: { position: WalkPosition };
  status: MotionStatus;
}

type Listener<K extends keyof WalkEvents> = (payload: WalkEvents[K]) => void;

export interface WalkWithMe {
  /** current sensor status (see MotionStatus) */
  status(): MotionStatus;
  /** Start following a route (legs, or the page's Route from /api/route). Listens to the sensors when allowed;
   * call requestMotionPermission() from the switch tap first on iOS. Subscribe before start: a route that
   * begins at a stair emits legEnded right away. Returns the sensor status. */
  start(route: MotionLeg[] | Pick<Route, "segments" | "floor_changes">): MotionStatus;
  /** stop listening and forget the route (End route, switch off) */
  stop(): void;
  /** through the stair/lift, or the person said "next" */
  next(): void;
  /** "I'm here" / drag / voice position; `calibrate` rescales the step length from the gap */
  resetTo(target: ResetTarget, options?: { calibrate?: boolean }): void;
  /** the person confirms they reached the end of the current leg (recalibrates) */
  confirmLegEnd(): void;
  position(): WalkPosition | null;
  calibrationFactor(): number;
  on<K extends keyof WalkEvents>(event: K, listener: Listener<K>): () => void;
  /** feed one accelerometer sample (recorded traces, tests) */
  feedSample(sample: AccelSample): void;
  feedHeading(reading: HeadingReading): void;
  /** Desktop demo: synthetic walking at `stepsPerSecond` through the real detector; 0 stops. Returns a stop fn. */
  simulate(stepsPerSecond: number): () => void;
}

export function createWalkWithMe(options: Partial<WalkWithMeOptions> = {}): WalkWithMe {
  const o: WalkWithMeOptions = { ...DEFAULTS, ...options };
  // one set per event name; the public on() keeps the payload types straight
  const listeners = new Map<keyof WalkEvents, Set<(payload: never) => void>>();
  let matcher: RouteMatcher | null = null;
  let detector = new StepDetector(o.detector);
  const heading = new HeadingSmoother(8);
  let headingAbsolute = false;
  let status: MotionStatus = motionSupport();
  let stopSensors: (() => void) | null = null;
  let noDataTimer: ReturnType<typeof setTimeout> | null = null;
  let gotSample = false;
  let stopSim: (() => void) | null = null;

  function emit<K extends keyof WalkEvents>(event: K, payload: WalkEvents[K]): void {
    for (const listener of listeners.get(event) ?? []) {
      try {
        (listener as Listener<K>)(payload);
      } catch (error) {
        console.error("walkWithMe listener failed", error);
      }
    }
  }

  function setStatus(next: MotionStatus): void {
    if (next === status) return;
    status = next;
    emit("status", status);
  }

  function publish(events: MatchEvent[]): void {
    if (!matcher) return;
    for (const event of events) {
      if (event.type === "legEnded") {
        emit("legEnded", { legIndex: event.legIndex, end: event.end, connector: event.connector, position: event.position });
      } else {
        emit("arrived", { position: event.position });
      }
    }
    emit("position", matcher.position());
  }

  function onStep(step: StepEvent): void {
    if (!matcher) return;
    const lengthM = stepLength(step.cadenceHz, o.stepLengthM, o.scaleByCadence);
    emit("step", { ...step, lengthM });
    const compass = o.headingCheck && headingAbsolute ? heading.value() : null;
    publish(matcher.step(lengthM, compass));
  }

  function feedSample(sample: AccelSample): void {
    gotSample = true;
    for (const step of detector.push(sample)) onStep(step);
  }

  function feedHeading(reading: HeadingReading): void {
    headingAbsolute = reading.absolute;
    heading.push(reading.deg);
  }

  function clearTimers(): void {
    if (noDataTimer) clearTimeout(noDataTimer);
    noDataTimer = null;
  }

  const walk: WalkWithMe = {
    status: () => status,
    start(route) {
      walk.stop();
      const legs = Array.isArray(route) ? route : legsFromRoute(route);
      matcher = new RouteMatcher(legs, o.matcher);
      detector = new StepDetector(o.detector);
      heading.reset();
      status = motionSupport();
      if (status === "ready") {
        gotSample = false;
        stopSensors = listenToSensors({ onAccel: feedSample, onHeading: feedHeading });
        setStatus("active");
        noDataTimer = setTimeout(() => {
          if (!gotSample && stopSensors) setStatus("unsupported"); // API present, but no sensor (desktop)
        }, o.noDataTimeoutMs);
      } else {
        emit("status", status);
      }
      publish(matcher.start());
      return status;
    },
    stop() {
      stopSim?.();
      stopSim = null;
      stopSensors?.();
      stopSensors = null;
      clearTimers();
      matcher = null;
      if (status === "active") setStatus(motionSupport());
    },
    next() {
      if (matcher) publish(matcher.next());
    },
    resetTo(target, resetOptions) {
      if (matcher) publish(matcher.resetTo(target, resetOptions?.calibrate === true));
    },
    confirmLegEnd() {
      if (matcher) publish(matcher.confirmLegEnd());
    },
    position: () => matcher?.position() ?? null,
    calibrationFactor: () => matcher?.calibrationFactor ?? 1,
    on(event, listener) {
      let set = listeners.get(event);
      if (!set) listeners.set(event, (set = new Set()));
      const stored = listener as (payload: never) => void;
      set.add(stored);
      return () => {
        set.delete(stored);
      };
    },
    feedSample,
    feedHeading,
    simulate(stepsPerSecond) {
      stopSim?.();
      stopSim = null;
      if (!(stepsPerSecond > 0) || typeof setInterval === "undefined") return () => {};
      const random = seededRandom(42);
      const periodMs = 20; // 50 Hz like a phone
      let t = 0;
      const timer = setInterval(() => {
        t += periodMs;
        const s = walkingSample(t, stepsPerSecond);
        feedSample({ t, x: s.x + 0.2 * gaussian(random), y: s.y + 0.2 * gaussian(random), z: s.z + 0.2 * gaussian(random) });
      }, periodMs);
      const stop = () => clearInterval(timer);
      stopSim = stop;
      return stop;
    },
  };
  installDevHook(walk);
  return walk;
}

declare global {
  interface Window {
    /** Dev only: synthetic steps into the latest Walk-with-me instance; __walkSim(0) stops. */
    __walkSim?: (stepsPerSecond: number) => void;
  }
}

function installDevHook(walk: WalkWithMe): void {
  if (!import.meta.env?.DEV || typeof window === "undefined") return;
  window.__walkSim = (stepsPerSecond: number) => {
    walk.simulate(stepsPerSecond);
  };
}
