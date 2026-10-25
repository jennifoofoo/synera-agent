// Place knowledge API (web/knowledge_api.py): list with history, add a note or issue from the page, undo the newest.
// Closures are not created here: they change routes, so they go through the chat (card and "yes").

import type { BuildingState, Fact, FactAnchor } from "./types";

export interface NewFact {
  kind: "note" | "issue";
  anchor: Partial<FactAnchor> & { space_id?: string };
  text: string;
  author?: string;
  photo_base64?: string;
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) }, ...init });
  const payload = (await response.json().catch(() => ({}))) as T & { error?: string };
  if (!response.ok) throw new Error(payload.error ?? `${url}: ${response.status}`);
  return payload;
}

export const factsApi = {
  /** Facts of one room; history: also resolved and expired ones, newest first. */
  list: (key: string, spaceId: string, history = false) =>
    call<{ facts: Fact[] }>(`/api/facts?key=${encodeURIComponent(key)}&space_id=${encodeURIComponent(spaceId)}${history ? "&history=1" : ""}`).then((r) => r.facts),
  create: (key: string, fact: NewFact) =>
    call<{ fact: Fact; state: BuildingState }>("/api/facts", { method: "POST", body: JSON.stringify({ building: key, source: "tap", ...fact }) }),
  undo: (key: string) => call<{ undone: Fact | null; state: BuildingState }>("/api/facts/undo", { method: "POST", body: JSON.stringify({ building: key }) }),
};

/** A camera photo, shrunk on the device before upload (long side 1600 px, JPEG): phones take 4-12 MB pictures.
 * The server shrinks again and strips EXIF; re-encoding through a canvas drops it here already. */
export async function photoAsBase64(file: File, longSide = 1600): Promise<string> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, longSide / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close?.();
    const url = canvas.toDataURL("image/jpeg", 0.85);
    return url.slice(url.indexOf(",") + 1);
  } catch {
    // createImageBitmap missing or the format unknown to the browser: send the file as it is (server checks it)
    const buffer = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let i = 0; i < buffer.length; i += 0x8000) binary += String.fromCharCode(...buffer.subarray(i, i + 0x8000));
    return btoa(binary);
  }
}
