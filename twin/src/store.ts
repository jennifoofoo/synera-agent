// One state for both experiences (planner and worker). Every fact comes from the API; this only remembers it.

import { create } from "zustand";
import { api } from "./api/client";
import type { Building, BuildingListEntry, BuildingState, ChatContext, ChatReply, Located, Point, Route } from "./api/types";
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

// ===== Campus hook (twin-campus session): set by campus/campusStore, null without a campus.
export interface CampusHook {
  /** "Route here" while "You are here" is in another campus building: routes across buildings, true if handled. */
  routeHere: (destinationSpaceId: string) => Promise<boolean>;
  /** Clearing the route on screen clears the whole campus route; true if there was one. */
  clearRoute: () => boolean;
  /** One step back inside the campus (tapped link -> site, building -> site); true if it went back. */
  back: () => boolean;
  /** Label for that step, or null when the campus has nothing to go back to. */
  backLabel: () => string | null;
  /** Name of the building of "You are here" when it is another campus building than the one on screen, else null. */
  hereName: () => string | null;
}

export interface ChatMessage {
  id: number;
  role: "user" | "agent";
  text: string;
  located?: Located[];
  note?: string;
  /** This reply drew a new route (the card then shows the one-line route summary, the text behind "Steps"). */
  route?: boolean;
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
  /** Width in px of UI covering the right edge (planner side sheet); the camera frames left of it. */
  rightInset: number;
  /** Height in px of UI covering the top (phone directions sheet); the camera frames below it. */
  topInset: number;
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
  /** "I'm here" set on screen, not yet told to the server: it travels as context.here with the next chat message. */
  pendingHere: { space_id: string; floor_id: string; point?: Point | null } | null;
  /** "I'm here" without the agent: the position is set at once on screen, the server learns it with the next message. */
  setHere: (here: { space_id: string; floor_id: string; point?: Point | null }) => void;
  /** True while the "You are here" dot is dragged: camera gestures are off (set by scene/HerePin). */
  dragLock: boolean;
  setDragLock: (on: boolean) => void;
  campusHook: CampusHook | null;
  /** A campus route is shown: the route on screen is one leg of it (the campus card shows the legs). */
  campusRoute: boolean;

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

  // --- walking (owner: phone session): "Start" steps through state.route.steps on the client, no agent call.
  /** Index into state.route.steps while walking; null = not walking. */
  walkStep: number | null;
  /** Bumped by "repeat" while walking: the Walk sheet speaks the current step again. */
  walkRepeat: number;
  startWalk: () => void;
  setWalkStep: (step: number) => void;
  stopWalk: () => void;

  // --- hands-free (owner: hands-free session): wake word "Hey Wanda", see handsFree.ts.
  handsFree: boolean;
  /** listening: waiting for the wake word; heard: wake word heard, taking the command; thinking: asking the agent. */
  handsFreeStatus: "listening" | "heard" | "thinking";
  /** What was heard after the wake word (interim), for the status line. */
  handsFreeHeard: string;
  /** Why hands-free switched itself off (no mic permission, unsupported browser); null otherwise. */
  handsFreeNotice: string | null;
  setHandsFree: (on: boolean) => void;

  loadBuildings: () => Promise<void>;
  openBuilding: (key: string) => Promise<void>;
  applyState: (state: BuildingState) => void;
  setProfile: (profile: Profile | null) => void;
  setViewMode: (mode: ViewMode) => void;
  setBottomInset: (px: number) => void;
  setRightInset: (px: number) => void;
  setTopInset: (px: number) => void;
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

/** The person muted "Hey Wanda" during guidance: remembered per browser, so the next guidance stays quiet too. */
export function handsFreeMuted(): boolean {
  try {
    return localStorage.getItem("twin.handsFreeMuted") === "1";
  } catch {
    return false;
  }
}
export function setHandsFreeMuted(muted: boolean): void {
  try {
    localStorage.setItem("twin.handsFreeMuted", muted ? "1" : "0");
  } catch {
    /* private mode: not remembered */
  }
}

let messageId = 0;
let cameraNonce = 0;

const prefersReducedMotion =
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** A real phone: coarse pointer AND a small screen. Only phones start in 2D and have no 3D toggle (3D is too heavy
 * there); tablets and narrow laptop windows use the phone layout but keep the 2D/3D toggle. */
export function isPhone(): boolean {
  if (typeof window === "undefined") return false;
  return !!window.matchMedia?.("(pointer: coarse)").matches && Math.min(window.innerWidth, window.innerHeight) < 600;
}

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
  viewMode: isPhone() ? "2d" : "3d",
  bottomInset: 0,
  rightInset: 0,
  topInset: 0,
  draft: false,
  offCentre: false,
  floorMode: "single", // only the chosen floor: a ghosted floor above read as a shadow copy
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
  pendingHere: null,
  dragLock: false,
  campusHook: null,
  campusRoute: false,
  directions: null,
  walkStep: null,
  walkRepeat: 0,
  handsFree: false,
  handsFreeStatus: "listening",
  handsFreeHeard: "",
  handsFreeNotice: null,

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
    set({ loading: true, error: null, selection: null, popover: null, highlights: {}, chat: [], directions: null, walkStep: null });
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
    set({ state: withPendingHere(state) });
  },

  setProfile(profile) {
    const next = profile ?? autoProfile();
    set({ profile: next, profileForced: profile !== null, ao: next === "planner", ...(next === "worker" && isPhone() ? { viewMode: "2d" as const } : {}) });
  },
  setViewMode(viewMode) {
    if (viewMode === "3d" && isPhone()) return; // phones are 2D only (narrow windows and tablets may use 3D)
    set({ viewMode });
  },
  setBottomInset(bottomInset) {
    if (bottomInset !== get().bottomInset) set({ bottomInset });
  },
  setRightInset(rightInset) {
    if (rightInset !== get().rightInset) set({ rightInset });
  },
  setTopInset(topInset) {
    if (topInset !== get().topInset) set({ topInset });
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
  setHere(here) {
    set((s) => ({
      state: s.state ? { ...s.state, position: { space_id: here.space_id, floor_id: here.floor_id, point: here.point ?? null, source: "click" } } : s.state,
      pendingHere: here,
      hereArmed: false,
      focusedFloorId: here.floor_id,
    }));
  },

  armHere(hereArmed) {
    set({ hereArmed });
  },
  setDragLock(dragLock) {
    set({ dragLock });
  },
  openDirections(to) {
    // "Your location" when known: here, or (campus) in another building, then routeDirections routes across.
    const from = get().state?.position || get().campusHook?.hereName() ? HERE : null;
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
  startWalk() {
    if (!get().state?.route?.ok) return;
    set({ walkStep: 0, selection: null, popover: null, replyShown: false });
    walkFloor(0);
    // Guidance listens for "Hey Wanda" by itself, unless the person muted it last time.
    if (!handsFreeMuted() && !get().handsFree) get().setHandsFree(true);
  },
  setWalkStep(step) {
    const steps = walkSteps();
    if (get().walkStep === null || !steps.length) return;
    const next = Math.max(0, Math.min(step, steps.length - 1));
    set({ walkStep: next });
    walkFloor(next);
  },
  stopWalk() {
    set({ walkStep: null });
    if (get().handsFree) get().setHandsFree(false);
  },
  setHandsFree(handsFree) {
    set({ handsFree, handsFreeStatus: "listening", handsFreeHeard: "", handsFreeNotice: null });
  },

  async route(start, destination, stepFree = false) {
    const key = get().buildingKey;
    if (!key) return;
    const result = await api.route(key, start, destination, stepFree);
    set({ state: withPendingHere(result.state) });
    if (result.route.ok && result.route.floors?.length) set({ focusedFloorId: result.route.floors[0] });
  },
  async clearRoute() {
    if (get().campusHook?.clearRoute()) return;
    const key = get().buildingKey;
    if (!key) return;
    set({ state: withPendingHere((await api.clearRoute(key)).state) });
  },
  async setClosed(element, closed) {
    const key = get().buildingKey;
    if (!key) return;
    set({ state: withPendingHere((await api.close(key, element, closed)).state) });
  },
  async addDoor(first, second) {
    const key = get().buildingKey;
    if (!key) return;
    set({ state: withPendingHere((await api.addDoor(key, first, second)).state) });
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
    // Walking the steps (client side, see Walk): the usual words move the step, no agent call.
    const walkStep = get().walkStep;
    if (walkStep !== null) {
      const word = message.trim().toLowerCase().replace(/[.!?]+$/, "");
      if (/^(next|ok|okay|done|weiter|go on|continue|and now|und jetzt)$/.test(word)) return get().setWalkStep(walkStep + 1), null;
      if (/^(back|previous|zurück)$/.test(word)) return get().setWalkStep(walkStep - 1), null;
      if (/^(repeat|again|say again|nochmal)$/.test(word)) return set({ walkRepeat: get().walkRepeat + 1 }), null;
      if (/^(stop|end|end route|cancel|abbrechen)$/.test(word)) {
        get().stopWalk();
        await get().clearRoute();
        return null;
      }
    }
    if (/^guide me\.?$/i.test(message.trim()) && get().state?.route?.ok) {
      get().startWalk(); // the drawn route already has its steps; no agent call
      return null;
    }
    const context: ChatContext = {};
    if (opts.here) context.here = opts.here;
    else if (get().pendingHere) {
      const pending = get().pendingHere!;
      context.here = { space_id: pending.space_id, floor_id: pending.floor_id, ...(pending.point ? { point: pending.point } : {}) };
    }
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
      pendingHere: null,
    }));
    try {
      const routeBefore = routeKey(get().state?.route);
      const reply = await api.chat(buildingKey, message, hasContext ? context : undefined, voice);
      const newRoute = !!reply.state?.route?.ok && routeKey(reply.state.route) !== routeBefore;
      const note = reply.selection_ignored
        ? `I couldn't use the selection: ${reply.selection_ignored}`
        : reply.here_ignored
          ? `I couldn't use "I'm here": ${reply.here_ignored}`
          : reply.here_note;
      set((s) => ({
        chat: [...s.chat, { id: ++messageId, role: "agent", text: reply.reply, located: reply.located, note, route: newRoute }],
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
          // A stair or lift space belongs to several floors: the leg's first segment says where it starts.
          const floorId = leg.segments?.[0]?.floor_id ?? model?.spaceById.get(leg.from_space_id)?.floor_id;
          if (floorId) set({ focusedFloorId: floorId });
        } else if (reply.state.position) {
          set({ focusedFloorId: reply.state.position.floor_id });
        }
      }
      if (reply.located?.length) {
        const ids = reply.located.map((entry) => entry.asset_id);
        get().setHighlight("found", { ids, colour: "#004fab" });
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

/** "I'm here" is local until the next chat message (pendingHere): a state from another endpoint (route, close,
 * door) does not know it yet, so the position on screen is kept instead of being wiped (mobile session). */
function withPendingHere(next: BuildingState): BuildingState {
  const { pendingHere, state } = useTwin.getState();
  return pendingHere && !next.position && state?.position ? { ...next, position: state.position } : next;
}

/** Identity of a drawn route (same ends and length = same route). */
function routeKey(route: Route | null | undefined): string {
  return route?.ok ? `${route.start}|${route.destination}|${route.length_m}` : "";
}

// --- directions (owner: card session): compute the route for the open From/To, newest request wins.
let directionsRun = 0;
async function routeDirections(): Promise<void> {
  const { directions, buildingKey, state } = useTwin.getState();
  if (!directions || !buildingKey) return;
  const resolve = (place: Place | null) => (place === HERE ? (state?.position?.space_id ?? null) : place);
  const start = resolve(directions.from);
  const destination = resolve(directions.to);
  const run = ++directionsRun;
  const campus = useTwin.getState().campusHook;
  if (directions.from === HERE && !start && destination && campus) {
    // "Your location" is not in this building: the campus routes across buildings (its card shows the legs).
    if (await campus.routeHere(destination)) return;
    const now = useTwin.getState().directions;
    if (run === directionsRun && now) useTwin.setState({ directions: { ...now, from: null, editing: "from" } });
    return;
  }
  if (!start || !destination || start === destination) {
    if (state?.route) useTwin.setState({ state: withPendingHere((await api.clearRoute(buildingKey)).state) });
    return;
  }
  const result = await api.route(buildingKey, start, destination, directions.stepFree);
  if (run !== directionsRun || !useTwin.getState().directions) return; // a newer pick or a close won
  useTwin.setState({ state: withPendingHere(result.state), replyShown: false });
  if (result.route.ok && result.route.floors?.length) useTwin.setState({ focusedFloorId: result.route.floors[0] });
}

/** The steps to walk: the route's own (deterministic, from /api/route), else one line to the destination. */
/** The route's step lines without the opening "Start in X on Ground floor." (it says nothing to do; the walk begins
 * with the first real move). */
export function walkLines(steps: string[] | undefined): string[] {
  return (steps ?? []).filter((line, index, all) => !(index === 0 && all.length > 1 && /^Start (in|at) /.test(line)));
}

export function walkSteps(): string[] {
  const { state, model } = useTwin.getState();
  const route = state?.route;
  if (!route?.ok) return [];
  const steps = walkLines(route.steps);
  if (steps.length) return steps;
  const name = route.destination ? model?.spaceById.get(route.destination)?.name || route.destination : "the destination";
  return [`Go to ${name}.`];
}

/** Show the floor a step starts on: the route's floors in order, one further after each ride ("Take …"/"Use … to …"). */
function walkFloor(step: number): void {
  const route = useTwin.getState().state?.route;
  const floors = route?.floors ?? [];
  if (!floors.length) return;
  const rides = walkSteps().slice(0, step).filter((line) => /^(Take|Use) .+ to /.test(line)).length;
  useTwin.setState({ focusedFloorId: floors[Math.min(rides, floors.length - 1)] });
}

if (typeof window !== "undefined") {
  const refreshProfile = () => {
    const { profileForced } = useTwin.getState();
    if (!profileForced) {
      const next = autoProfile();
      useTwin.setState({ profile: next, ao: next === "planner", ...(isPhone() ? { viewMode: "2d" } : {}) });
    }
  };
  window.addEventListener("resize", refreshProfile);
  window.addEventListener("orientationchange", refreshProfile);
}
