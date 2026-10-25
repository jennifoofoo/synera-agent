// Page state of place knowledge (docs/specs/place-knowledge-page.md). The facts themselves come from the API
// (state.facts); this only remembers what the page shows: the "Notes & photos" layer (off by default, remembered
// per browser), the open pin, the facts Wanda's last reply named, the photo viewer, the undo window, the author name.

import { create } from "zustand";
import type { Fact } from "../api/types";
import type { FactPinGroup } from "../model/facts";

/** Undo is offered as long as the server allows it (2 minutes after saving). */
export const UNDO_MS = 2 * 60 * 1000;
const LAYER_KEY = "twin.notesLayer";
const AUTHOR_KEY = "twin.author";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode: not remembered */
  }
}

interface FactsState {
  layer: boolean;
  setLayer: (on: boolean) => void;
  /** The pin whose card is open (its facts at the time of the tap; the card re-reads them from state.facts). */
  pin: FactPinGroup | null;
  openPin: (pin: FactPinGroup | null) => void;
  /** Facts named by Wanda's last reply: their pins show (and glow) even with the layer off. */
  highlighted: string[];
  setHighlighted: (ids: string[]) => void;
  /** Photo viewer (full size), null = closed. */
  photo: { url: string; caption: string } | null;
  showPhoto: (photo: { url: string; caption: string } | null) => void;
  /** The fact this page just saved, for "Undo" (until `at` + UNDO_MS). */
  saved: { fact: Fact; at: number } | null;
  setSaved: (saved: { fact: Fact; at: number } | null) => void;
}

export const useFacts = create<FactsState>((set) => ({
  layer: read(LAYER_KEY) === "1",
  setLayer(layer) {
    write(LAYER_KEY, layer ? "1" : "0");
    set(layer ? { layer } : { layer, pin: null });
  },
  pin: null,
  openPin(pin) {
    set({ pin });
  },
  highlighted: [],
  setHighlighted(highlighted) {
    set({ highlighted });
  },
  photo: null,
  showPhoto(photo) {
    set({ photo });
  },
  saved: null,
  setSaved(saved) {
    set({ saved });
  },
}));

/** The name notes are signed with, asked once ("Your name for notes"); null = not asked yet. */
export function authorName(): string | null {
  const name = read(AUTHOR_KEY);
  return name && name.trim() ? name.trim() : null;
}
export function setAuthorName(name: string): string {
  const clean = name.trim().slice(0, 60) || "Technician";
  write(AUTHOR_KEY, clean);
  return clean;
}
