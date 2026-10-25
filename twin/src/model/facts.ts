// Place knowledge on the map (docs/specs/place-knowledge-page.md): where a fact's pin stands, how its age and a
// closure's end read ("since 8:10", "until tomorrow 18:00"). Pure functions, no store: tested in facts.test.ts.
// Times are shown in Europe/Berlin like the server resolves them ("bis morgen" = tomorrow 18:00 Berlin).

import type { Fact, Point } from "../api/types";
import type { BuildingModel } from "./model";

const ZONE = "Europe/Berlin";
const dayFormat = new Intl.DateTimeFormat("en-CA", { timeZone: ZONE, year: "numeric", month: "2-digit", day: "2-digit" });
const clockFormat = new Intl.DateTimeFormat("en-GB", { timeZone: ZONE, hour: "numeric", minute: "2-digit", hourCycle: "h23" });
const weekdayFormat = new Intl.DateTimeFormat("en-GB", { timeZone: ZONE, weekday: "short" });
const dateFormat = new Intl.DateTimeFormat("en-GB", { timeZone: ZONE, day: "numeric", month: "short" });

/** Days from `now` to `moment` in Berlin calendar days (0 = same day, 1 = tomorrow, -1 = yesterday). */
export function dayDiff(moment: Date, now: Date): number {
  const day = (d: Date) => {
    const [y, m, dd] = dayFormat.format(d).split("-").map(Number);
    return Date.UTC(y, m - 1, dd) / 86_400_000;
  };
  return Math.round(day(moment) - day(now));
}

/** "18:00" / "8:10" (Berlin). */
export function clock(moment: Date): string {
  return clockFormat.format(moment).replace(/^0(\d):/, "$1:");
}

/** When a timed closure ends: "until 18:00", "until tomorrow 18:00", "until Fri 18:00", "until 3 Nov 18:00". */
export function untilText(iso: string, now: Date = new Date()): string {
  const end = new Date(iso);
  if (Number.isNaN(end.getTime())) return "";
  const days = dayDiff(end, now);
  if (days <= 0) return `until ${clock(end)}`;
  if (days === 1) return `until tomorrow ${clock(end)}`;
  if (days < 7) return `until ${weekdayFormat.format(end)} ${clock(end)}`;
  return `until ${dateFormat.format(end)} ${clock(end)}`;
}

/** Since when a fact holds: "since 8:10", "since yesterday 8:10", "since Fri 8:10", "since 20 Oct". */
export function sinceText(iso: string, now: Date = new Date()): string {
  const start = new Date(iso);
  if (Number.isNaN(start.getTime())) return "";
  const days = dayDiff(now, start);
  if (days <= 0) return `since ${clock(start)}`;
  if (days === 1) return `since yesterday ${clock(start)}`;
  if (days < 7) return `since ${weekdayFormat.format(start)} ${clock(start)}`;
  return `since ${dateFormat.format(start)}`;
}

/** A date for the history list: "today 8:10", "yesterday 12:40", "Fri 9:00", "20 Oct 9:00". */
export function whenText(iso: string, now: Date = new Date()): string {
  const moment = new Date(iso);
  if (Number.isNaN(moment.getTime())) return "";
  const days = dayDiff(now, moment);
  if (days === 0) return `today ${clock(moment)}`;
  if (days === 1) return `yesterday ${clock(moment)}`;
  if (days > 1 && days < 7) return `${weekdayFormat.format(moment)} ${clock(moment)}`;
  return `${dateFormat.format(moment)} ${clock(moment)}`;
}

/** Where a fact's pin stands (plan metres) and on which floor: its own point, else its thing, door, or room. */
export function factPlace(model: BuildingModel, fact: Fact): { floor_id: string; point: Point } | null {
  const anchor = fact.anchor;
  const space = model.spaceById.get(anchor.space_id);
  const floorId = anchor.floor_id || space?.floor_id;
  if (!floorId) return null;
  if (anchor.point) return { floor_id: floorId, point: anchor.point };
  const asset = anchor.asset_id ? model.assetById.get(anchor.asset_id) : undefined;
  if (asset) return { floor_id: asset.floor_id, point: asset.position };
  const opening = anchor.element_id ? model.openingById.get(anchor.element_id) : undefined;
  if (opening) return { floor_id: opening.floor_id, point: opening.position };
  return space ? { floor_id: floorId, point: space.anchor } : null;
}

/** Notes and issues are pins; closures already have their own marks (glyph, hatching, "Closed until ..."). */
export function pinFacts(facts: readonly Fact[] | undefined): Fact[] {
  return (facts ?? []).filter((fact) => fact.kind !== "closure" && fact.status === "open" && !fact.resolves);
}

export interface FactPinGroup {
  /** Stable id: the first fact's id. */
  id: string;
  point: Point;
  floor_id: string;
  facts: Fact[];
  /** Only the room is known (no point, thing or door): the pin sits above the room name, not on it. */
  roomOnly: boolean;
}

/** One pin per spot: facts on the same point (or thing, door, room) share a pin with a count. Issues first. */
export function groupFactPins(model: BuildingModel, facts: readonly Fact[]): FactPinGroup[] {
  const groups = new Map<string, FactPinGroup>();
  const sorted = [...facts].sort((a, b) => Number(b.kind === "issue") - Number(a.kind === "issue") || a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
  for (const fact of sorted) {
    const place = factPlace(model, fact);
    if (!place) continue;
    const anchor = fact.anchor;
    const roomOnly = !anchor.point && !anchor.asset_id && !(anchor.element_id && model.openingById.has(anchor.element_id));
    const key = `${place.floor_id}|${place.point[0].toFixed(1)}|${place.point[1].toFixed(1)}|${roomOnly}`;
    const known = groups.get(key);
    if (known) known.facts.push(fact);
    else groups.set(key, { id: fact.id, point: place.point, floor_id: place.floor_id, facts: [fact], roomOnly });
  }
  return [...groups.values()].sort((a, b) => a.id.localeCompare(b.id));
}

/** Stop spaces and element ids of timed closures -> ISO end, so a closed glyph or chip can say "until ...". */
export function untilByPlace(model: BuildingModel, closedUntil: Record<string, string> | undefined): Map<string, string> {
  const out = new Map<string, string>();
  for (const [id, end] of Object.entries(closedUntil ?? {})) {
    out.set(id, end);
    const connector = model.connectorById.get(id);
    if (connector) for (const spaceId of connector.space_ids) out.set(spaceId, end);
  }
  return out;
}

/** The place's name for the card title: thing, door, stairs/lift or room. */
export function factPlaceName(model: BuildingModel, fact: Fact): string {
  const anchor = fact.anchor;
  const asset = anchor.asset_id ? model.assetById.get(anchor.asset_id) : undefined;
  const space = model.spaceById.get(anchor.space_id);
  const connector = anchor.element_id ? model.connectorById.get(anchor.element_id) : undefined;
  const room = space?.name || model.connectorBySpace.get(anchor.space_id)?.name || "this room";
  if (asset) return `${asset.name} · ${room}`;
  if (connector) return connector.name || (connector.kind === "lift" ? "Lift" : "Stairs");
  if (anchor.element_id && model.openingById.has(anchor.element_id)) return `Door · ${room}`;
  return room;
}

/** Facts whose place a step line names (room or thing name in the line), plus the destination's on the last step:
 * the quiet line in the walk sheet. Longest names first, so "Hall A2" wins over "Hall A". */
export function factsForStep(model: BuildingModel, facts: readonly Fact[], line: string, destination?: string | null, last = false): Fact[] {
  const text = line.toLowerCase();
  return pinFacts(facts).filter((fact) => {
    if (last && destination && fact.anchor.space_id === destination) return true;
    const names = [model.spaceById.get(fact.anchor.space_id)?.name, fact.anchor.asset_id ? model.assetById.get(fact.anchor.asset_id)?.name : undefined];
    return names.some((name) => !!name && name.length >= 3 && text.includes(name.toLowerCase()));
  });
}
