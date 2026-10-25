import type { Building, BuildingListEntry, BuildingState, ChatContext, ChatReply, PlannedRound, Route, Status } from "./types";

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return (await response.json()) as T;
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

/** Exact route ends inside the start/destination rooms (e.g. the "You are here" dot); the server checks them. */
export interface RoutePoints {
  start_point?: { x: number; y: number; floor_id?: string };
  destination_point?: { x: number; y: number; floor_id?: string };
}

export const api = {
  status: () => getJson<Status>("/api/status"),
  buildings: () => getJson<{ buildings: BuildingListEntry[] }>("/api/buildings").then((r) => r.buildings),
  building: (key: string) => getJson<Building>(`/api/building?key=${encodeURIComponent(key)}`),
  route: (building: string, start: string, destination: string, stepFree = false, via: string[] = [], points: RoutePoints = {}) =>
    postJson<{ route: Route; state: BuildingState }>("/api/route", {
      building,
      start,
      destination,
      step_free: stepFree,
      via,
      ...points,
    }),
  /** Plan an inspection round on the server (plan_round) and draw it; area: "Whole building", a floor, "Hall A", ... */
  round: (
    building: string,
    type: string,
    options: { area?: string; start?: string | null; startPoint?: [number, number] | null; returnToStart?: boolean; stepFree?: boolean } = {},
  ) =>
    postJson<{ round: PlannedRound; state: BuildingState }>("/api/round", {
      building,
      type,
      ...(options.area ? { area: options.area } : {}),
      ...(options.start ? { start: options.start } : {}),
      ...(options.start && options.startPoint ? { start_point: { x: options.startPoint[0], y: options.startPoint[1] } } : {}),
      return_to_start: !!options.returnToStart,
      step_free: !!options.stepFree,
    }),
  clearRoute: (building: string) => postJson<{ state: BuildingState }>("/api/route/clear", { building }),
  setStepFree: (building: string, enabled: boolean) =>
    postJson<{ state: BuildingState }>("/api/step_free", { building, enabled }),
  close: (building: string, element: string, closed: boolean) =>
    postJson<{ element: string; closed: boolean; state: BuildingState }>("/api/close", { building, element, closed }),
  addDoor: (building: string, first: string, second: string, stepFree = true) =>
    postJson<{ state: BuildingState }>("/api/door", { building, first, second, step_free: stepFree }),
  reset: (building: string) => postJson<Building>("/api/reset", { building }),
  chat: (building: string, message: string, context?: ChatContext, voice?: boolean) =>
    postJson<ChatReply>("/api/chat", {
      building,
      message,
      ...(context ? { context } : {}),
      ...(voice ? { voice: true } : {}),
    }),
  speak: async (text: string, lang = "en"): Promise<Blob | null> => {
    const response = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, lang }),
    });
    if (!response.ok) return null;
    return response.blob();
  },
};
