// Level 3: the campus (several buildings). Owner: twin-campus session. Every fact comes from Jennifer's campus
// endpoints (web/campus_api.py); this store only remembers them and switches between the site and a building.
//
// Modes: "off" (a normal building), "site" (all buildings on one map), "building" (one campus building in the normal
// building view, with a back action). A route across buildings is a list of legs (building, link, building ...);
// the leg of the building on screen is handed to the building scene as `state.route`, so the scene draws it as is.

import { create } from "zustand";
import { api } from "../api/client";
import { campusApi, type BuildingLeg, type CampusLeg, type CampusLink, type CampusRoute, type CampusView } from "../api/campus";
import type { Building, BuildingState, Route } from "../api/types";
import { useTwin } from "../store";

export type CampusMode = "off" | "site" | "building";

export interface CampusHere {
  building_id: string;
  space_id: string;
}

interface CampusStore {
  available: { key: string; name: string }[];
  view: CampusView | null;
  mode: CampusMode;
  /** building id -> its full building JSON (outlines for the site map, floors for 3D). */
  details: Record<string, Building>;
  /** Building id shown in "building" mode. */
  current: string | null;
  route: CampusRoute | null;
  /** Index into `steps(route)` of the leg on screen, null = overview. */
  step: number | null;
  /** The link tapped on the site map. */
  selectedLink: string | null;
  /** Last known "You are here" in any campus building (from that building's state.position). */
  here: CampusHere | null;
  busy: boolean;
  error: string | null;
  note: string | null;

  loadList: () => Promise<void>;
  open: (key: string) => Promise<void>;
  exit: () => void;
  enterBuilding: (buildingId: string) => Promise<void>;
  backToSite: () => void;
  selectLink: (linkId: string | null) => void;
  setLinkClosed: (linkId: string, closed: boolean) => Promise<void>;
  routeBetween: (start: string, destination: string, opts?: { startBuilding?: string; destinationBuilding?: string; stepFree?: boolean }) => Promise<void>;
  clearRoute: () => void;
  goStep: (index: number) => Promise<void>;
}

/** The legs worth a step: a building leg of 0 m that enters and leaves by the same entrance is only passed through. */
export function steps(route: CampusRoute | null): CampusLeg[] {
  if (!route?.ok || !route.legs) return [];
  return route.legs.filter(
    (leg) => leg.kind === "link" || !(leg.length_m === 0 && leg.entry_entrance && leg.entry_entrance === leg.exit_entrance),
  );
}

export function stepLabel(leg: CampusLeg): string {
  if (leg.kind === "link") return `${leg.name} ${Math.round(leg.length_m)} m`;
  return leg.building_name;
}

export function buildingOf(view: CampusView | null, id: string | null) {
  return view?.buildings.find((building) => building.id === id) ?? null;
}

export function linkOf(view: CampusView | null, id: string | null): CampusLink | null {
  return view?.links.find((link) => link.id === id) ?? null;
}

/** The building leg as the building scene's Route shape (same fields as /api/route). */
function legRoute(leg: BuildingLeg): Route {
  const floors: string[] = [];
  for (const segment of leg.segments) if (!floors.includes(segment.floor_id)) floors.push(segment.floor_id);
  return {
    ok: true,
    start: leg.rooms[0]?.id,
    destination: leg.rooms[leg.rooms.length - 1]?.id,
    length_m: leg.length_m,
    space_path: leg.rooms.map((room) => room.id),
    segments: leg.segments,
    floor_changes: leg.floor_changes,
    floors,
    steps: [],
  };
}

/** The open campus survives a reload (like the building does); wrapped because storage can be blocked. */
function storage(action: "get" | "set" | "remove", key?: string): string | null {
  try {
    if (action === "get") return localStorage.getItem("twin.campus");
    if (action === "set") localStorage.setItem("twin.campus", key!);
    else localStorage.removeItem("twin.campus");
  } catch {
    /* private mode */
  }
  return null;
}

let overlay: Route | null = null; // the leg route we put into useTwin.state, to recognise it again

function currentLeg(store: CampusStore): BuildingLeg | null {
  if (store.mode !== "building" || !store.current) return null;
  const legs = steps(store.route);
  const onScreen = store.step !== null ? legs[store.step] : undefined;
  if (onScreen?.kind === "building" && onScreen.building_id === store.current) return onScreen;
  return (legs.find((leg) => leg.kind === "building" && leg.building_id === store.current) as BuildingLeg | undefined) ?? null;
}

/** Put the leg of the building on screen into the twin's state (or take ours out again). */
function syncOverlay(focus = false) {
  const store = useCampus.getState();
  const twin = useTwin.getState();
  const building = buildingOf(store.view, store.current);
  if (!twin.state || !building || twin.buildingKey !== building.page_key) {
    if (store.mode !== "building" && overlay && twin.state?.route === overlay) {
      overlay = null;
      useTwin.setState({ state: { ...twin.state, route: null } });
    }
    return;
  }
  const leg = currentLeg(store);
  if (!leg) {
    if (overlay && twin.state.route === overlay) {
      overlay = null;
      useTwin.setState({ state: { ...twin.state, route: null } });
    }
    return;
  }
  const route = legRoute(leg);
  overlay = route;
  const patch: Partial<ReturnType<typeof useTwin.getState>> = { state: { ...twin.state, route } as BuildingState };
  if (focus && route.floors?.length) patch.focusedFloorId = route.floors[0];
  useTwin.setState(patch);
  // After the scene has the new building (and the card its height), frame the leg's rooms.
  const ids = route.space_path ?? [];
  if (focus && ids.length) setTimeout(() => useTwin.getState().requestCamera({ kind: "object", ids }), 250);
}

function campusBuildingForKey(view: CampusView | null, key: string | null) {
  return view?.buildings.find((building) => building.page_key && building.page_key === key) ?? null;
}

export const useCampus = create<CampusStore>((set, get) => ({
  available: [],
  view: null,
  mode: "off",
  details: {},
  current: null,
  route: null,
  step: null,
  selectedLink: null,
  here: null,
  busy: false,
  error: null,
  note: null,

  async loadList() {
    try {
      const view = await campusApi.view(useTwin.getState().buildingKey);
      set({ available: view.available, view: view.loaded ? view : get().view });
      const wanted = new URLSearchParams(location.search).get("campus") ?? storage("get");
      if (wanted && get().mode === "off" && view.available.some((entry) => entry.key === wanted)) await get().open(wanted);
    } catch {
      set({ available: [] }); // an older server without campus endpoints: no campus entries in the menu
    }
  },

  async open(key) {
    set({ busy: true, error: null, note: null, selectedLink: null });
    try {
      let view = get().view;
      if (!view?.loaded || view.key !== key) {
        const loaded = await campusApi.load(key);
        view = loaded.campus;
        set({ route: null, step: null, details: {}, note: loaded.problems ? loaded.summary : null });
      } else {
        view = await campusApi.view(useTwin.getState().buildingKey);
      }
      set({ view, mode: "site", current: null, busy: false });
      storage("set", key);
      const missing = view.buildings.filter((building) => building.page_key && !get().details[building.id]);
      const fetched = await Promise.all(missing.map((building) => api.building(building.page_key!).then((data) => [building.id, data] as const)));
      const details = { ...get().details, ...Object.fromEntries(fetched) };
      // "You are here" lives in each building's page session; remember the first one we see.
      const withPosition = view.buildings.find((building) => details[building.id]?.state.position);
      const here = get().here ?? (withPosition ? { building_id: withPosition.id, space_id: details[withPosition.id].state.position!.space_id } : null);
      set({ details, here });
      // The server remembers the page's last campus route (state.campus.route); show it again after a reload.
      const remembered = view.state?.route;
      if (!get().route && remembered?.ok) {
        const { start, destination, start_building, destination_building, step_free } = remembered.request;
        const route = await campusApi.route(start, destination, {
          startBuilding: start_building ?? undefined,
          destinationBuilding: destination_building ?? undefined,
          stepFree: step_free,
        });
        if (route.ok) set({ route, step: null });
      }
      syncOverlay();
    } catch (error) {
      set({ busy: false, error: (error as Error).message });
    }
  },

  exit() {
    storage("remove");
    set({ mode: "off", current: null, selectedLink: null, step: null });
    syncOverlay();
  },

  async enterBuilding(buildingId) {
    const building = buildingOf(get().view, buildingId);
    if (!building?.page_key) {
      set({ error: `${building?.name ?? "This building"} has no map to show.` });
      return;
    }
    set({ mode: "building", current: buildingId, selectedLink: null, error: null, note: null });
    const twin = useTwin.getState();
    if (twin.buildingKey !== building.page_key || !twin.model) await twin.openBuilding(building.page_key);
    syncOverlay(true);
    // The scene sat hidden under the site; frame the building again once it is visible (a leg frames itself).
    if (!currentLeg(get())) setTimeout(() => useTwin.getState().requestCamera({ kind: "home" }), 250);
  },

  backToSite() {
    set({ mode: "site", selectedLink: null });
    syncOverlay();
    void campusApi.view(useTwin.getState().buildingKey).then((view) => view.loaded && set({ view })).catch(() => {});
  },

  selectLink(selectedLink) {
    set({ selectedLink });
  },

  async setLinkClosed(linkId, closed) {
    set({ busy: true, error: null });
    try {
      const result = await campusApi.close(linkId, closed);
      const view = get().view;
      if (view) set({ view: { ...view, links: view.links.map((link) => (link.id === linkId ? result.link : link)), state: result.state } });
      const note = result.effect.join(" ");
      if (get().route) {
        const route = result.route ?? null;
        set({ route, step: route?.ok ? Math.min(get().step ?? 0, steps(route).length - 1) : null });
        if (route && !route.ok) set({ error: route.error ?? "No route any more." });
      }
      set({ busy: false, note: note || null });
      syncOverlay();
    } catch (error) {
      set({ busy: false, error: (error as Error).message });
    }
  },

  async routeBetween(start, destination, opts = {}) {
    set({ busy: true, error: null, note: null });
    try {
      const route = await campusApi.route(start, destination, opts);
      set({ busy: false, route, step: null, selectedLink: null });
      if (!route.ok) {
        set({ error: route.error ?? "No route." });
        return;
      }
      useTwin.getState().dismissReply();
      await get().goStep(0);
    } catch (error) {
      set({ busy: false, error: (error as Error).message });
    }
  },

  clearRoute() {
    set({ route: null, step: null, error: null });
    syncOverlay();
  },

  async goStep(index) {
    const legs = steps(get().route);
    const leg = legs[index];
    if (!leg) return;
    set({ step: index });
    if (leg.kind === "building") await get().enterBuilding(leg.building_id);
    else {
      set({ mode: "site", selectedLink: null });
      syncOverlay();
    }
  },
}));

// ---------------------------------------------------------------- glue with the twin store

// A new state from the API (a closure, a reply, a reset) replaces ours: put the leg back while it is on screen.
// Also remember "You are here" whenever a campus building reports a position.
useTwin.subscribe((twin, previous) => {
  if (twin.state === previous.state) return;
  const campus = useCampus.getState();
  if (campus.mode === "off" || !campus.view) return;
  const building = campusBuildingForKey(campus.view, twin.buildingKey);
  if (building && twin.state?.position && twin.state.position.space_id !== campus.here?.space_id) {
    useCampus.setState({ here: { building_id: building.id, space_id: twin.state.position.space_id } });
  }
  if (overlay && twin.state && twin.state.route !== overlay && campus.mode === "building" && currentLeg(campus)) {
    if (twin.state.route === null || !twin.state.route.ok) syncOverlay();
  }
});

/** Hook for the card's "Route here": a destination in this building while "You are here" is in another campus
 * building is a route across buildings. Returns false when the normal building route should run. */
export async function routeHereAcross(destinationSpaceId: string): Promise<boolean> {
  const campus = useCampus.getState();
  if (campus.mode !== "building" || !campus.current) return false;
  const twinPosition = useTwin.getState().state?.position;
  if (twinPosition && twinPosition.space_id !== destinationSpaceId) return false; // here is in this building
  const here = campus.here;
  if (!here || here.building_id === campus.current) return false;
  await campus.routeBetween(here.space_id, destinationSpaceId, { startBuilding: here.building_id, destinationBuilding: campus.current });
  return useCampus.getState().route?.ok ?? false;
}

/** Hook for the card's route close: clearing the leg on screen clears the whole campus route. */
export function clearCampusRoute(): boolean {
  const campus = useCampus.getState();
  if (!campus.route) return false;
  campus.clearRoute();
  return true;
}

function campusBack(): boolean {
  const campus = useCampus.getState();
  if (campus.mode === "site" && campus.selectedLink) campus.selectLink(null);
  else if (campus.mode === "building") campus.backToSite();
  else return false;
  return true;
}

function campusBackLabel(): string | null {
  const campus = useCampus.getState();
  if (campus.mode === "building") return `Back to ${campus.view?.name ?? "the site"}`;
  if (campus.mode === "site" && campus.selectedLink) return "Close";
  return null;
}

function campusHereName(): string | null {
  const campus = useCampus.getState();
  if (campus.mode !== "building" || !campus.here || campus.here.building_id === campus.current) return null;
  return buildingOf(campus.view, campus.here.building_id)?.name ?? null;
}

useTwin.setState({
  campusHook: { routeHere: routeHereAcross, clearRoute: clearCampusRoute, back: campusBack, backLabel: campusBackLabel, hereName: campusHereName },
});
useCampus.subscribe((campus) => {
  const on = campus.mode !== "off" && !!campus.route?.ok;
  if (useTwin.getState().campusRoute !== on) useTwin.setState({ campusRoute: on });
});
