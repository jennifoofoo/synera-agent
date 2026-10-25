// When which map label shows (docs/specs/label-rules.md). Pure rules, shared by Labels.tsx (layout from the plan)
// and Declutter.tsx (last check on screen), so both decide the same way:
// 1. one fixed priority list: on a collision the higher rank always wins, never the one drawn first;
// 2. fixed zoom tiers (mapZoom.ts) whose edges are held 15 % past the threshold (zoom hysteresis);
// 3. Töpfer's radical law as a density cap: labels per screen area grow only with the square root of the zoom;
// 4. overlap hysteresis: a label that is shown keeps its place until it is clearly covered, a hidden one only comes
//    back with a clear margin;
// 5. stable placement: visibility is decided only at decision points (zoom step, floor, route, selection, round,
//    building), never while the map only pans or rotates.

/** Label classes, high to low. The spec's order (destination ... furniture) with three additions: the task markers
 * (route floor-change badges, closure chips, found dots: markers, not names) above every name, the names of found
 * things right after the tapped room (they answer the question just asked) and closed lifts and stairs before the
 * round stop (safety), the symbols of the coloured rooms before the zone names (never colour without a symbol), and
 * the second lines and door widths after everything (details). */
export const LABEL_PRIORITY = [
  "marker",
  "destination",
  "here",
  "selected",
  "found",
  "closure",
  "roundStop",
  "landmark",
  "roomSymbol",
  "zone",
  "poi",
  "room",
  "machine",
  "furniture",
  "detail",
] as const;

export type LabelClass = (typeof LABEL_PRIORITY)[number];

const RANK = new Map<string, number>(LABEL_PRIORITY.map((name, index) => [name, index]));

/** Rank of a class (lower wins); unknown classes rank with the room names. */
export function rankOfClass(name: string | undefined | null): number {
  const rank = name ? RANK.get(name) : undefined;
  return rank ?? RANK.get("room")!;
}

/** Sorted by priority, then by the given tie key (an id), so the same input always gives the same order. */
export function byPriority<T>(items: readonly T[], classOf: (item: T) => LabelClass, keyOf: (item: T) => string): T[] {
  return [...items].sort((a, b) => rankOfClass(classOf(a)) - rankOfClass(classOf(b)) || keyOf(a).localeCompare(keyOf(b)));
}

/** Classes the density cap never drops: what the current task names (they are few), and the symbols of the coloured
 * rooms (kitchen, bathroom, stairs, lift, meeting): they say what the colour means, never colour without a symbol. */
const UNCAPPED: ReadonlySet<LabelClass> = new Set(["marker", "destination", "here", "selected", "found", "closure", "roundStop", "landmark", "roomSymbol"]);

export function capped(name: LabelClass): boolean {
  return !UNCAPPED.has(name);
}

export interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** How far two boxes overlap (px, the smaller of the two axes); negative: the gap between them. */
export function overlapPx(a: Box, b: Box): number {
  return Math.min(Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0), Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0));
}

/** Overlap hysteresis (px). A label that is shown stays while it overlaps another by at most `hold`; a hidden or new
 * one only shows with at least `reveal` px of free space around it. Between the two the last state stays. */
export interface Hysteresis {
  hold: number;
  reveal: number;
}

/** Does `other` push `box` off the map? `shown`: the label is shown now. */
export function blocked(box: Box, other: Box, shown: boolean, h: Hysteresis): boolean {
  const overlap = overlapPx(box, other);
  return shown ? overlap > h.hold : overlap > -h.reveal;
}

/** Zoom hysteresis: a zoom step (tier or scale bucket) is only left once the scale is this much past its edge. */
export const ZOOM_MARGIN = 1.15;

/** Has the zoom changed by a full step since the last decision (more than ZOOM_MARGIN either way)? Panning and
 * rotating never change the scale, so they never count. */
export function zoomStepChanged(metresPerPixel: number, atDecision: number | null): boolean {
  if (atDecision === null || !(atDecision > 0) || !(metresPerPixel > 0)) return true;
  return Math.abs(Math.log(metresPerPixel / atDecision)) > Math.log(ZOOM_MARGIN);
}

/** Töpfer's radical law, per screen area: at the reference scale a cell of DENSITY_CELL_PX² carries at most
 * DENSITY_REF capped labels; zooming in by a factor k allows sqrt(k) times as many (twice as close: 1.4 times). */
export const DENSITY_CELL_PX = 256;
export const DENSITY_REF = 6;
export const DENSITY_REF_MPP = 0.3; // the far/mid tier edge (mapZoom.ts)

/** The most capped labels one density cell may carry at a scale (metres per screen pixel). */
export function densityCap(metresPerPixel: number): number {
  return Math.max(1, Math.floor(DENSITY_REF * Math.sqrt(DENSITY_REF_MPP / Math.max(1e-3, metresPerPixel))));
}

/** A density budget over fixed cells of the layout (layout px, so it does not move with the camera): `take` says
 * whether one more capped label fits in the cell of its box centre and counts it. Items must come in priority
 * order, so the lowest ranked ones are the ones dropped. */
export function densityBudget(metresPerPixel: number, cellPx = DENSITY_CELL_PX): { cap: number; take: (box: Box) => boolean } {
  const cap = densityCap(metresPerPixel);
  const used = new Map<string, number>();
  return {
    cap,
    take(box) {
      const key = `${Math.floor((box.x0 + box.x1) / 2 / cellPx)},${Math.floor((box.y0 + box.y1) / 2 / cellPx)}`;
      const n = used.get(key) ?? 0;
      if (n >= cap) return false;
      used.set(key, n + 1);
      return true;
    },
  };
}

export interface Placed<T> {
  item: T;
  box: Box;
  shown: boolean;
}

/** One decision: walks the items in priority order (sorted by the caller) and keeps each one that no kept box
 * blocks (with hysteresis) and that fits the density budget. `fixed` are boxes nothing may cover (markers). Returns
 * the kept items. */
export function decide<T>(
  items: readonly Placed<T>[],
  options: { fixed?: readonly Box[]; hysteresis: Hysteresis; budget?: { take: (box: Box) => boolean }; isCapped?: (item: T) => boolean },
): Set<T> {
  const kept: Box[] = [...(options.fixed ?? [])];
  const out = new Set<T>();
  for (const { item, box, shown } of items) {
    if (kept.some((other) => blocked(box, other, shown, options.hysteresis))) continue;
    if (options.budget && options.isCapped?.(item) && !options.budget.take(box)) continue;
    kept.push(box);
    out.add(item);
  }
  return out;
}

/** A room's name as the map shows it: without a numbered suffix in brackets ("Kitchen 0.27 (apartment 6)" becomes
 * "Kitchen 0.27"), which only crowds the map; the room card and the list keep the full name. A bracket without a
 * number is part of the name and stays ("Café (Gastraum)"). */
export function mapRoomName(name: string): string {
  return name.replace(/\s*\([^()]*\d[^()]*\)\s*$/, "").trim() || name;
}
