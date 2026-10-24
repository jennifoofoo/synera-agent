// Level 4 (new building from floor plans): shapes and calls of web/level4_api.py. Only the fields the twin reads.

import type { Building } from "./types";

export type Along = "building_width" | "room" | "door";

export interface Level4FloorIn {
  upload_id: string;
  level: number;
  known_length_m?: number;
  scale_bar?: boolean;
  along?: Along;
}

export interface Level4Status {
  state: "idle" | "running" | "done" | "error";
  message?: string;
  floor_index?: number;
  floors_total?: number;
  seconds?: number;
  errors?: { level: number; error: string }[];
  has_draft: boolean;
  version: number;
  saved: string | null;
}

export interface Level4Finding {
  level: "error" | "warning";
  code: string;
  message: string;
  items: string[];
}

export interface Level4Preview {
  draft: Building | null;
  version?: number;
  suspect_spaces?: string[];
  suspect_openings?: string[];
  findings?: Level4Finding[];
  summary?: string;
  problems?: string;
  can_save?: boolean;
  scales?: { level: number; note: string }[];
  status: Level4Status;
  done?: string; // after a fix: what was changed
}

export type Level4Card = Record<string, unknown> & { "can be saved"?: boolean; "problems found"?: string };

export interface Level4Saved {
  saved?: boolean;
  key?: string;
  [field: string]: unknown;
}

export interface Level4Fix {
  action: "add_door" | "remove_door" | "set_room_type" | "set_scale";
  ref?: string;
  other_ref?: string;
  room_type?: string;
  known_length_m?: number;
  along?: Along;
  level?: number;
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, headers: { Accept: "application/json", ...(init?.headers ?? {}) } });
  } catch {
    throw new Error("The server cannot be reached.");
  }
  const payload = (await response.json().catch(() => ({}))) as T & { error?: string };
  if (!response.ok) {
    if (response.status === 413) throw new Error("The image is larger than 10 MB.");
    throw new Error(payload.error ?? `The server answered ${response.status}.`);
  }
  return payload;
}

const post = <T>(url: string, body: unknown) =>
  call<T>(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const level4 = {
  upload: (image: Blob) =>
    call<{ upload_id: string; width: number; height: number }>("/api/level4/upload", {
      method: "POST",
      headers: { "Content-Type": image.type },
      body: image,
    }),
  build: (floors: Level4FloorIn[], name?: string) => post<Level4Status>("/api/level4/build", { floors, name }),
  status: () => call<Level4Status>("/api/level4/status"),
  preview: () => call<Level4Preview>("/api/level4/preview"),
  fix: (fix: Level4Fix) => post<Level4Preview>("/api/level4/fix", fix),
  card: () => post<{ card: Level4Card; version: number }>("/api/level4/card", {}),
  save: (answer: "yes" | "no", acceptProblems = false) =>
    post<Level4Saved>("/api/level4/save", { answer, accept_problems: acceptProblems }),
  reset: () => post<Level4Status>("/api/level4/reset", {}),
};
