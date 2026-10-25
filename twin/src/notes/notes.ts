// Place notes ("the knowledge stays in the building"): what a note is and where it is kept.
// Frontend only for now: notes live in this browser's IndexedDB, per building key, and the UI says "saved on this
// device". Everything goes through NotesStorage, so a server API (POST/GET /api/notes) can replace it later without
// touching the UI: write a class with the same three methods and pass it to setNotesStorage().

import type { Point } from "../api/types";

export interface Note {
  id: string;
  buildingKey: string;
  /** The room the note belongs to (for an asset note: the asset's room). */
  spaceId: string;
  floorId: string;
  assetId: string | null;
  point: Point | null;
  text: string;
  author: string;
  /** Epoch milliseconds. */
  createdAt: number;
  /** Downscaled JPEG (at most PHOTO_MAX_PX on the long side, at most PHOTO_MAX_BYTES), or null. */
  photo: Blob | null;
}

export interface NotesStorage {
  /** Where the notes are kept, for the honest label in the UI. */
  readonly label: string;
  list(buildingKey: string): Promise<Note[]>;
  add(note: Note): Promise<void>;
  remove(buildingKey: string, id: string): Promise<void>;
}

// ---- IndexedDB (default) ----

const DB_NAME = "twin-notes";
const STORE = "notes";

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export class IndexedDbNotes implements NotesStorage {
  readonly label = "Saved on this device";
  private db: Promise<IDBDatabase> | null = null;

  private open(): Promise<IDBDatabase> {
    this.db ??= new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        const store = req.result.createObjectStore(STORE, { keyPath: "id" });
        store.createIndex("buildingKey", "buildingKey");
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return this.db;
  }

  async list(buildingKey: string): Promise<Note[]> {
    const db = await this.open();
    const index = db.transaction(STORE).objectStore(STORE).index("buildingKey");
    const notes = await request(index.getAll(buildingKey) as IDBRequest<Note[]>);
    return notes.sort((a, b) => a.createdAt - b.createdAt);
  }

  async add(note: Note): Promise<void> {
    const db = await this.open();
    const tx = db.transaction(STORE, "readwrite");
    await request(tx.objectStore(STORE).put(note));
  }

  async remove(_buildingKey: string, id: string): Promise<void> {
    const db = await this.open();
    const tx = db.transaction(STORE, "readwrite");
    await request(tx.objectStore(STORE).delete(id));
  }
}

/** Fallback when IndexedDB is unavailable (private mode in some browsers): kept until the tab closes. */
export class MemoryNotes implements NotesStorage {
  readonly label = "Kept until this tab closes";
  private notes: Note[] = [];
  async list(buildingKey: string): Promise<Note[]> {
    return this.notes.filter((note) => note.buildingKey === buildingKey);
  }
  async add(note: Note): Promise<void> {
    this.notes = [...this.notes.filter((n) => n.id !== note.id), note];
  }
  async remove(_buildingKey: string, id: string): Promise<void> {
    this.notes = this.notes.filter((note) => note.id !== id);
  }
}

let storage: NotesStorage = typeof indexedDB !== "undefined" ? new IndexedDbNotes() : new MemoryNotes();

export function notesStorage(): NotesStorage {
  return storage;
}

/** Swap the storage (e.g. a server API later). The notes store reloads on the next building change or reload(). */
export function setNotesStorage(next: NotesStorage): void {
  storage = next;
}

// ---- photos ----

export const PHOTO_MAX_PX = 1280;
export const PHOTO_MAX_BYTES = 450_000;
/** Larger files are refused before decoding (a phone photo is 2 to 8 MB). */
export const PHOTO_INPUT_MAX_BYTES = 25_000_000;

function toJpeg(canvas: HTMLCanvasElement, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
}

/** A camera photo as a JPEG of at most PHOTO_MAX_PX on the long side and at most PHOTO_MAX_BYTES. */
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

export function newNoteId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `n-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// ---- words ----

/** "today 14:12", "yesterday 14:12", "Mon 14:12", "12 Oct 14:12". */
export function whenLabel(at: number, now = Date.now()): string {
  const date = new Date(at);
  const time = date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((day(new Date(now)) - day(date)) / 86_400_000);
  if (days <= 0) return `today ${time}`;
  if (days === 1) return `yesterday ${time}`;
  if (days < 7) return `${date.toLocaleDateString("en-GB", { weekday: "short" })} ${time}`;
  return `${date.toLocaleDateString("en-GB", { day: "numeric", month: "short" })} ${time}`;
}

export function clockLabel(at: number): string {
  return new Date(at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

/** "4 min", "1 h 05 min". */
export function durationLabel(ms: number): string {
  const minutes = Math.max(0, Math.round(ms / 60_000));
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}
