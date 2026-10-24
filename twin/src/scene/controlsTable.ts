import { create } from "zustand";

/** The one table of camera controls. The help overlay (ui/KeyHelp.tsx) and twin/CONTROLS.md both read from it. */
export interface ControlRow {
  keys: string;
  does: string;
}

export const KEY_CONTROLS: ControlRow[] = [
  { keys: "W A S D, arrows", does: "Move over the floor (relative to the view)" },
  { keys: "Q / E", does: "Rotate left / right (3D)" },
  { keys: "R / F, + / -", does: "Zoom in / out" },
  { keys: "Shift", does: "3x faster while moving, zooming or rotating" },
  { keys: "Home, 0", does: "Reset the view" },
  { keys: "1 to 9, G", does: "Show floor 1 to 9 (G = ground floor)" },
  { keys: "T", does: "Switch between 2D and 3D" },
  { keys: "L", does: "Open or close the list" },
  { keys: "Esc", does: "Close the open panel" },
  { keys: "? or H", does: "This help" },
];

export const MOUSE_CONTROLS: ControlRow[] = [
  { keys: "Left drag, middle drag", does: "Grab the map and move it (2D and 3D)" },
  { keys: "Right drag, Ctrl or Alt + left drag", does: "Rotate (3D: also tilt, 2D: rotate only)" },
  { keys: "Wheel, trackpad pinch", does: "Zoom towards the pointer" },
  { keys: "Two-finger trackpad scroll", does: "Move the map (Alt + scroll zooms instead)" },
  { keys: "Click, double click", does: "Select a room, fly to it (3D) or zoom in (2D)" },
  { keys: "One finger / two fingers", does: "Move the map / pinch to zoom (2D: around the fingers, moving with them; 3D: twist rotates, up or down tilts)" },
];

/** Open state of the help card (a tiny store of its own, so the main store stays untouched). */
export const useKeyHelp = create<{ open: boolean; setOpen: (open: boolean) => void }>((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
}));
