// Shapes of Jennifer's JSON API (web/api.py, web/server.py). Only the fields the twin reads.

export type Point = [number, number];

export interface BuildingListEntry {
  key: string;
  name: string;
  split: string;
  source: string;
  floors: number | null;
}

export interface Floor {
  id: string;
  level: number;
  name: string;
  elevation_m: number;
  height_m: number;
}

export interface Space {
  id: string;
  floor_id: string;
  type: string; // room | corridor | hall | stair | lift | outdoor
  room_type: string;
  name: string;
  ref: string | null;
  polygon: Point[];
  anchor: Point;
  area_m2: number;
}

export interface Opening {
  id: string;
  floor_id: string;
  space_ids: string[];
  kind: string; // door | entrance | ...
  position: Point;
  width_m: number | null;
  step_free: boolean;
  added: boolean;
}

export interface Connector {
  id: string;
  kind: string; // stairs | lift
  name: string;
  floor_ids: string[];
  space_ids: string[];
  step_free: boolean;
}

export interface Footprint {
  width_m: number;
  depth_m: number;
  rotation_deg: number;
}

export interface Asset {
  id: string;
  name: string;
  type: string;
  category: string | null; // furniture | equipment | fixture | machine
  space_id: string;
  floor_id: string;
  position: Point;
  footprint: Footprint | null;
}

export interface RouteSegment {
  floor_id: string;
  kind: "walk" | "outside";
  points: Point[];
}

export interface FloorChange {
  connector_id: string;
  kind: string;
  name: string;
  from_floor: string;
  to_floor: string;
  from_point: Point;
  to_point: Point;
  direction: "up" | "down";
}

export interface Route {
  ok: boolean;
  error?: string;
  /** The same message for people: room names, closures named, no ids. */
  message?: string;
  start?: string;
  destination?: string;
  via?: string[];
  step_free?: boolean;
  length_m?: number;
  space_path?: string[];
  steps?: string[];
  segments?: RouteSegment[];
  floor_changes?: FloorChange[];
  floors?: string[];
  /** Set when the chat agent planned this route as an inspection round (plan_round): the stops in order. */
  round?: AgentRound;
}

export interface AgentRound {
  device_type: string;
  start: string;
  /** Exact start in the start room (the person's dot), [x, y] in model metres. */
  start_point?: [number, number] | null;
  /** One stop per device (asset_id, name, position, leg_m); older rounds have one stop per room (asset_ids only). */
  stops: AgentRoundStop[];
  return_to_start: boolean;
  back_to_start_m?: number;
  total_m?: number;
  step_free?: boolean;
}

export interface AgentRoundStop {
  space_id: string;
  asset_ids: string[];
  asset_id?: string;
  name?: string;
  /** The device's position, the end of the leg to it (destination_point). */
  position?: [number, number] | null;
  /** Metres from the stop before (or the start) to this device. */
  leg_m?: number;
}

/** One stop of a round planned by POST /api/round (plan_round's own result). */
export interface PlannedStop {
  n: number;
  room: string;
  space_id: string;
  floor: string;
  devices: string[];
  /** Metres from the stop before (or the start). */
  leg_m: number;
  asset_id?: string;
  device?: string;
  position?: [number, number] | null;
}

/** POST /api/round: plan_round for the page (same order and metres as the chat agent), drawn as state.route.round. */
export type PlannedRound =
  | {
      ok: true;
      device_type: string;
      start: string;
      stops: PlannedStop[];
      total_m: number;
      back_to_start_m?: number;
      /** Rooms no route reaches, already described for people, left out of the round. */
      unreachable?: string[];
      info: AgentRound;
      route: Route;
    }
  | { ok: false; error?: string; needs_choice?: boolean; question?: string };

export interface Position {
  space_id: string;
  floor_id: string;
  point: Point | null; // null when the position was set by room (source "said" or a click without a point)
  source: string;
}

export interface Guide {
  active: boolean;
  step_index: number;
  step_count: number;
  leg: { from_space_id: string; to_space_id: string; points: Point[]; segments: RouteSegment[] };
  target_space_id: string;
}

export interface AssetEdit {
  space_id: string;
  floor_id: string;
  position: Point;
  name: string;
  rotation_deg?: number;
  type?: string;
  category?: string;
}

export interface BuildingState {
  closed: string[];
  added_doors: { id: string; floor_id: string; space_ids: string[]; position: Point; step_free: boolean }[];
  route: Route | null;
  position: Position | null;
  guide: Guide | null;
  added_assets?: Record<string, AssetEdit>;
  moved_assets?: Record<string, AssetEdit>;
  removed_assets?: string[];
  removed_openings?: string[];
  widened_openings?: Record<string, number>;
}

export interface Building {
  key: string;
  name: string;
  source: string | null;
  floors: Floor[];
  spaces: Space[];
  openings: Opening[];
  connectors: Connector[];
  assets: Asset[];
  state: BuildingState;
}

export interface Located {
  asset_id: string;
  space_id: string;
  space_name: string;
  floor_level: number;
}

export interface ChatContext {
  space_id?: string;
  asset_id?: string;
  point?: Point;
  floor_id?: string;
  here?: { space_id: string; point?: Point; floor_id?: string } | { clear: true };
}

export interface ChatReply {
  reply: string;
  backend: string | null;
  error?: string;
  state?: BuildingState;
  located?: Located[];
  selection_ignored?: string;
  here_ignored?: string;
  here_note?: string;
  opened?: string;
  stale?: boolean;
}

export interface Status {
  chat_available: boolean;
  chat_backend: string;
  speech_available: boolean;
}
