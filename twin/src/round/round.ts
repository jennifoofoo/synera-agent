// Inspection round (owner: round session): "all fire extinguishers on the ground floor", walked in a short order.
// Deterministic, no agent: the assets come from the building model, the distances from /api/route (cached per
// building and door/closure state), the order from order.ts (nearest neighbour + 2-opt), the drawn route and its
// length from one /api/route call with the stops as via. Guidance goes leg by leg: each stop is its own route, so
// the step sheet (ui/Walk.tsx) shows only the way to the next stop; "Done" checks the stop and loads the next leg.
//
// Voice hooks for the integrator: roundDone() ("Hey Wanda, done"), roundStatus().text ("how many left").
// The main store (store.ts) is used only through its public actions: applyState, startWalk, stopWalk, clearRoute,
// setHighlight, flyTo, focusFloor, select.

import { create } from "zustand";
import { api } from "../api/client";
import type { Building, BuildingState, Space } from "../api/types";
import { prettyType } from "../model/palette";
import { useTwin } from "../store";
import { walkMinutes } from "../walkInfo";
import { entranceRoom, inArea, normType, orderRound, straightLine, typeMatches } from "./order";

/** Up to this many route calls the matrix is measured on real routes; above it, straight lines. */
const MAX_ROUTE_PAIRS = 231; // 21 stops + start
export const ROUND_BLUE = "#004fab";

export interface RoundStop {
  spaceId: string;
  floorId: string;
  name: string;
  assetIds: string[];
}

export interface RoundPlan {
  building: string;
  type: string;
  area: string;
  startId: string;
  startName: string;
  stops: RoundStop[];
  lengthM: number;
  /** "route": distances from /api/route; "straight": straight-line stand-in (too many stops). */
  measured: "route" | "straight";
  unreachable: string[];
}

export interface WhatIf {
  doorId: string;
  first: string;
  second: string;
  firstName: string;
  secondName: string;
  beforeM: number;
  afterM: number;
  position: [number, number] | null;
  floorId: string;
  undone: boolean;
}

interface RoundState {
  open: boolean;
  type: string;
  area: string;
  /** null: start where I am (or at the entrance). */
  startId: string | null;
  busy: string | null;
  error: string | null;
  plan: RoundPlan | null;
  guiding: boolean;
  index: number;
  checked: string[];
  finished: boolean;
  whatIf: WhatIf | null;
  /** Tap two rooms for "What if a door here?": the first one picked so far. */
  picking: { first: string | null } | null;
  /** A door suggested from outside (URL hash or integrator): two room ids. */
  suggestion: [string, string] | null;
}

export const useRound = create<RoundState>(() => ({
  open: false,
  type: "",
  area: "Whole building",
  startId: null,
  busy: null,
  error: null,
  plan: null,
  guiding: false,
  index: 0,
  checked: [],
  finished: false,
  whatIf: null,
  picking: null,
  suggestion: null,
}));

// ---------- distances ----------

const cache = new Map<string, number>();

/** Doors and closures change routes: they are part of the cache key. */
function graphKey(state: BuildingState | null): string {
  if (!state) return "";
  return JSON.stringify([
    [...state.closed].sort(),
    state.added_doors.map((door) => door.id).sort(),
    [...(state.removed_openings ?? [])].sort(),
    state.widened_openings ?? {},
  ]);
}

async function routeLength(building: string, graph: string, a: string, b: string, stepFree: boolean): Promise<number> {
  if (a === b) return 0;
  const [x, y] = a < b ? [a, b] : [b, a];
  const key = `${building}|${graph}|${stepFree}|${x}|${y}`;
  const known = cache.get(key);
  if (known !== undefined) return known;
  const { route } = await api.route(building, x, y, stepFree);
  const length = route.ok && typeof route.length_m === "number" ? route.length_m : Infinity;
  cache.set(key, length);
  return length;
}

// ---------- planning ----------

function stopsFor(building: Building, type: string, area: string): RoundStop[] {
  const spaces = new Map(building.spaces.map((space) => [space.id, space]));
  const floors = new Map(building.floors.map((floor) => [floor.id, floor]));
  const bySpace = new Map<string, string[]>();
  for (const asset of building.assets) {
    if (!typeMatches(asset, type)) continue;
    const space = spaces.get(asset.space_id);
    if (!space || !inArea(space, floors.get(space.floor_id), area)) continue;
    bySpace.set(space.id, [...(bySpace.get(space.id) ?? []), asset.id]);
  }
  return [...bySpace.keys()].sort().map((spaceId) => {
    const space = spaces.get(spaceId)!;
    return { spaceId, floorId: space.floor_id, name: space.name, assetIds: bySpace.get(spaceId)!.sort() };
  });
}

function startRoom(building: Building, chosen: string | null): string | null {
  return chosen ?? useTwin.getState().state?.position?.space_id ?? entranceRoom(building.openings);
}

/** Plan the round for the current choices: stops, order, drawn route. Draws it on the map. */
export async function planRound(): Promise<RoundPlan | null> {
  const { buildingKey, building, model } = useTwin.getState();
  const { type, area, startId } = useRound.getState();
  if (!buildingKey || !building || !model) return null;
  const stops = stopsFor(building, type, area);
  const start = startRoom(building, startId);
  if (!stops.length || !start) {
    useRound.setState({ plan: null, error: stops.length ? "No start room: tap “I'm here” first." : `No ${prettyType(type).toLowerCase()} found in ${area}.` });
    return null;
  }
  const nodes = [start, ...stops.map((stop) => stop.spaceId)];
  const n = nodes.length;
  const pairs = (n * (n - 1)) / 2;
  const measured: RoundPlan["measured"] = pairs <= MAX_ROUTE_PAIRS ? "route" : "straight";
  const distance = nodes.map(() => nodes.map(() => 0));
  const graph = graphKey(useTwin.getState().state);
  const levelOf = (floorId: string) => model.floorById.get(floorId)?.level ?? 0;
  let done = 0;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const d =
        measured === "route"
          ? await routeLength(buildingKey, graph, nodes[i], nodes[j], false)
          : straightLine(model.spaceById.get(nodes[i]) as Space, model.spaceById.get(nodes[j]) as Space, levelOf);
      distance[i][j] = distance[j][i] = d;
      if (++done % 10 === 0) useRound.setState({ busy: `Measuring routes ${done} of ${pairs}…` });
    }
  }
  // Stops that no route reaches (closed off) are left out and named.
  const unreachable = stops.filter((_, i) => !isFinite(distance[0][i + 1])).map((stop) => stop.name);
  const reachable = nodes.map((_, i) => i).filter((i) => i === 0 || isFinite(distance[0][i]));
  const sub = reachable.map((i) => reachable.map((j) => distance[i][j]));
  const order = orderRound(sub).map((k) => stops[reachable[k] - 1]);
  if (!order.length) {
    useRound.setState({ plan: null, error: "No stop can be reached from the start." });
    return null;
  }
  const last = order[order.length - 1];
  const result = await api.route(buildingKey, start, last.spaceId, false, order.slice(0, -1).map((stop) => stop.spaceId));
  if (!result.route.ok || typeof result.route.length_m !== "number") {
    useRound.setState({ plan: null, error: result.route.message ?? result.route.error ?? "No route for this round." });
    return null;
  }
  useTwin.getState().applyState(result.state);
  const plan: RoundPlan = {
    building: buildingKey,
    type,
    area,
    startId: start,
    startName: model.spaceById.get(start)?.name ?? start,
    stops: order,
    lengthM: result.route.length_m,
    measured,
    unreachable,
  };
  useRound.setState({ plan, error: null });
  showStops(plan, null);
  useTwin.getState().requestCamera({ kind: "object", ids: [start, ...order.map((stop) => stop.spaceId)] });
  return plan;
}

/** Highlight the stops' assets (all of them, or only the stop being walked to). */
function showStops(plan: RoundPlan, index: number | null): void {
  const ids = index === null ? plan.stops.flatMap((stop) => stop.assetIds) : plan.stops[index].assetIds;
  useTwin.getState().setHighlight("round", { ids, colour: ROUND_BLUE });
}

/** Run a step with a busy note; errors land in the panel. */
async function busy<T>(note: string, run: () => Promise<T>): Promise<T | null> {
  useRound.setState({ busy: note, error: null });
  try {
    return await run();
  } catch (error) {
    useRound.setState({ error: (error as Error).message });
    return null;
  } finally {
    useRound.setState({ busy: null });
  }
}

// ---------- public actions ----------

/** Open the panel, optionally with a type and an area ("fire extinguisher", "Ground floor"), and plan at once. */
export async function openRound(type?: string, area?: string): Promise<void> {
  const building = useTwin.getState().building;
  const fallbackType = building?.assets.some((asset) => normType(asset.type) === "fire extinguisher") ? "fire_extinguisher" : (building?.assets[0]?.type ?? "");
  const known = type ? building?.assets.find((asset) => typeMatches(asset, type))?.type : undefined;
  useRound.setState({
    open: true,
    type: known ?? (useRound.getState().type || fallbackType),
    ...(area ? { area } : {}),
    guiding: false,
    finished: false,
    error: null,
  });
  if (type || area) await busy("Planning the round…", planRound);
}

export function closeRound(): void {
  const { guiding } = useRound.getState();
  if (guiding) endRound();
  useRound.setState({ open: false, plan: null, whatIf: null, picking: null, error: null });
  useTwin.getState().setHighlight("round", null);
  useTwin.getState().setHighlight("round-door", null);
  if (useTwin.getState().state?.route) void useTwin.getState().clearRoute();
}

export async function setRoundChoice(choice: Partial<Pick<RoundState, "type" | "area" | "startId">>): Promise<void> {
  useRound.setState({ ...choice, whatIf: null, finished: false, checked: [], index: 0 });
  await busy("Planning the round…", planRound);
}

let switching = false;

/** Route from the previous stop (or the start) to stop `index` and start the step sheet. */
async function goToStop(index: number): Promise<void> {
  const { plan } = useRound.getState();
  const key = useTwin.getState().buildingKey;
  if (!plan || !key) return;
  const from = index === 0 ? plan.startId : plan.stops[index - 1].spaceId;
  const to = plan.stops[index].spaceId;
  switching = true;
  try {
    const result = from === to ? null : await api.route(key, from, to, false);
    if (result?.route.ok) {
      useTwin.getState().applyState(result.state);
      useRound.setState({ index, guiding: true });
      useTwin.getState().startWalk();
    } else {
      // Already in the room (two stops in one place) or no route: show the stop, the step sheet stays closed.
      useTwin.getState().stopWalk();
      if (useTwin.getState().state?.route) await useTwin.getState().clearRoute();
      useRound.setState({ index, guiding: true });
      useTwin.getState().flyTo(plan.stops[index].assetIds[0] ?? to);
    }
    showStops(plan, index);
  } finally {
    switching = false;
  }
}

/** Start guidance at the first stop not checked yet. */
export async function startRound(): Promise<void> {
  const { plan, finished } = useRound.getState();
  if (!plan) return;
  // A finished round starts over; a paused one goes on at the first stop not checked yet.
  const checked = finished || useRound.getState().checked.length >= plan.stops.length ? [] : useRound.getState().checked;
  const first = plan.stops.findIndex((stop) => !checked.includes(stop.spaceId));
  useRound.setState({ finished: false, checked });
  await busy("Starting…", () => goToStop(first < 0 ? 0 : first));
}

/** "Done": the current stop is checked; go on to the next stop, or finish the round. Returns what to say. */
export async function roundDone(): Promise<string> {
  const { plan, index, checked, guiding } = useRound.getState();
  if (!plan || !guiding) return "No inspection round is running.";
  const stop = plan.stops[index];
  const nowChecked = checked.includes(stop.spaceId) ? checked : [...checked, stop.spaceId];
  useRound.setState({ checked: nowChecked });
  const next = plan.stops.findIndex((candidate, i) => i > index && !nowChecked.includes(candidate.spaceId));
  if (next < 0) {
    endRound();
    useRound.setState({ finished: true });
    useTwin.getState().setHighlight("round", null);
    return `Round complete: ${nowChecked.length} of ${plan.stops.length} stops checked.`;
  }
  await busy("Next stop…", () => goToStop(next));
  return roundStatus().text;
}

/** Is a round being walked? (Walk.tsx: the last step's Done goes on to the next stop.) */
export function inRound(): boolean {
  return useRound.getState().guiding;
}

/** Leave guidance (the plan and the checks stay). */
export function endRound(): void {
  switching = true;
  useRound.setState({ guiding: false });
  useTwin.getState().stopWalk();
  void useTwin.getState().clearRoute();
  switching = false;
}

export interface RoundStatus {
  active: boolean;
  stop: number;
  total: number;
  left: number;
  checked: number;
  label: string;
  text: string;
}

/** Where the round stands, for the header and for "how many left". */
export function roundStatus(): RoundStatus {
  const { plan, index, checked, guiding } = useRound.getState();
  if (!plan) return { active: false, stop: 0, total: 0, left: 0, checked: 0, label: "", text: "No inspection round is planned." };
  const total = plan.stops.length;
  const left = total - checked.length;
  const stop = plan.stops[index];
  const label = assetLabel(plan.type, stop?.assetIds.length ?? 1);
  const text = guiding
    ? `Stop ${index + 1} of ${total}: ${label} in ${stop.name}. ${left} ${left === 1 ? "stop" : "stops"} left.`
    : `${checked.length} of ${total} stops checked, ${left} left.`;
  return { active: guiding, stop: index + 1, total, left, checked: checked.length, label, text };
}

export function assetLabel(type: string, count: number): string {
  const name = prettyType(type);
  return count > 1 ? `${count} × ${name.toLowerCase()}` : name;
}

/** "14 stops · 230 m · ~4 min" */
export function summary(plan: RoundPlan): string {
  const stops = `${plan.stops.length} ${plan.stops.length === 1 ? "stop" : "stops"}`;
  return `${stops} · ${Math.round(plan.lengthM)} m · ~${walkMinutes(plan.lengthM)} min`;
}

// ---------- what if: a new door ----------

/** Add a door between two neighbouring rooms, plan the same round again and compare. */
export async function roundWhatIfDoor(first: string, second: string): Promise<WhatIf | null> {
  const before = useRound.getState().plan;
  const { buildingKey: key, model } = useTwin.getState();
  if (!before || !key || !model) return null;
  return busy("Adding the door…", async () => {
    const reply = (await api.addDoor(key, first, second, true)) as { state: BuildingState; door?: { id: string; position?: [number, number] } };
    useTwin.getState().applyState(reply.state);
    const door = reply.state.added_doors.find((added) => added.id === reply.door?.id) ?? reply.state.added_doors[reply.state.added_doors.length - 1];
    useRound.setState({ busy: "Planning the round again…" });
    const after = await planRound();
    if (!after) return null;
    const whatIf: WhatIf = {
      doorId: door.id,
      first,
      second,
      firstName: model.spaceById.get(first)?.name ?? first,
      secondName: model.spaceById.get(second)?.name ?? second,
      beforeM: before.lengthM,
      afterM: after.lengthM,
      position: door.position ?? null,
      floorId: door.floor_id,
      undone: false,
    };
    useRound.setState({ whatIf, picking: null, checked: [], index: 0 });
    useTwin.getState().setHighlight("round-door", { ids: [first, second], colour: ROUND_BLUE });
    if (door.position) useTwin.getState().requestCamera({ kind: "point", point: door.position, floorId: door.floor_id, radius: 18 });
    return whatIf;
  });
}

/** Undo the what-if door: the server has no "remove door", so the added door is closed again (it stays listed
 * under Changes as a closed door; Reset in the planner removes it for good). Then the round is planned again. */
export async function roundUndoDoor(): Promise<void> {
  const { whatIf } = useRound.getState();
  const key = useTwin.getState().buildingKey;
  if (!whatIf || !key) return;
  await busy("Removing the door…", async () => {
    const reply = await api.close(key, whatIf.doorId, true);
    useTwin.getState().applyState(reply.state);
    useTwin.getState().setHighlight("round-door", null);
    useRound.setState({ whatIf: null });
    await planRound();
  });
}

/** "Saved 38 m (100 → 62 m)" */
export function whatIfLine(whatIf: WhatIf): string {
  const before = Math.round(whatIf.beforeM);
  const after = Math.round(whatIf.afterM);
  const saved = before - after;
  if (saved > 0) return `Round ${saved} m shorter (${before} → ${after} m)`;
  if (saved < 0) return `Round ${-saved} m longer (${before} → ${after} m)`;
  return `Round length unchanged (${before} m)`;
}

/** Tap two rooms on the map: arm picking; the panel watches the selection. */
export function pickDoorRooms(on: boolean): void {
  useRound.setState({ picking: on ? { first: null } : null });
}

// ---------- wiring to the main store ----------

if (typeof window !== "undefined") {
  // The step sheet was closed some other way (End route, Esc, building change): guidance pauses, the plan stays.
  useTwin.subscribe((now, before) => {
    if (switching || !useRound.getState().guiding) return;
    if (before.walkStep !== null && now.walkStep === null) useRound.setState({ guiding: false });
  });
  // Another building: the round belongs to the old one.
  useTwin.subscribe((now, before) => {
    if (now.buildingKey !== before.buildingKey && useRound.getState().plan) {
      useRound.setState({ plan: null, whatIf: null, guiding: false, checked: [], index: 0, picking: null });
    }
  });
  // Picking rooms for the what-if door: each tapped room (or a point in a room) counts.
  useTwin.subscribe((now, before) => {
    const picking = useRound.getState().picking;
    if (!picking || now.selection === before.selection || !now.selection) return;
    const spaceId = now.selection.kind === "space" ? now.selection.id : now.selection.kind === "point" ? now.selection.space_id : undefined;
    if (!spaceId) return;
    if (!picking.first) useRound.setState({ picking: { first: spaceId } });
    else if (spaceId !== picking.first) {
      const first = picking.first;
      useRound.setState({ picking: null });
      useTwin.getState().select(null);
      void roundWhatIfDoor(first, spaceId);
    }
  });
  (window as unknown as { __round: unknown }).__round = { useRound, openRound, planRound, startRound, roundDone, roundStatus, roundWhatIfDoor, roundUndoDoor, endRound, pickDoorRooms, closeRound };
}
