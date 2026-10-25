// Inspection round (owner: round session): "all fire extinguishers on the ground floor", walked in a short order.
// Deterministic, no agent: POST /api/round plans it with the same plan_round the chat agent uses (exact order up to
// 8 stops), so panel and chat give the same stops, order and metres; the server draws it as state.route.round. One stop
// per device. Guidance goes leg by leg, device to device: each leg is its own route from the previous device's position
// (start_point) to this device's position (destination_point), so the step sheet (ui/Walk.tsx) shows only the way to the
// next device; "Done" checks the device and loads the next leg.
//
// Voice hooks for the integrator: roundDone() ("Hey Wanda, done"), roundStatus().text ("how many left").
// The main store (store.ts) is used only through its public actions: applyState, startWalk, stopWalk, clearRoute,
// setHighlight, flyTo, focusFloor, select.

import { create } from "zustand";
import { api } from "../api/client";
import type { RoutePoints } from "../api/client";
import type { AgentRound, Building, BuildingState, PlannedRound, Route } from "../api/types";
import { prettyType } from "../model/palette";
import { useTwin } from "../store";
import { walkMinutes } from "../walkInfo";
import { areaOptions, entranceRoom, missingDevicesNote, typeMatches } from "./choices";

export const ROUND_BLUE = "#004fab";

export interface RoundStop {
  /** What "checked" holds: the device id (one stop per device), or the room id for a round of rooms. */
  key: string;
  spaceId: string;
  floorId: string;
  /** The room's name. */
  name: string;
  /** The device's name ("Fire extinguisher H-A2"); "" for a round of rooms. */
  device: string;
  assetIds: string[];
  /** The device's position, where its leg ends; null: the room's anchor. */
  position: [number, number] | null;
}

export interface RoundPlan {
  building: string;
  type: string;
  area: string;
  startId: string;
  startName: string;
  /** The exact start in the start room (the person's dot), null: the room. */
  startPoint: [number, number] | null;
  stops: RoundStop[];
  lengthM: number;
  unreachable: string[];
  /** The round ends back at the start: after the last stop, "Done" guides the way back as a final leg. */
  returnToStart: boolean;
  /** Metres of each leg: legsM[i] from the stop before (or the start) to stop i; one more for the way back. From
   * plan_round's legs (POST /api/round); null when not known (a round taken over from the chat). */
  legsM?: number[] | null;
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
  /** Plan the round back to the start (planner choice "End: back at the start"). */
  returnToStart: boolean;
  busy: string | null;
  error: string | null;
  plan: RoundPlan | null;
  guiding: boolean;
  index: number;
  checked: string[];
  /** Walking the final leg from the last stop back to the start. */
  returning: boolean;
  finished: boolean;
  whatIf: WhatIf | null;
  /** Tap two rooms for "What if a door here?": the first one picked so far. */
  picking: { first: string | null } | null;
  /** A door suggested from outside (URL hash or integrator): two room ids. */
  suggestion: [string, string] | null;
  /** A what-if door waiting for a yes: nothing is changed in the building before roundConfirmDoor(). */
  pendingDoor: [string, string] | null;
}

export const useRound = create<RoundState>(() => ({
  open: false,
  type: "",
  area: "Whole building",
  startId: null,
  returnToStart: false,
  busy: null,
  error: null,
  plan: null,
  guiding: false,
  index: 0,
  checked: [],
  returning: false,
  finished: false,
  whatIf: null,
  picking: null,
  suggestion: null,
  pendingDoor: null,
}));

// ---------- planning ----------

/** The round last drawn by this page or taken over from the chat, so the watcher below opens each round once. */
let adoptedKey = "";

function startRoom(building: Building, chosen: string | null): string | null {
  return chosen ?? useTwin.getState().state?.position?.space_id ?? entranceRoom(building.openings, building.spaces);
}

/** The stops of a planned round, in its order; null when the building does not have one of its rooms. */
function roundStops(round: AgentRound): RoundStop[] | null {
  const model = useTwin.getState().model;
  if (!model) return null;
  const stops: RoundStop[] = [];
  for (const stop of round.stops) {
    const space = model.spaceById.get(stop.space_id);
    if (!space) return null;
    const assetIds = stop.asset_id ? [stop.asset_id] : [...stop.asset_ids];
    stops.push({
      key: stop.asset_id ?? stop.space_id,
      spaceId: space.id,
      floorId: space.floor_id,
      name: space.name,
      device: stop.asset_id ? (stop.name ?? model.assetById?.get(stop.asset_id)?.name ?? "") : "",
      assetIds,
      position: stop.position ?? null,
    });
  }
  return stops.length ? stops : null;
}

/** Each leg's metres from the server's stops (plus the way back), or null when the round does not carry them. */
function roundLegs(round: AgentRound): number[] | null {
  const legs = round.stops.map((stop) => stop.leg_m);
  if (round.return_to_start) legs.push(round.back_to_start_m);
  return legs.every((leg) => typeof leg === "number") ? (legs as number[]) : null;
}

/** start_point / destination_point for /api/route. */
function points(from: [number, number] | null, to: [number, number] | null): RoutePoints {
  return {
    ...(from ? { start_point: { x: from[0], y: from[1] } } : {}),
    ...(to ? { destination_point: { x: to[0], y: to[1] } } : {}),
  };
}

/** The plan from a server round: plan_round's stops in its order, its total and its legs. */
function plannedFrom(building: string, type: string, area: string, planned: Extract<PlannedRound, { ok: true }>): RoundPlan | null {
  const stops = roundStops(planned.info);
  if (!stops) return null;
  const legs = planned.stops.map((stop) => stop.leg_m);
  if (planned.info.return_to_start) legs.push(planned.back_to_start_m ?? 0);
  return {
    building,
    type,
    area,
    startId: planned.info.start,
    startName: useTwin.getState().model?.spaceById.get(planned.info.start)?.name ?? planned.start,
    startPoint: planned.info.start_point ?? null,
    stops,
    lengthM: planned.total_m,
    // plan_round ends the list with "(left out of the round)"; the panel says that itself.
    unreachable: (planned.unreachable ?? []).filter((name) => !name.startsWith("(")),
    returnToStart: !!planned.info.return_to_start,
    legsM: legs.length === stops.length + (planned.info.return_to_start ? 1 : 0) ? legs : null,
  };
}

/** Plan the round for the current choices on the server (POST /api/round) and draw it on the map. A refusal (no such
 * device here, too many rooms, ...) shows the server's words in the panel. */
export async function planRound(): Promise<RoundPlan | null> {
  const { buildingKey, building, model } = useTwin.getState();
  const { type, area, startId, returnToStart } = useRound.getState();
  if (!buildingKey || !building || !model) return null;
  if (!type) {
    useRound.setState({ plan: null, error: null });
    return null;
  }
  const start = startRoom(building, startId);
  if (!start) {
    useRound.setState({ plan: null, error: "No start room: tap “I'm here” first." });
    return null;
  }
  // Starting where I am: the first leg starts at the dot, not in the middle of the room.
  const position = useTwin.getState().state?.position;
  const startPoint = position && position.space_id === start ? (position.point ?? null) : null;
  const reply = await api.round(buildingKey, type, { area, start, startPoint, returnToStart });
  const planned = reply.round;
  // The drawn round carries its stops (state.route.round): it is ours, the chat watcher below must not take it over.
  if (planned.ok) adoptedKey = agentRoundKey(buildingKey, planned.info);
  useTwin.getState().applyState(reply.state);
  if (!planned.ok) {
    useRound.setState({ plan: null, error: planned.error ?? planned.question ?? "No round for this choice." });
    return null;
  }
  const plan = plannedFrom(buildingKey, type, area, planned);
  if (!plan) {
    useRound.setState({ plan: null, error: "The planned round names a room this map does not have." });
    return null;
  }
  useRound.setState({ plan, error: null });
  showStops(plan, null);
  useTwin.getState().requestCamera({ kind: "object", ids: [plan.startId, ...plan.stops.map((stop) => stop.spaceId)] });
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
  // No type asked for: the panel opens with "What" empty (or the one chosen before), the person picks.
  const known = type ? building?.assets.find((asset) => typeMatches(asset, type))?.type : undefined;
  useRound.setState({
    open: true,
    type: known ?? useRound.getState().type,
    ...(area ? { area } : {}),
    guiding: false,
    finished: false,
    error: null,
  });
  // A map without the devices (a plan read before anyone added them): say so instead of an empty "What" list.
  const missing = missingDevicesNote(building?.assets ?? [], type);
  if (missing) {
    useRound.setState({ plan: null, error: missing });
    return;
  }
  if (type || area) await busy("Planning the round…", planRound);
}

export function closeRound(): void {
  const { guiding } = useRound.getState();
  if (guiding) endRound();
  useRound.setState({ open: false, plan: null, whatIf: null, picking: null, pendingDoor: null, error: null });
  useTwin.getState().setHighlight("round", null);
  useTwin.getState().setHighlight("round-door", null);
  if (useTwin.getState().state?.route) void useTwin.getState().clearRoute();
}

export async function setRoundChoice(choice: Partial<Pick<RoundState, "type" | "area" | "startId" | "returnToStart">>): Promise<void> {
  useRound.setState({ ...choice, whatIf: null, finished: false, checked: [], index: 0 });
  await busy("Planning the round…", planRound);
}

/** Held while guidance is switched on purpose (a leg loads, a round ends), so the watchers below do not take the
 * closing step sheet for the walker leaving. A counter: one switch may start while another is still settling. */
let switching = 0;
/** A leg (next stop, or the way back) is loading: further Done taps and "done" are ignored until it is in. */
let legLoading = false;

/** Where leg `index` starts: the previous device, or for the first leg the start (the person's dot when it is in the
 * start room, so a "From" room picked in the panel is kept). */
function legStart(plan: RoundPlan, index: number): { spaceId: string; point: [number, number] | null } {
  if (index > 0) return { spaceId: plan.stops[index - 1].spaceId, point: plan.stops[index - 1].position };
  const position = useTwin.getState().state?.position;
  if (position && position.space_id === plan.startId && position.point) return { spaceId: plan.startId, point: position.point };
  return { spaceId: plan.startId, point: plan.startPoint };
}

/** Route from the previous device (or the start) to the device of stop `index` and start the step sheet. */
async function goToStop(index: number): Promise<void> {
  const { plan } = useRound.getState();
  const key = useTwin.getState().buildingKey;
  if (!plan || !key) return;
  const from = legStart(plan, index);
  const stop = plan.stops[index];
  switching++;
  try {
    // Same room: no step sheet, the panel says "You are in <room>" (a few metres along the wall need no directions).
    const result = from.spaceId === stop.spaceId ? null : await api.route(key, from.spaceId, stop.spaceId, false, [], points(from.point, stop.position));
    if (result?.route.ok) {
      useTwin.getState().applyState(result.state);
      useRound.setState({ index, guiding: true, returning: false });
      useTwin.getState().startWalk();
    } else {
      // Already in the room (two stops in one place) or no route: show the stop, the step sheet stays closed.
      const listening = useTwin.getState().handsFree;
      useTwin.getState().stopWalk();
      if (listening) useTwin.getState().setHandsFree(true); // "Hey Wanda, done" still checks this stop
      if (useTwin.getState().state?.route) await useTwin.getState().clearRoute();
      useRound.setState({ index, guiding: true, returning: false });
      useTwin.getState().flyTo(stop.assetIds[0] ?? stop.spaceId);
    }
    showStops(plan, index);
  } finally {
    switching--;
  }
}

/** Start guidance at the first stop not checked yet. */
export async function startRound(): Promise<void> {
  const { plan, finished } = useRound.getState();
  if (!plan) return;
  // A finished round starts over; a paused one goes on at the first stop not checked yet.
  const checked = finished || useRound.getState().checked.length >= plan.stops.length ? [] : useRound.getState().checked;
  const first = plan.stops.findIndex((stop) => !checked.includes(stop.key));
  useRound.setState({ finished: false, returning: false, checked });
  await busy("Starting…", () => goToStop(first < 0 ? 0 : first));
}

/** The final leg: from the last stop back to the start. Returns false when there is no way to walk (already there). */
async function goBack(): Promise<boolean> {
  const { plan, index } = useRound.getState();
  const key = useTwin.getState().buildingKey;
  if (!plan || !key) return false;
  const from = plan.stops[index];
  if (from.spaceId === plan.startId) return false;
  switching++;
  try {
    const result = await api.route(key, from.spaceId, plan.startId, false, [], points(from.position, plan.startPoint));
    if (!result.route.ok) return false;
    useTwin.getState().applyState(result.state);
    useRound.setState({ returning: true, guiding: true });
    useTwin.getState().startWalk();
    useTwin.getState().setHighlight("round", null);
    return true;
  } finally {
    switching--;
  }
}

function finishRound(): string {
  const { plan, checked } = useRound.getState();
  // finished before guiding ends, so whoever watches the end of guidance sees a completed round.
  useRound.setState({ finished: true });
  endRound();
  useTwin.getState().setHighlight("round", null);
  return `Round complete: ${checked.length} of ${plan?.stops.length ?? 0} stops checked.`;
}

/** "Done": the current stop is checked; go on to the next stop, or finish the round. Returns what to say. */
export async function roundDone(): Promise<string> {
  if (legLoading || useRound.getState().busy) return "One moment, the next stop is loading.";
  legLoading = true;
  try {
    return await checkStop();
  } finally {
    legLoading = false;
  }
}

async function checkStop(): Promise<string> {
  const { plan, index, checked, guiding, returning } = useRound.getState();
  if (!plan || !guiding) return "No inspection round is running.";
  if (returning) return finishRound();
  const stop = plan.stops[index];
  const nowChecked = checked.includes(stop.key) ? checked : [...checked, stop.key];
  useRound.setState({ checked: nowChecked });
  const next = plan.stops.findIndex((candidate, i) => i > index && !nowChecked.includes(candidate.key));
  if (next < 0) {
    if (plan.returnToStart && (await busy("Back to the start…", goBack))) return roundStatus().text;
    return finishRound();
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
  switching++;
  try {
    useRound.setState({ guiding: false, returning: false });
    useTwin.getState().stopWalk();
  } catch (error) {
    switching--;
    throw error;
  }
  void useTwin
    .getState()
    .clearRoute()
    .catch(() => {})
    .finally(() => switching--);
}

/** "How far" in a round: to the next stop and for the whole rest of the round. legLeftM: metres left on the leg
 * being walked (null: not known, e.g. the stop is in the room you are in). */
export function roundHowFar(legLeftM: number | null): string {
  const { plan, index, checked, guiding, returning } = useRound.getState();
  if (!plan || !guiding) return "No inspection round is running.";
  const leg = Math.round(legLeftM ?? 0);
  if (returning) return `${leg} metres back to the start.`;
  const legs = plan.legsM;
  const later = legs
    ? plan.stops.reduce((sum, stop, i) => (i > index && !checked.includes(stop.key) ? sum + legs[i] : sum), 0) + (plan.returnToStart ? (legs[plan.stops.length] ?? 0) : 0)
    : null;
  const toStop = legLeftM === null ? `You are at stop ${index + 1}` : `${leg} metres to the next stop`;
  return later === null ? `${toStop}.` : `${toStop}, ${Math.round(leg + later)} metres left in the round.`;
}

export interface RoundStatus {
  active: boolean;
  stop: number;
  total: number;
  left: number;
  checked: number;
  /** On the final leg back to the start. */
  returning: boolean;
  label: string;
  text: string;
}

/** Where the round stands, for the header and for "how many left". */
export function roundStatus(): RoundStatus {
  const { plan, index, checked, guiding, returning } = useRound.getState();
  if (!plan) return { active: false, stop: 0, total: 0, left: 0, checked: 0, returning: false, label: "", text: "No inspection round is planned." };
  const total = plan.stops.length;
  const left = total - checked.length;
  if (guiding && returning) {
    const route = useTwin.getState().state?.route;
    const metres = route?.ok && typeof route.length_m === "number" ? ` · ${Math.round(route.length_m)} m` : "";
    return { active: true, stop: total, total, left, checked: checked.length, returning: true, label: `Back to the start${metres}`, text: `All stops done. Back to the start, ${plan.startName}${metres ? `, ${metres.slice(3)}` : ""}.` };
  }
  const stop = plan.stops[index];
  const label = stop?.device || assetLabel(plan.type, stop?.assetIds.length ?? 1);
  const text = guiding
    ? `Stop ${index + 1} of ${total}: ${label} in ${stop.name}. ${left} ${left === 1 ? "stop" : "stops"} left.`
    : `${checked.length} of ${total} stops checked, ${left} left.`;
  return { active: guiding, stop: index + 1, total, left, checked: checked.length, returning: false, label, text };
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

// ---------- a round the chat agent planned ----------

function agentRoundKey(building: string, round: AgentRound): string {
  return JSON.stringify([building, round.start, round.stops.map((stop) => stop.asset_id ?? stop.space_id), round.return_to_start]);
}

/** Take over a round the chat agent planned (plan_round, state.route.round): the same stops in the same order, so
 * Start, "guide me" and "done" go stop by stop. The agent's drawn route stays on the map. */
export function adoptRound(round: AgentRound, lengthM: number | null): RoundPlan | null {
  const { buildingKey, building, model } = useTwin.getState();
  if (!buildingKey || !building || !model) return null;
  const stops = roundStops(round);
  if (!stops) return null;
  adoptedKey = agentRoundKey(buildingKey, round);
  if (useRound.getState().guiding) endRound();
  // The area the panel shows: the floor when all stops are on one floor (so "plan again" keeps it), else everything.
  const floors = [...new Set(stops.map((stop) => stop.floorId))];
  const floor = floors.length === 1 ? model.floorById.get(floors[0]) : undefined;
  const floorName = floor ? floor.name || `Level ${floor.level}` : "";
  const area = floorName && areaOptions(building.floors, building.spaces).includes(floorName) ? floorName : "Whole building";
  const type = building.assets.find((asset) => typeMatches(asset, round.device_type))?.type ?? round.device_type;
  const plan: RoundPlan = {
    building: buildingKey,
    type,
    area,
    startId: round.start,
    startName: model.spaceById.get(round.start)?.name ?? round.start,
    startPoint: round.start_point ?? null,
    stops,
    lengthM: round.total_m ?? lengthM ?? 0,
    unreachable: [],
    returnToStart: !!round.return_to_start,
    // plan_round's legs ride along in state.route.round, so "how far" knows the rest of a chat-planned round too.
    legsM: roundLegs(round),
  };
  useRound.setState({ open: true, type, area, startId: round.start, returnToStart: plan.returnToStart, plan, guiding: false, returning: false, index: 0, checked: [], finished: false, whatIf: null, picking: null, error: null, busy: null });
  showStops(plan, null);
  return plan;
}

/** Is this drawn route the whole round (the agent's, or the one planRound drew), not one leg of it? */
function isWholeRound(route: Route | null | undefined, plan: RoundPlan): boolean {
  if (!route?.ok) return false;
  if (route.round) return true;
  const ids = plan.stops.map((stop) => stop.spaceId);
  if (plan.returnToStart) return route.start === plan.startId && route.destination === plan.startId && JSON.stringify(route.via ?? []) === JSON.stringify(ids);
  return route.start === plan.startId && route.destination === ids[ids.length - 1] && JSON.stringify(route.via ?? []) === JSON.stringify(ids.slice(0, -1));
}

// ---------- what if: a new door ----------

/** Add a door between two neighbouring rooms, plan the same round again on the server and compare the two totals. */
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

/** "What if a door here?" only asks first: the panel shows "Add a door between A and B? This changes the building."
 * and nothing is sent to the server before roundConfirmDoor(). */
export function proposeDoor(first: string, second: string): void {
  useRound.setState({ pendingDoor: [first, second], picking: null });
}

export async function roundConfirmDoor(): Promise<WhatIf | null> {
  const pending = useRound.getState().pendingDoor;
  useRound.setState({ pendingDoor: null });
  return pending ? roundWhatIfDoor(pending[0], pending[1]) : null;
}

export function cancelDoor(): void {
  useRound.setState({ pendingDoor: null });
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
    if (now.buildingKey !== before.buildingKey) adoptedKey = "";
    if (now.buildingKey !== before.buildingKey && useRound.getState().plan) {
      useRound.setState({ plan: null, whatIf: null, guiding: false, returning: false, checked: [], index: 0, picking: null, pendingDoor: null });
    }
  });
  // The chat agent planned a round (state.route.round): open it here once, with its stops in its order.
  useTwin.subscribe((now, before) => {
    const route = now.state?.route;
    if (route === before.state?.route || !route?.ok || !route.round || !now.buildingKey) return;
    if (agentRoundKey(now.buildingKey, route.round) === adoptedKey) return;
    adoptRound(route.round, typeof route.length_m === "number" ? route.length_m : null);
  });
  // "Guide me" (card, chat or voice) on the whole round: guide it stop by stop instead.
  useTwin.subscribe((now, before) => {
    if (switching || before.walkStep !== null || now.walkStep === null) return;
    const { plan, guiding, busy: working } = useRound.getState();
    if (!plan || guiding || working || plan.building !== now.buildingKey || !isWholeRound(now.state?.route, plan)) return;
    void startRound();
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
      useTwin.getState().select(null);
      proposeDoor(first, spaceId);
    }
  });
  (window as unknown as { __round: unknown }).__round = { useRound, adoptRound, openRound, planRound, startRound, roundDone, roundStatus, roundHowFar, roundWhatIfDoor, proposeDoor, roundConfirmDoor, roundUndoDoor, endRound, pickDoorRooms, closeRound };
}
