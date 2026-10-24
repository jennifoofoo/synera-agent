// Level 3 campus: shapes and calls of Jennifer's campus endpoints (web/campus_api.py, docs/specs/level3-campus.md).
// Only the fields the twin reads. Campus metres: x east, y north (same as building metres).

import type { Floor, FloorChange, Point, RouteSegment } from "./types";

export interface CampusEntrance {
  id: string;
  name: string;
  room: string;
  space_id: string;
  floor_id: string | null;
  position: Point;
  world_position: Point | null;
  step_free: boolean;
}

export interface CampusBuilding {
  id: string;
  name: string;
  map_loaded: boolean;
  page_key: string | null;
  active: boolean;
  floors: Floor[];
  floor_count: number;
  origin: Point | null;
  rotation_deg: number;
  world_center: Point | null;
  entrances: CampusEntrance[];
}

export interface LinkEnd {
  building_id: string;
  entrance_id: string;
  point: Point | null;
  world_point: Point | null;
}

export interface CampusLink {
  id: string;
  kind: string; // walkway | bridge | tunnel | path | ...
  name: string;
  from: LinkEnd;
  to: LinkEnd;
  level_delta: number;
  length_m: number;
  length_estimated: boolean;
  width_m: number | null;
  step_free: boolean;
  closed: boolean;
}

export interface CampusFinding {
  level: string;
  code: string;
  message: string;
  items: string[];
}

export interface CampusRouteState {
  request: { start: string; destination: string; start_building: string | null; destination_building: string | null; step_free: boolean };
  ok: boolean;
  error?: string;
  length_m?: number;
  buildings?: string[];
  links_used?: string[];
}

export interface CampusState {
  loaded: boolean;
  key: string | null;
  name: string | null;
  route: CampusRouteState | null;
  closed_links: string[];
}

export interface CampusView {
  loaded: boolean;
  available: { key: string; name: string }[];
  key?: string;
  name?: string;
  buildings: CampusBuilding[];
  links: CampusLink[];
  findings: CampusFinding[];
  state?: CampusState;
}

export interface BuildingLeg {
  kind: "building";
  building_id: string;
  building_name: string;
  length_m: number;
  entry_entrance: string | null;
  exit_entrance: string | null;
  rooms: { id: string; name: string; floor_id: string }[];
  segments: RouteSegment[];
  floor_changes: FloorChange[];
  points: Point[];
  world_points: Point[] | null;
}

export interface LinkLeg {
  kind: "link";
  link_id: string;
  link_kind: string;
  name: string;
  length_m: number;
  step_free: boolean;
  level_delta: number;
  from: LinkEnd;
  to: LinkEnd;
}

export type CampusLeg = BuildingLeg | LinkLeg;

export interface CampusCandidate {
  building_id: string;
  building: string;
  space_id: string;
  name: string;
  floor: string;
}

export interface CampusRoute {
  ok: boolean;
  ambiguous?: boolean;
  error?: string;
  candidates?: CampusCandidate[];
  length_m?: number;
  step_free?: boolean;
  buildings?: string[];
  building_names?: string[];
  links_used?: string[];
  steps?: string[];
  legs?: CampusLeg[];
  state?: CampusState;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  const payload = (await response.json().catch(() => ({}))) as T & { error?: string };
  if (!response.ok) throw new Error(payload.error ?? `${url}: ${response.status}`);
  return payload;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  const payload = (await response.json().catch(() => ({}))) as T & { error?: string };
  if (!response.ok) throw new Error(payload.error ?? `${url}: ${response.status}`);
  return payload;
}

export const campusApi = {
  /** `key` = the building the page shows (marks it `active`); the server keeps no "active building". */
  view: (buildingKey?: string | null) =>
    getJson<CampusView>(`/api/campus${buildingKey ? `?key=${encodeURIComponent(buildingKey)}` : ""}`),
  load: (key: string) => postJson<{ loaded: boolean; key: string; problems: number; summary: string; campus: CampusView }>("/api/campus/load", { key }),
  route: (start: string, destination: string, opts: { startBuilding?: string; destinationBuilding?: string; stepFree?: boolean } = {}) =>
    postJson<CampusRoute>("/api/campus/route", {
      start,
      destination,
      ...(opts.startBuilding ? { start_building: opts.startBuilding } : {}),
      ...(opts.destinationBuilding ? { destination_building: opts.destinationBuilding } : {}),
      step_free: !!opts.stepFree,
    }),
  close: (linkId: string, closed: boolean) =>
    postJson<{ link: CampusLink; effect: string[]; saved: boolean; state: CampusState; route?: CampusRoute }>("/api/campus/close", {
      link_id: linkId,
      closed,
    }),
};
