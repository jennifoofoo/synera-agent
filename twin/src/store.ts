// One state for both experiences (planner and worker). Every fact comes from the API; this only remembers it.

import { create } from "zustand";
import { api } from "./api/client";
import type { Building, BuildingListEntry, BuildingState, ChatContext, ChatReply, Located, Point } from "./api/types";
import { buildModel, type BuildingModel } from "./model/model";

export type FloorMode = "stacked" | "exploded" | "single";
export type Profile = "planner" | "worker";
export type ThingsMode = "near" | "all" | "off";
export type ViewMode = "2d" | "3d";

export interface Selection {
  kind: "space" | "asset" | "point" | "opening" | "connector";
  id: string;
  floor_id: string;
  point?: Point;
  space_id?: string;
}

/** A directions end: a space id, or "here" = the current position (state.position). */
export type Place = string;
export const HERE: Place = "here";

export interface Directions {
  from: Place | null;
  to: Place | null;
  stepFree: boolean;
  /** The field a plan tap or the next typed pick fills; null = none (taps are ignored). */
  editing: "from" | "to" | null;
}

export interface Highlight {
  ids: string[];
  colour: string;
}

export interface CameraRequest {
  nonce: number;
  kind: "home" | "object" | "floor" | "point";
  ids?: string[];
  floorId?: string;
  point?: Point;
  radius?: number;
}

export interface ChatMessage {
  id: number;
  role: "user" | "agent";
  text: string;
  located?: Located[];
  note?: string;
}

interface TwinState {
  buildings: BuildingListEntry[];
  buildingKey: string | null;
  building: Building | null;
  model: BuildingModel | null;
  state: BuildingState | null;
  loading: boolean;
  error: string | null;
  chatAvailable: boolean;
  speechAvailable: boolean;

  profile: Profile;
  profileForced: boolean;
  /** 2D = orthographic plan of the focused floor, 3D = the twin. Phones (worker) are 2D only: setViewMode("3d")
   * is ignored there and the 3D/postprocessing code paths are never reached. */
  viewMode: ViewMode;
  /** Height in px of UI covering the bottom of the viewport (dock / sheet); the camera frames above it. */
  bottomInset: number;
  /** A Level 4 draft (new building from floor plans) is shown instead of the building; set by ui/newBuildingStore. */
  draft: boolean;
  /** 2D: the plan was panned away from the floor (shows the recenter button). Set by the scene. */
  offCentre: boolean;
  floorMode: FloorMode;
  focusedFloorId: string | null;
  thingsMode: ThingsMode;
  cutaway: boolean;
  ao: boolean;
  reducedMotion: boolean;

  selection: Selection | null;
  popover: { selection: Selection; screen: [number, number] } | null;
  highlights: Record<string, Highlight>;
  camera: CameraRequest;
  replyShown: boolean;

  chat: ChatMessage[];
  chatBusy: boolean;
  voiceOut: boolean;
  hereArmed: boolean;

  // --- directions (owner: card session). Google-Maps-like From/To panel: "Route" on the card opens it with To set;
  // From is "here" (state.position) when known. As soon as both ends are set the route is computed (/api/route).
  // While it is open, a room tapped in the plan fills the field being edited (never a selection card).
  directions: Directions | null;
  openDirections: (to: string) => void;
  setDirectionsFrom: (place: Place | null) => void;
  setDirectionsTo: (place: Place | null) => void;
  swapDirections: () => void;
  setDirectionsStepFree: (on: boolean) => void;
  editDirections: (field: "from" | "to" | null) => void;
  /** keepRoute: leave the drawn route (e.g. "Start" guidance); default clears it. */
  closeDirections: (keepRoute?: boolean) => void;

  loadBuildings: () => Promise<void>;
  openBuilding: (key: string) => Promise<void>;
  applyState: (state: BuildingState) => void;
  setProfile: (profile: Profile | null) => void;
  setViewMode: (mode: ViewMode) => void;
  setBottomInset: (px: number) => void;
  setFloorMode: (mode: FloorMode) => void;
  focusFloor: (floorId: string | null) => void;
  setThingsMode: (mode: ThingsMode) => void;
  toggleCutaway: () => void;
  select: (selection: Selection | null, screen?: [number, number]) => void;
  closePopover: () => void;
  setHighlight: (name: string, highlight: Highlight | null) => void;
  requestCamera: (request: Omit<CameraRequest, "nonce">) => void;
  flyTo: (id: string) => void;
  dismissReply: () => void;
  setVoiceOut: (on: boolean) => void;
  armHere: (on: boolean) => void;

  route: (start: string, destination: string, stepFree?: boolean) => Promise<void>;
  clearRoute: () => Promise<void>;
  setClosed: (element: string, closed: boolean) => Promise<void>;
  addDoor: (first: string, second: string) => Promise<void>;
  reset: () => Promise<void>;
  /** opts.here overrides the hereArmed/selection logic, e.g. { here: { clear: true } } from the "You are here" chip. */
  ask: (message: string, voice?: boolean, opts?: { here?: ChatContext["here"] }) => Promise<ChatReply | null>;
}

let messageId = 0;
let cameraNonce = 0;

const prefersReducedMotion =
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function autoProfile(): Profile {
  if (typeof window === "undefined") return "planner";
  const narrow = window.innerWidth < 1100;
  const phone = window.matchMedia?.("(pointer: coarse)").matches && Math.min(window.innerWidth, window.innerHeight) < 600;
  return narrow || phone ? "worker" : "planner";
}

export const useTwin = create<TwinState>((set, get) => ({
  buildings: [],
  buildingKey: null,
  building: null,
  model: null,
  state: null,
  loading: false,
  error: null,
  chatAvailable: false,
  speechAvailable: false,

  profile: autoProfile(),
  profileForced: false,
  viewMode: autoProfile() === "worker" ? "2d" : "3d",
  bottomInset: 0,
  draft: false,
  offCentre: false,
  floorMode: "stacked",
  focusedFloorId: null,
  thingsMode: "near",
  cutaway: true,
  ao: autoProfile() === "planner",
  reducedMotion: !!prefersReducedMotion,

  selection: null,
  popover: null,
  highlights: {},
  camera: { nonce: 0, kind: "home" },
  replyShown: false,

  chat: [],
  chatBusy: false,
  voiceOut: false,
  hereArmed: false,
  directions: null,

  async loadBuildings() {
    try {
      const [buildings, status] = await Promise.all([api.buildings(), api.status()]);
      set({ buildings, chatAvailable: status.chat_available, speechAvailable: status.speech_available });
      const wanted = new URLSearchParams(location.search).get("building") ?? localStorage.getItem("twin.building");
      const first = buildings.find((b) => b.key === wanted) ?? buildings.find((b) => b.key.includes("factory")) ?? buildings[0];
      if (first && !get().buildingKey) await get().openBuilding(first.key);
    } catch (error) {
      set({ error: `Cannot reach the API: ${(error as Error).message}` });
    }
  },

  async openBuilding(key) {
    set({ loading: true, error: null, selection: null, popover: null, highlights: {}, chat: [], directions: null });
    try {
      const building = await api.building(key);
      const model = buildModel(building);
      localStorage.setItem("twin.building", key);
      set({
        buildingKey: key,
        building,
        model,
        state: building.state,
        loading: false,
        focusedFloorId: (model.floors.find((floor) => floor.level === 0) ?? model.floors.find((floor) => floor.level > 0) ?? model.floors[0])?.id ?? null,
        camera: { nonce: ++cameraNonce, kind: "home" },
      });
    } catch (error) {
      set({ loading: false, error: (error as Error).message });
    }
  },

  applyState(state) {
    set({ state });
  },

  setProfile(profile) {
    const next = profile ?? autoProfile();
    set({ profile: next, profileForced: profile !== null, ao: next === "planner", ...(next === "worker" ? { viewMode: "2d" as const } : {}) });
  },
  setViewMode(viewMode) {
    if (viewMode === "3d" && get().profile === "worker") return; // phones are 2D only
    set({ viewMode });
  },
  setBottomInset(bottomInset) {
    if (bottomInset !== get().bottomInset) set({ bottomInset });
  },
  setFloorMode(floorMode) {
    set({ floorMode });
  },
  focusFloor(focusedFloorId) {
    set({ focusedFloorId });
  },
  setThingsMode(thingsMode) {
    set({ thingsMode });
  },
  toggleCutaway() {
    set({ cutaway: !get().cutaway });
  },
  select(selection, screen) {
    if (!selection) {
      set({ selection: null, popover: null });
      return;
    }
    set({ selection, popover: screen ? { selection, screen } : null, focusedFloorId: selection.floor_id });
  },
  closePopover() {
    set({ popover: null });
  },
  setHighlight(name, highlight) {
    const highlights = { ...get().highlights };
    if (highlight) highlights[name] = highlight;
    else delete highlights[name];
    set({ highlights });
  },
  requestCamera(request) {
    set({ camera: { ...request, nonce: ++cameraNonce } });
  },
  flyTo(id) {
    const model = get().model;
    if (!model) return;
    const floorId =
      model.spaceById.get(id)?.floor_id ?? model.assetById.get(id)?.floor_id ?? model.openingById.get(id)?.floor_id;
    const connector = model.connectorById.get(id);
    if (floorId) set({ focusedFloorId: floorId });
    else if (connector) set({ focusedFloorId: get().focusedFloorId ?? connector.floor_ids[0] });
    set({ camera: { nonce: ++cameraNonce, kind: "object", ids: [id] } });
  },
  dismissReply() {
    set({ replyShown: false });
  },
  setVoiceOut(voiceOut) {
    set({ voiceOut });
  },
  armHere(hereArmed) {
    set({ hereArmed });
  },
  openDirections(to) {
    const from = get().state?.position ? HERE : null;
    set({ directions: { from, to, stepFree: false, editing: from ? null : "from" }, selection: null, popover: null });
    void routeDirections();
  },
  setDirectionsFrom(from) {
    const d = get().directions;
    if (!d) return;
    set({ directions: { ...d, from, editing: from ? (d.to ? null : "to") : "from" } });
    void routeDirections();
  },
  setDirectionsTo(to) {
    const d = get().directions;
    if (!d) return;
    set({ directions: { ...d, to, editing: to ? (d.from ? null : "from") : "to" } });
    void routeDirections();
  },
  swapDirections() {
    const d = get().directions;
    if (!d) return;
    set({ directions: { ...d, from: d.to, to: d.from } });
    void routeDirections();
  },
  setDirectionsStepFree(stepFree) {
    const d = get().directions;
    if (!d) return;
    set({ directions: { ...d, stepFree } });
    void routeDirections();
  },
  editDirections(editing) {
    const d = get().directions;
    if (d) set({ directions: { ...d, editing } });
  },
  closeDirections(keepRoute = false) {
    if (!get().directions) return;
    set({ directions: null });
    directionsRun++;
    if (!keepRoute && get().state?.route) void get().clearRoute();
  },

  async route(start, destination, stepFree = false) {
    const key = get().buildingKey;
    if (!key) return;
    const result = await api.route(key, start, destination, stepFree);
    set({ state: result.state });
    if (result.route.ok && result.route.floors?.length) set({ focusedFloorId: result.route.floors[0] });
  },
  async clearRoute() {
    const key = get().buildingKey;
    if (!key) return;
    set({ state: (await api.clearRoute(key)).state });
  },
  async setClosed(element, closed) {
    const key = get().buildingKey;
    if (!key) return;
    set({ state: (await api.close(key, element, closed)).state });
  },
  async addDoor(first, second) {
    const key = get().buildingKey;
    if (!key) return;
    set({ state: (await api.addDoor(key, first, second)).state });
  },
  async reset() {
    const key = get().buildingKey;
    if (!key) return;
    const building = await api.reset(key);
    set({ building, model: buildModel(building), state: building.state, selection: null, popover: null, highlights: {} });
  },

  async ask(message, voice = false, opts = {}) {
    const { buildingKey, selection, hereArmed, model } = get();
    if (!buildingKey || !message.trim()) return null;
    const context: ChatContext = {};
    if (opts.here) context.here = opts.here;
    if (selection) {
      if (selection.kind === "space") context.space_id = selection.id;
      if (selection.kind === "asset") (context.asset_id = selection.id), (context.space_id = selection.space_id);
      if (selection.kind === "point") (context.space_id = selection.space_id), (context.point = selection.point);
      context.floor_id = selection.floor_id;
    }
    if (!opts.here && hereArmed && selection && (selection.kind === "space" || selection.kind === "point")) {
      context.here = { space_id: selection.kind === "space" ? selection.id : selection.space_id!, point: selection.point, floor_id: selection.floor_id };
    }
    const hasContext = Object.keys(context).length > 0;
    set((s) => ({
      chat: [...s.chat, { id: ++messageId, role: "user", text: message }],
      chatBusy: true,
      hereArmed: false,
    }));
    try {
      const reply = await api.chat(buildingKey, message, hasContext ? context : undefined, voice);
      const note = reply.selection_ignored
        ? `I couldn't use the selection: ${reply.selection_ignored}`
        : reply.here_ignored
          ? `I couldn't use "I'm here": ${reply.here_ignored}`
          : reply.here_note;
      set((s) => ({
        chat: [...s.chat, { id: ++messageId, role: "agent", text: reply.reply, located: reply.located, note }],
        chatBusy: false,
        replyShown: true,
        selection: reply.selection_ignored ? s.selection : null,
        popover: null,
      }));
      if (reply.opened) {
        await get().loadBuildings();
        await get().openBuilding(reply.opened);
        return reply;
      }
      if (reply.state) {
        set({ state: reply.state });
        if (reply.state.route?.ok && reply.state.route.floors?.length && !reply.state.guide) {
          set({ focusedFloorId: reply.state.route.floors[0] });
        }
        if (reply.state.guide?.active) {
          const leg = reply.state.guide.leg;
          const floorId = model?.spaceById.get(leg.from_space_id)?.floor_id;
          if (floorId) set({ focusedFloorId: floorId });
        } else if (reply.state.position) {
          set({ focusedFloorId: reply.state.position.floor_id });
        }
      }
      if (reply.located?.length) {
        const ids = reply.located.map((entry) => entry.asset_id);
        get().setHighlight("found", { ids, colour: "#5eead4" });
        get().flyTo(ids[0]);
      }
      return reply;
    } catch (error) {
      set((s) => ({
        chat: [...s.chat, { id: ++messageId, role: "agent", text: `The request failed: ${(error as Error).message}` }],
        chatBusy: false,
        replyShown: true,
      }));
      return null;
    }
  },
}));

// --- directions (owner: card session): compute the route for the open From/To, newest request wins.
let directionsRun = 0;
async function routeDirections(): Promise<void> {
  const { directions, buildingKey, state } = useTwin.getState();
  if (!directions || !buildingKey) return;
  const resolve = (place: Place | null) => (place === HERE ? (state?.position?.space_id ?? null) : place);
  const start = resolve(directions.from);
  const destination = resolve(directions.to);
  const run = ++directionsRun;
  if (!start || !destination || start === destination) {
    if (state?.route) useTwin.setState({ state: (await api.clearRoute(buildingKey)).state });
    return;
  }
  const result = await api.route(buildingKey, start, destination, directions.stepFree);
  if (run !== directionsRun || !useTwin.getState().directions) return; // a newer pick or a close won
  useTwin.setState({ state: result.state, replyShown: false });
  if (result.route.ok && result.route.floors?.length) useTwin.setState({ focusedFloorId: result.route.floors[0] });
}

if (typeof window !== "undefined") {
  const refreshProfile = () => {
    const { profileForced } = useTwin.getState();
    if (!profileForced) {
      const next = autoProfile();
      useTwin.setState({ profile: next, ao: next === "planner", ...(next === "worker" ? { viewMode: "2d" } : {}) });
    }
  };
  window.addEventListener("resize", refreshProfile);
  window.addEventListener("orientationchange", refreshProfile);
}
