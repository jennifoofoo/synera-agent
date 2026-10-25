// Place knowledge on the page: what a fact is and where it is kept (contract: docs/specs/place-knowledge.md).
// A fact (note, issue, closure) hangs on a room, machine or element and is valid from/to; nothing is deleted, facts
// are resolved or expire. Two storages behind one interface, picked per building: the server (/api/facts) when it
// answers, else this browser's IndexedDB ("Saved on this device").

import type { Point } from "../api/types";

export type FactKind = "note" | "issue" | "closure";
export type FactStatus = "open" | "resolved" | "expired";

export interface FactAnchor {
  space_id: string;
  asset_id: string | null;
  element_id: string | null;
  point: Point | null;
  floor_id: string;
}

/** The server's fact (the spec's shape); `photo` is a URL the page can show (server path or local object URL). */
export interface Fact {
  id: string;
  kind: FactKind;
  anchor: FactAnchor;
  text: string;
  valid_from: string;
  valid_to: string | null;
  status: FactStatus;
  resolved_by?: string | null;
  author: string | null;
  /** Normalised author ("klaus"), set by the server. */
  person_id?: string | null;
  related?: string[];
  photo: string | null;
  created_at: string;
  source?: string;
}

/** What a save or undo returns: the fact and, from the server, the building state after it (`{fact, state}`). */
export interface Saved {
  fact: Fact;
  state?: unknown;
}

/** Older name kept for the notes UI. */
export type Note = Fact;

export interface NewFact {
  kind: "note" | "issue";
  anchor: FactAnchor;
  text: string;
  valid_to?: string | null;
  author?: string | null;
  /** Downscaled JPEG (downscalePhoto). */
  photo?: Blob | null;
  source?: "text" | "voice" | "tap";
}

export interface FactsStorage {
  readonly kind: "local" | "server";
  /** Where the facts are kept, for the honest label in the UI. */
  readonly label: string;
  /** Every fact of the building, current and past (history), newest first. */
  list(buildingKey: string): Promise<Fact[]>;
  add(buildingKey: string, input: NewFact): Promise<Saved>;
  /** Mark done: the fact gets valid_to = now and status resolved (local only; the server resolves through the chat). */
  resolve?(buildingKey: string, id: string, author: string | null): Promise<Fact>;
  /** Undo right after creating (typos); the only real delete. Returns the new state from the server, if any. */
  undo?(buildingKey: string, id: string): Promise<{ state?: unknown; undoneId?: string } | void>;
}

/** Valid now: started, not ended, not resolved (spec "jetzt gültig"). */
export function isCurrent(fact: Fact, now = Date.now()): boolean {
  if (fact.status === "resolved" || fact.status === "expired") return false;
  if (Date.parse(fact.valid_from) > now) return false;
  return !fact.valid_to || Date.parse(fact.valid_to) > now;
}

export function newestFirst(a: Fact, b: Fact): number {
  return Date.parse(b.created_at) - Date.parse(a.created_at);
}

// ---- IndexedDB (local) ----

const DB_NAME = "twin-facts";
const STORE = "facts";

interface StoredFact extends Omit<Fact, "photo"> {
  building: string;
  photoBlob: Blob | null;
}

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export class LocalFacts implements FactsStorage {
  readonly kind = "local" as const;
  readonly label = "Saved on this device";
  private db: Promise<IDBDatabase> | null = null;
  private urls = new Map<string, string>();

  private open(): Promise<IDBDatabase> {
    this.db ??= new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "id" }).createIndex("building", "building");
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return this.db;
  }

  private toFact(stored: StoredFact): Fact {
    const { building: _building, photoBlob, ...fact } = stored;
    let photo: string | null = null;
    if (photoBlob) {
      photo = this.urls.get(stored.id) ?? URL.createObjectURL(photoBlob);
      this.urls.set(stored.id, photo);
    }
    return { ...fact, photo };
  }

  private async get(id: string): Promise<StoredFact | undefined> {
    const db = await this.open();
    return request(db.transaction(STORE).objectStore(STORE).get(id) as IDBRequest<StoredFact | undefined>);
  }

  private async put(stored: StoredFact): Promise<void> {
    const db = await this.open();
    await request(db.transaction(STORE, "readwrite").objectStore(STORE).put(stored));
  }

  async list(buildingKey: string): Promise<Fact[]> {
    const db = await this.open();
    const index = db.transaction(STORE).objectStore(STORE).index("building");
    const stored = await request(index.getAll(buildingKey) as IDBRequest<StoredFact[]>);
    return stored.map((s) => this.toFact(s)).sort(newestFirst);
  }

  async add(buildingKey: string, input: NewFact): Promise<Saved> {
    const now = new Date().toISOString();
    const stored: StoredFact = {
      id: newFactId(),
      building: buildingKey,
      kind: input.kind,
      anchor: input.anchor,
      text: input.text,
      valid_from: now,
      valid_to: input.valid_to ?? null,
      status: "open",
      resolved_by: null,
      author: input.author ?? null,
      created_at: now,
      source: input.source ?? "text",
      photoBlob: input.photo ?? null,
    };
    await this.put(stored);
    return { fact: this.toFact(stored) };
  }

  async resolve(_buildingKey: string, id: string): Promise<Fact> {
    const stored = await this.get(id);
    if (!stored) throw new Error("That note is gone.");
    const next = { ...stored, status: "resolved" as const, valid_to: new Date().toISOString() };
    await this.put(next);
    return this.toFact(next);
  }

  async undo(_buildingKey: string, id: string): Promise<void> {
    const db = await this.open();
    await request(db.transaction(STORE, "readwrite").objectStore(STORE).delete(id));
    const url = this.urls.get(id);
    if (url) URL.revokeObjectURL(url);
    this.urls.delete(id);
  }
}

/** Fallback when IndexedDB is unavailable (some private modes): kept until the tab closes. */
export class MemoryFacts implements FactsStorage {
  readonly kind = "local" as const;
  readonly label = "Kept until this tab closes";
  private facts = new Map<string, Fact[]>();
  async list(buildingKey: string): Promise<Fact[]> {
    return [...(this.facts.get(buildingKey) ?? [])].sort(newestFirst);
  }
  async add(buildingKey: string, input: NewFact): Promise<Saved> {
    const now = new Date().toISOString();
    const fact: Fact = {
      id: newFactId(),
      kind: input.kind,
      anchor: input.anchor,
      text: input.text,
      valid_from: now,
      valid_to: input.valid_to ?? null,
      status: "open",
      author: input.author ?? null,
      photo: input.photo ? URL.createObjectURL(input.photo) : null,
      created_at: now,
      source: input.source ?? "text",
    };
    this.facts.set(buildingKey, [...(this.facts.get(buildingKey) ?? []), fact]);
    return { fact };
  }
  async resolve(buildingKey: string, id: string): Promise<Fact> {
    const list = this.facts.get(buildingKey) ?? [];
    const fact = list.find((f) => f.id === id);
    if (!fact) throw new Error("That note is gone.");
    const next = { ...fact, status: "resolved" as const, valid_to: new Date().toISOString() };
    this.facts.set(buildingKey, list.map((f) => (f.id === id ? next : f)));
    return next;
  }
  async undo(buildingKey: string, id: string): Promise<void> {
    this.facts.set(buildingKey, (this.facts.get(buildingKey) ?? []).filter((f) => f.id !== id));
  }
}

// ---- server (/api/facts, Jennifer's web/knowledge_api.py) ----

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).replace(/^data:[^,]*,/, ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

export class ServerFacts implements FactsStorage {
  readonly kind = "server" as const;
  readonly label = "Saved in the building";

  async list(buildingKey: string): Promise<Fact[]> {
    const response = await fetch(`/api/facts?key=${encodeURIComponent(buildingKey)}&history=1`);
    if (!response.ok) throw new Error(`facts ${response.status}`);
    const body = (await response.json()) as { facts?: Fact[] };
    return (body.facts ?? []).sort(newestFirst);
  }

  async add(buildingKey: string, input: NewFact): Promise<Saved> {
    const body = {
      key: buildingKey,
      kind: input.kind,
      anchor: input.anchor,
      text: input.text,
      ...(input.valid_to ? { valid_to: input.valid_to } : {}),
      ...(input.author ? { author: input.author } : {}),
      ...(input.photo ? { photo_base64: await blobToBase64(input.photo) } : {}),
      source: input.source ?? "text",
    };
    const reply = await postJson("/api/facts", body);
    return "fact" in reply ? { fact: reply.fact as Fact, state: reply.state } : { fact: reply as unknown as Fact };
  }

  /** POST /api/facts/undo removes the building's newest fact if it is younger than 2 minutes; refuse when that is
   * not this note (someone saved after it, or it is too old), so undo never removes another person's note. */
  async undo(buildingKey: string, id: string): Promise<{ state?: unknown; undoneId?: string }> {
    // Fetched again right before: the server undoes the newest fact, whoever saved it.
    const newest = (await this.list(buildingKey))[0];
    if (newest?.id !== id) throw new Error("Only the newest note can be undone.");
    const reply = await postJson("/api/facts/undo", { key: buildingKey });
    if (!reply.undone) throw new Error("Too late to undo.");
    const undone = reply.undone as { id?: unknown };
    return { state: reply.state, undoneId: typeof undone.id === "string" ? undone.id : undefined };
  }
}

async function postJson(url: string, body: unknown): Promise<Record<string, unknown>> {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) throw new Error(`facts ${response.status}`);
  return (await response.json()) as Record<string, unknown>;
}

/** The server when GET /api/facts answers 200 with a facts list, else IndexedDB (or memory). */
export async function pickFactsStorage(buildingKey: string): Promise<FactsStorage> {
  try {
    const response = await fetch(`/api/facts?key=${encodeURIComponent(buildingKey)}`);
    if (response.ok) {
      const body = (await response.json()) as { facts?: unknown };
      if (Array.isArray(body.facts)) return serverFacts;
    }
  } catch {
    /* offline or no server: local */
  }
  return localFacts;
}

const localFacts: FactsStorage = typeof indexedDB !== "undefined" ? new LocalFacts() : new MemoryFacts();
const serverFacts = new ServerFacts();

// ---- photos ----

export const PHOTO_MAX_PX = 1280;
export const PHOTO_MAX_BYTES = 450_000;
/** Larger files are refused before decoding (a phone photo is 2 to 8 MB). */
export const PHOTO_INPUT_MAX_BYTES = 25_000_000;

function toJpeg(canvas: HTMLCanvasElement, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
}

/** A camera photo as a JPEG of at most PHOTO_MAX_PX on the long side and at most PHOTO_MAX_BYTES. Re-encoding through
 * a canvas also drops EXIF and location data. */
export async function downscalePhoto(file: Blob): Promise<Blob> {
  if (!file.type.startsWith("image/")) throw new Error("That file is not a photo.");
  if (file.size > PHOTO_INPUT_MAX_BYTES) throw new Error("That photo is too large.");
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" } as ImageBitmapOptions);
  let scale = Math.min(1, PHOTO_MAX_PX / Math.max(bitmap.width, bitmap.height));
  for (let attempt = 0; attempt < 4; attempt++) {
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    for (const quality of [0.82, 0.7, 0.58]) {
      const blob = await toJpeg(canvas, quality);
      if (blob && blob.size <= PHOTO_MAX_BYTES) {
        bitmap.close();
        return blob;
      }
    }
    scale *= 0.75;
  }
  bitmap.close();
  throw new Error("Could not make that photo small enough.");
}

export function newFactId(): string {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `f-${random}`;
}

// ---- words ----

/** "today 14:12", "yesterday 14:12", "Mon 14:12", "12 Oct 14:12" (also "tomorrow 18:00" for a valid_to). */
export function whenLabel(at: number | string, now = Date.now()): string {
  const date = new Date(at);
  const time = date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((day(new Date(now)) - day(date)) / 86_400_000);
  if (days === 0) return `today ${time}`;
  if (days === 1) return `yesterday ${time}`;
  if (days === -1) return `tomorrow ${time}`;
  if (days > 1 && days < 7) return `${date.toLocaleDateString("en-GB", { weekday: "short" })} ${time}`;
  return `${date.toLocaleDateString("en-GB", { day: "numeric", month: "short" })} ${time}`;
}

/** "since today 8:10, by Klaus" (spec: Wanda names age and author). */
export function sinceLabel(fact: Fact, withAuthor = true, now = Date.now()): string {
  const by = withAuthor && fact.author ? `, by ${fact.author}` : "";
  const until = fact.valid_to && isCurrent(fact, now) ? ` · until ${whenLabel(fact.valid_to, now)}` : "";
  return `since ${whenLabel(fact.valid_from, now)}${by}${until}`;
}

/** For past facts in the history list: "resolved today 12:40" / "expired yesterday 18:00". */
export function endedLabel(fact: Fact, now = Date.now()): string {
  const when = fact.valid_to ? ` ${whenLabel(fact.valid_to, now)}` : "";
  return fact.status === "resolved" ? `resolved${when}` : `ended${when}`;
}

export function clockLabel(at: number | string): string {
  return new Date(at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

/** "4 min", "1 h 05 min". */
export function durationLabel(ms: number): string {
  const minutes = Math.max(0, Math.round(ms / 60_000));
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}
