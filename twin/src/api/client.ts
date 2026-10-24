import type { Building, BuildingListEntry, BuildingState, ChatContext, ChatReply, Route, Status } from "./types";

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
  clearRoute: (building: string) => postJson<{ state: BuildingState }>("/api/route/clear", { building }),
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
