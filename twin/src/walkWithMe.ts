// "Walk with me" wired into the step guide (ui/Walk.tsx). The motion module (motion/) counts steps and snaps them
// to the route; this file connects it to the store: the switch, the estimated dot, step advance, corrections, stop.
//
// Honesty (docs/specs/auto-pace.md): the module's position is an estimate. It lives only in useWalkMotion, is drawn
// as "estimated" with an uncertainty ring, and is never written to state.position or sent to the server as `here`.

import { create } from "zustand";
import type { BuildingState, Point, Route } from "./api/types";
import { createWalkWithMe, legsFromRoute, motionSupport, requestMotionPermission, type MotionStatus, type WalkPosition, type WalkWithMe } from "./motion";
import { useTwin, walkSteps } from "./store";
import { speak } from "./voice";
import { metresIn, readable } from "./walkInfo";

const PREF_KEY = "twin.walkWithMe";
export const ABOUT_THERE = "You should be about there.";

interface WalkMotionState {
  /** the switch (remembered per viewer) */
  on: boolean;
  /** a short plain status after a tap ("on", "needs https", ...); cleared after a few seconds */
  notice: string | null;
  /** the module's estimate while it runs; never a position fact */
  estimate: WalkPosition | null;
  /** radius of the soft ring around the estimate, metres */
  uncertaintyM: number;
  /** the estimate reached the destination: "You should be about there." */
  arrived: boolean;
  /** the viewer has answered Walk with me once (switch or the hint), so the hint in the guide does not ask again */
  answered: boolean;
}

function loadPref(): boolean {
  try {
    return localStorage.getItem(PREF_KEY) === "1";
  } catch {
    return false;
  }
}

function loadAnswered(): boolean {
  try {
    return localStorage.getItem(PREF_KEY) !== null;
  } catch {
    return false;
  }
}

function savePref(on: boolean): void {
  useWalkMotion.setState({ answered: true });
  try {
    localStorage.setItem(PREF_KEY, on ? "1" : "0");
  } catch {
    /* private mode: not remembered */
  }
}

export const useWalkMotion = create<WalkMotionState>(() => ({ on: loadPref(), notice: null, estimate: null, uncertaintyM: 0, arrived: false, answered: loadAnswered() }));

const STATUS_TEXT: Partial<Record<MotionStatus, string>> = {
  "needs-https": "needs https",
  denied: "motion permission denied",
  unsupported: "not supported here",
  "needs-permission": "motion permission denied",
};

let noticeTimer: ReturnType<typeof setTimeout> | null = null;
function showNotice(text: string): void {
  if (noticeTimer) clearTimeout(noticeTimer);
  useWalkMotion.setState({ notice: text });
  noticeTimer = setTimeout(() => useWalkMotion.setState({ notice: null }), 4000);
}

/** The switch tap. requestMotionPermission() is the first thing called, inside the gesture (iOS). */
export async function toggleWalkWithMe(): Promise<void> {
  if (useWalkMotion.getState().on) {
    useWalkMotion.setState({ on: false });
    savePref(false);
    showNotice("off");
    return;
  }
  const status = await requestMotionPermission();
  const failed = STATUS_TEXT[status];
  if (failed) {
    showNotice(failed);
    return;
  }
  useWalkMotion.setState({ on: true });
  savePref(true);
  showNotice("on");
}

/** A phone whose motion sensors can work here (touch screen, sensors present, https). Laptops never qualify. */
export function walkWithMeAvailable(): boolean {
  if (typeof window === "undefined" || !window.matchMedia?.("(pointer: coarse)").matches) return false;
  const status = motionSupport();
  return status !== "unsupported" && status !== "needs-https";
}

/** The hint's "Turn on": the same switch tap (permission inside the gesture). A refused permission counts as an
 * answer too, so the hint does not ask again; the switch stays available. */
export async function acceptWalkWithMeHint(): Promise<void> {
  await toggleWalkWithMe();
  if (!useWalkMotion.getState().on) savePref(false);
}

/** The hint's "Not now": remembered like switching it off. */
export function declineWalkWithMeHint(): void {
  savePref(false);
}

/** While true, Walk with me moves the guide. A time-based auto-pace timer must not run then (one driver only). */
export function walkWithMeDriving(): boolean {
  return (useWalkMotion.getState().on || simForced) && running !== null;
}

/** Step lines as people should hear them while the estimate drives: no "you have arrived" from a guess. */
export function honestLine(line: string): string {
  if (!walkWithMeDriving()) return line;
  return line.replace(/\bYou have arrived at (.+?)\.?$/i, "$1 should be about here.").replace(/^\s*\.\s*/, "");
}

// ---------- the plan: which step covers which metres of the route ----------

interface PlanStep {
  kind: "start" | "walk" | "ride";
  group: number; // stretch between two stairs/lifts
  startM: number; // metres along the route (walking only, like the module)
  endM: number;
}

interface Plan {
  steps: PlanStep[];
  /** group of each motion leg */
  legGroup: number[];
  /** step index of the ride that ends each group */
  rideStep: (number | undefined)[];
}

const isRide = (line: string) => /^(Take|Use) .+ to /.test(line);

function legLength(points: [number, number][]): number {
  let sum = 0;
  for (let i = 1; i < points.length; i++) sum += Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
  return sum;
}

export function buildPlan(lines: string[], route: Pick<Route, "segments" | "floor_changes">): Plan {
  const legs = legsFromRoute(route).filter((leg) => leg.points.length > 0);
  const legGroup: number[] = [];
  const groupRange: [number, number][] = [];
  let offset = 0;
  let group = 0;
  legs.forEach((leg, index) => {
    const length = legLength(leg.points);
    if (!groupRange[group]) groupRange[group] = [offset, offset];
    legGroup.push(group);
    offset += length;
    groupRange[group][1] = offset;
    if (leg.end === "connector" && index < legs.length - 1) group++;
  });
  const lastGroup = Math.max(0, groupRange.length - 1);
  const steps: PlanStep[] = [];
  const rideStep: (number | undefined)[] = [];
  let g = 0;
  lines.forEach((line, index) => {
    if (index === 0 && /^Start/i.test(line)) steps.push({ kind: "start", group: 0, startM: 0, endM: 0 });
    else if (isRide(line)) {
      const end = groupRange[Math.min(g, lastGroup)]?.[1] ?? 0;
      steps.push({ kind: "ride", group: Math.min(g, lastGroup), startM: end, endM: end });
      if (rideStep[g] === undefined) rideStep[g] = index;
      g++;
    } else steps.push({ kind: "walk", group: Math.min(g, lastGroup), startM: 0, endM: 0 });
  });
  // Spread each group's walking metres over its walk steps, in proportion to the metres the lines name.
  for (let k = 0; k <= lastGroup; k++) {
    const [from, to] = groupRange[k] ?? [0, 0];
    const walks = steps.map((step, index) => ({ step, index })).filter(({ step }) => step.kind === "walk" && step.group === k);
    const named = walks.map(({ index }) => metresIn(lines[index]));
    const total = named.reduce((a, b) => a + b, 0);
    let at = from;
    walks.forEach(({ step }, i) => {
      const share = total > 0 ? named[i] / total : 1 / walks.length;
      step.startM = at;
      at = i === walks.length - 1 ? to : at + share * (to - from);
      step.endM = at;
    });
  }
  return { steps, legGroup, rideStep };
}

// ---------- where the person is once a step is done (Next/Back without motion) ----------

export interface StepPoint {
  point: [number, number];
  floorId: string;
}

function pointAlong(points: [number, number][], metres: number): [number, number] {
  let left = Math.max(0, metres);
  for (let i = 1; i < points.length; i++) {
    const [ax, ay] = points[i - 1];
    const [bx, by] = points[i];
    const length = Math.hypot(bx - ax, by - ay);
    if (left <= length && length > 0) return [ax + ((bx - ax) * left) / length, ay + ((by - ay) * left) / length];
    left -= length;
  }
  const last = points[points.length - 1];
  return [last[0], last[1]];
}

/** The route point at the start of step `step` (= the end of the step before it), on the same metres the plan uses
 * for Walk with me: a ride step sits at the stairs/lift on the floor it leaves, the step after it at the start of
 * the next floor's leg, the last step at the destination. Null without a route line. */
export function stepStart(lines: string[], route: Pick<Route, "segments" | "floor_changes">, step: number): StepPoint | null {
  const legs = legsFromRoute(route).filter((leg) => leg.points.length > 0);
  if (!legs.length || !lines.length) return null;
  const plan = buildPlan(lines, route);
  const index = Math.max(0, Math.min(step, plan.steps.length - 1));
  const at = (legIndex: number, metres: number): StepPoint => ({ point: pointAlong(legs[legIndex].points, metres), floorId: legs[legIndex].floorId });
  const last = legs.length - 1;
  if (index === plan.steps.length - 1 && index > 0) return at(last, Infinity); // arrival: the destination
  const target = plan.steps[index];
  if (index === 0 || target.kind === "start") return at(0, 0);
  let offset = 0;
  const inGroup: { legIndex: number; offset: number; length: number }[] = [];
  legs.forEach((leg, legIndex) => {
    const length = legLength(leg.points);
    if (plan.legGroup[legIndex] === target.group) inGroup.push({ legIndex, offset, length });
    offset += length;
  });
  if (!inGroup.length) return at(last, Infinity);
  const end = inGroup[inGroup.length - 1];
  if (target.kind === "ride") return at(end.legIndex, Infinity); // waiting at the stairs/lift, still on this floor
  // A walk step starts on the first leg of its stretch that still lies ahead (after a ride: the new floor).
  const leg = inGroup.find((entry) => entry.length > 1e-6 && entry.offset + entry.length > target.startM + 1e-6) ?? end;
  return at(leg.legIndex, target.startM - leg.offset);
}

/** The step the estimate is in: the ride while waiting at stairs/lift, the last step on arrival. */
export function stepFor(plan: Plan, p: WalkPosition): number | null {
  if (!plan.steps.length) return null;
  if (p.arrived) return plan.steps.length - 1;
  const group = plan.legGroup[p.legIndex] ?? 0;
  if (p.atConnector) return plan.rideStep[group] ?? null;
  let lastWalk: number | null = null;
  for (let i = 0; i < plan.steps.length; i++) {
    const step = plan.steps[i];
    if (step.kind !== "walk" || step.group !== group) continue;
    if (step.endM > p.alongRouteM + 0.01) return i;
    lastWalk = i;
  }
  return lastWalk;
}

// ---------- the running walk ----------

interface Running {
  key: string;
  plan: Plan;
  anchorM: number;
  position: string; // last known state.position, so only a real change counts as a correction
}

let walk: WalkWithMe | null = null;
let running: Running | null = null;
let driving = false; // our own setWalkStep calls
let correcting = false; // inside a correction: the step follows the estimate both ways

function instance(): WalkWithMe {
  if (walk) return walk;
  walk = createWalkWithMe();
  walk.on("position", onPosition);
  walk.on("legEnded", (event) => {
    if (event.end === "connector" && running) {
      const target = stepFor(running.plan, event.position);
      if (target !== null) drive(target, true); // wait here: the ride step is said, the dot holds until "next"
    }
  });
  walk.on("arrived", () => {
    useWalkMotion.setState({ arrived: true });
    showNotice(ABOUT_THERE);
    const { handsFree, speechAvailable } = useTwin.getState();
    if (handsFree) setTimeout(() => void speak(ABOUT_THERE, speechAvailable), 1500); // after the step line
  });
  walk.on("status", (status) => {
    if (simulating || simForced) return; // the desktop demo / e2e feeds its own steps, whatever the sensors say
    const text = STATUS_TEXT[status];
    if (text && running) showNotice(text);
  });
  return walk;
}

let simulating = false;
let simForced = false; // __walkSim runs the estimate even with Walk with me off or the sensors refused

function onPosition(p: WalkPosition): void {
  if (!running) return;
  if (correcting) running.anchorM = p.alongRouteM;
  const drift = Math.abs(p.alongRouteM - running.anchorM);
  useWalkMotion.setState({ estimate: p, uncertaintyM: Math.max(1.5, 0.1 * drift), arrived: p.arrived });
  const target = stepFor(running.plan, p);
  if (target === null) return;
  drive(target, correcting);
}

function drive(target: number, bothWays: boolean): void {
  const current = useTwin.getState().walkStep;
  if (current === null || target === current || (!bothWays && target < current)) return;
  driving = true;
  try {
    useTwin.getState().setWalkStep(target); // like the Next button: Walk speaks the new step
  } finally {
    driving = false;
  }
}

function positionKey(state: BuildingState | null): string {
  const p = state?.position;
  return p ? `${p.floor_id}|${p.space_id}|${p.point?.join(",") ?? ""}` : "";
}

function routeKey(route: Route | null | undefined): string {
  return route?.ok ? `${route.start}|${route.destination}|${route.length_m}|${route.segments?.length ?? 0}` : "";
}

function stop(): void {
  if (!running) return;
  running = null;
  simulating = false;
  walk?.stop();
  useWalkMotion.setState({ estimate: null, uncertaintyM: 0, arrived: false });
}

function start(route: Route, key: string): void {
  stop();
  const w = instance();
  const plan = buildPlan(walkSteps().map(readable), route);
  running = { key, plan, anchorM: 0, position: positionKey(useTwin.getState().state) };
  w.start(route); // listeners are on: a route that starts at stairs ends leg 0 right here
  // Switched on mid-walk: start the estimate at the step the person is on.
  const step = useTwin.getState().walkStep ?? 0;
  const from = plan.steps[step];
  if (step > 0 && from && running) correct(() => w.resetTo({ distanceAlong: from.startM }));
}

function correct(run: () => void): void {
  correcting = true;
  try {
    run();
  } finally {
    correcting = false;
  }
}

/** Keep the module in step with the store: start, stop, corrections, the person's Next/Back. */
function sync(): void {
  const { walkStep, state, buildingKey } = useTwin.getState();
  const { on } = useWalkMotion.getState();
  const route = state?.route;
  const key = route?.ok && buildingKey ? `${buildingKey}|${routeKey(route)}` : "";
  if ((!on && !simForced) || walkStep === null || !key || !route) return stop();
  if (!running || running.key !== key) return start(route, key);
  // "I'm here", a dragged dot or a position set by voice: the person says where they are.
  const position = positionKey(state);
  if (position !== running.position) {
    running.position = position;
    const p = state?.position;
    const point = p?.point ?? (p ? useTwin.getState().model?.spaceById.get(p.space_id)?.anchor : undefined);
    if (p && point) correct(() => walk?.resetTo({ point: [point[0], point[1]], floorId: p.floor_id }, { calibrate: true }));
  }
}

function onUserStep(step: number): void {
  if (!running || !walk) return;
  const p = walk.position();
  const plan = running.plan;
  const ride = p ? plan.rideStep[plan.legGroup[p.legIndex] ?? 0] : undefined;
  if (p?.atConnector && ride !== undefined && step === ride + 1) {
    walk.next(); // through the stairs/lift: Next button, "next" by voice or "Hey Wanda, next"
    return;
  }
  // Same point as the confirmed dot (stepStart), so the estimate and the dot agree, also after a floor change.
  const route = useTwin.getState().state?.route;
  const at = route ? stepStart(walkSteps().map(readable), route, step) : null;
  if (at) correct(() => walk?.resetTo({ point: at.point, floorId: at.floorId }));
}

// ---------- the confirmed dot: Next/Back say "I did this step" ----------
// Pressing Next (button, list, "next" by voice) moves the "You are here" dot to the end of the step just done, Back
// moves it back. It is set like "I'm here" (setHere: on screen at once, the server learns it as context.here with
// the next chat message, never a call of its own). Steps driven by the Walk with me estimate do not move it.

type Here = { space_id: string; floor_id: string; point?: Point | null };
let beforeGuide: { position: BuildingState["position"]; pendingHere: Here | null } | null = null;
let confirmedKey = "";

function inPolygon(point: Point, polygon: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > point[1] !== yj > point[1] && point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function edgeDistance(point: Point, polygon: Point[]): number {
  let best = Infinity;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [a, b] = [polygon[j], polygon[i]];
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const l2 = dx * dx + dy * dy;
    const t = l2 ? Math.max(0, Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / l2)) : 0;
    best = Math.min(best, Math.hypot(a[0] + t * dx - point[0], a[1] + t * dy - point[1]));
  }
  return best;
}

/** The room a route point lies in (a point on a door line: the nearest room). */
function spaceAt(floorId: string, point: Point): string | null {
  const spaces = useTwin.getState().model?.floorById.get(floorId)?.spaces ?? [];
  const inside = spaces.filter((space) => inPolygon(point, space.polygon));
  const pick = inside.find((space) => space.type !== "outdoor") ?? inside[0];
  if (pick) return pick.id;
  let best: { id: string; d: number } | null = null;
  for (const space of spaces) {
    const d = edgeDistance(point, space.polygon);
    if (!best || d < best.d) best = { id: space.id, d };
  }
  return best?.id ?? null;
}

function confirmStep(step: number): void {
  const { state } = useTwin.getState();
  const route = state?.route;
  if (!route?.ok) return;
  const at = stepStart(walkSteps().map(readable), route, step);
  if (!at) return;
  // Arrival: the dot is in the destination room, not in whatever room the last route point happens to touch.
  const total = walkSteps().length;
  const destination = step >= total - 1 && route.destination ? useTwin.getState().model?.spaceById.get(route.destination) : undefined;
  const space = destination ? destination.id : spaceAt(at.floorId, at.point);
  if (!space) return;
  const floorId = destination?.floor_id ?? at.floorId;
  const inside = destination ? inPolygon(at.point, destination.polygon) : true;
  const point: Point | null = inside ? [Math.round(at.point[0] * 100) / 100, Math.round(at.point[1] * 100) / 100] : null;
  const here = { space_id: space, floor_id: floorId, point };
  confirmedKey = `${floorId}|${space}|${point?.join(",") ?? ""}`;
  if (running) running.position = confirmedKey; // ours, not a correction: the estimate is reset by onUserStep
  useTwin.getState().setHere(here);
}

/** End of the guide: Done (on the last step) leaves the dot at the destination; End route midway puts back the
 * position from before the guide, unless the person set one herself meanwhile. */
function endGuide(lastStep: number): void {
  const before = beforeGuide;
  beforeGuide = null;
  const total = walkSteps().length;
  if (total && lastStep >= total - 1) {
    confirmStep(total - 1);
    return;
  }
  const state = useTwin.getState().state;
  if (!before || !confirmedKey || positionKey(state) !== confirmedKey) return;
  useTwin.setState({ state: state ? { ...state, position: before.position } : state, pendingHere: before.pendingHere });
}

if (typeof window !== "undefined") {
  useTwin.subscribe((state, prev) => {
    if (state.walkStep !== null && prev.walkStep === null) {
      beforeGuide = { position: state.state?.position ?? null, pendingHere: state.pendingHere };
      confirmedKey = "";
    } else if (state.walkStep === null && prev.walkStep !== null) {
      if (state.loading) beforeGuide = null; // another building opens: nothing to keep or put back
      else endGuide(prev.walkStep);
    }
    if (state.walkStep !== prev.walkStep && state.walkStep !== null && prev.walkStep !== null && !driving) {
      confirmStep(state.walkStep);
      if (running) onUserStep(state.walkStep);
    }
    if (state.walkStep !== prev.walkStep || state.state !== prev.state || state.buildingKey !== prev.buildingKey) sync();
  });
  useWalkMotion.subscribe((state, prev) => {
    if (state.on !== prev.on) sync();
  });
  // Desktop demo and e2e: synthetic steps through the real detector, no phone needed. __walkSim(0) stops.
  window.__walkSim = (stepsPerSecond: number) => {
    // Runs regardless of the switch and the motion permission (a refused or missing sensor must not block the demo).
    simForced = stepsPerSecond > 0;
    if (simForced) sync();
    if (!running) return;
    simulating = stepsPerSecond > 0;
    instance().simulate(stepsPerSecond);
    if (!simForced) sync(); // switch off: stop the estimate unless Walk with me itself is on
  };
  (window as unknown as { __walkMotion: typeof useWalkMotion }).__walkMotion = useWalkMotion;
  // e2e: the confirmed dot's point for a step of the drawn route (stepStart on the guide's lines).
  (window as unknown as { __walkStepStart: (step: number) => StepPoint | null }).__walkStepStart = (step) => {
    const route = useTwin.getState().state?.route;
    return route?.ok ? stepStart(walkSteps().map(readable), route, step) : null;
  };
}
