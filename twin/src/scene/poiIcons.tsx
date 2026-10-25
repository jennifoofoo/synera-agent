// Point-of-interest pictograms for the 2D map: a white glyph in a small round grey badge, like a street map.
import "./poiIcons.css";

export type PoiKind = "stairs" | "lift" | "toilet" | "meeting" | "entrance" | "step" | "coffee" | "printer" | "extinguisher" | "firstaid";

/** What each symbol means, for the legend in the help card (ui/KeyHelp.tsx) and twin/CONTROLS.md. */
export const POI_LEGEND: { kind: PoiKind; label: string }[] = [
  { kind: "entrance", label: "Entrance / exit" },
  { kind: "lift", label: "Lift" },
  { kind: "stairs", label: "Stairs" },
  { kind: "toilet", label: "Toilets" },
  { kind: "meeting", label: "Meeting room" },
  { kind: "step", label: "Not step-free (a step or threshold)" },
  { kind: "coffee", label: "Coffee machine" },
  { kind: "printer", label: "Printer" },
  { kind: "extinguisher", label: "Fire extinguisher" },
  { kind: "firstaid", label: "First aid / defibrillator / eyewash" },
];

/** Things shown as a symbol on the 2D map (from the middle zoom tier on), by asset type. */
export function amenityKindOf(type: string): PoiKind | null {
  if (type === "coffee_machine") return "coffee";
  if (type === "printer" || type === "multifunction_printer") return "printer";
  if (type === "fire_extinguisher") return "extinguisher";
  if (type === "defibrillator" || type === "first_aid_kit" || type === "first_aid" || /^eye_?wash/.test(type)) return "firstaid";
  return null;
}

/** Badge diameter in px (CSS below must match); used for collision boxes. */
export const POI_PX = 22;

const GLYPHS: Record<PoiKind, JSX.Element> = {
  // a staircase seen from the side
  stairs: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path className="stroke" d="M3.5 19.5h4.5v-4.5h4v-4h4v-4.5h4.5" />
    </svg>
  ),
  // a lift car with up and down arrows
  lift: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <rect className="stroke" x="4" y="3.5" width="16" height="17" rx="2" />
      <path d="M8.5 10.5 12 6.5l3.5 4z" />
      <path d="M8.5 13.5 12 17.5l3.5-4z" />
    </svg>
  ),
  // a man and a woman, split by a line
  toilet: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <circle cx="6.5" cy="5" r="2" />
      <path d="M4.5 8.5h4a1.2 1.2 0 0 1 1.2 1.2v4.8H8.4v6H4.6v-6H3.3V9.7a1.2 1.2 0 0 1 1.2-1.2z" />
      <path className="stroke thin" d="M12 3v18" />
      <circle cx="17.5" cy="5" r="2" />
      <path d="M15.6 8.5h3.8l2.4 7.5h-2.4v4.5h-3.8V16h-2.4z" />
    </svg>
  ),
  // a meeting: three people round a table
  meeting: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="5" r="2.1" />
      <circle cx="5.5" cy="9" r="2" />
      <circle cx="18.5" cy="9" r="2" />
      <path d="M3 14.5h18v3H3z" />
      <path className="stroke thin" d="M7 17.5v3M17 17.5v3" />
    </svg>
  ),
  // not step-free: a single step (a threshold) on the floor line
  step: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path className="stroke" d="M3.5 17.5h8v-6h9" />
    </svg>
  ),
  // a cup with a handle and steam
  coffee: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path d="M4.5 9.5h11v4.5a5 5 0 0 1-5 5h-1a5 5 0 0 1-5-5z" />
      <path className="stroke" d="M15.5 11h1.5a2.2 2.2 0 0 1 0 4.4h-1.5" />
      <path className="stroke thin" d="M8 3.5v3M11.5 3.5v3" />
    </svg>
  ),
  // a printer with a sheet coming out
  printer: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path className="stroke" d="M7.5 8V3.5h9V8" />
      <path d="M3.5 8.5h17v8h-3v-3h-11v3h-3z" />
      <path className="stroke" d="M7.5 14.5h9v6h-9z" />
    </svg>
  ),
  // a fire extinguisher: body, valve, hose
  extinguisher: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path d="M8.5 9h6v11a1.5 1.5 0 0 1-1.5 1.5h-3A1.5 1.5 0 0 1 8.5 20z" />
      <path d="M10 5h3v3.5h-3z" />
      <path className="stroke thin" d="M13 6h3.5l2 3" />
    </svg>
  ),
  // a cross (first aid, defibrillator)
  firstaid: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path d="M9.5 3.5h5v6h6v5h-6v6h-5v-6h-6v-5h6z" />
    </svg>
  ),
  // Tabler Icons "door-exit" (MIT, https://tabler.io/icons): a door with an arrow out
  entrance: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path className="stroke" d="M13 12v.01M3 21h18M5 21v-16a2 2 0 0 1 2 -2h7.5m2.5 10.5v7.5M14 7h7m-3 -3l3 3l-3 3" />
    </svg>
  ),
};

/** `closed`: the same glyph with a danger-red edge and a diagonal bar (prohibition style), for a closed lift or stairs. */
export function PoiBadge({ kind, title, closed = false }: { kind: PoiKind; title: string; closed?: boolean }) {
  return (
    <div className={`poi-badge poi-${kind} ${closed ? "poi-closed" : ""}`} title={title} role="img" aria-label={title} data-closed={closed || undefined}>
      {GLYPHS[kind]}
    </div>
  );
}

/** Width (px) of the "Closed" tag beside a closed glyph (12 px semibold, see .closed-tag). */
export const CLOSED_TAG_PX = 46;

/** Height of the floor-change badge and the found-item name (px); widths come from floorBadgeWidth / the text. */
export const FLOOR_BADGE_H_PX = 22;
export function floorBadgeWidth(level: number): number {
  return 22 + 8 + String(level).length * 7 + 6; // glyph, arrow, level digits, padding
}

/** Where the route changes floor: the stairs or lift glyph with "↑ 1", in the route blue (map-app style). */
export function FloorBadge({ kind, direction, level, title }: { kind: "stairs" | "lift"; direction: "up" | "down"; level: number; title: string }) {
  return (
    <div className="floor-badge" title={title} role="img" aria-label={title} data-floor-change={level}>
      {GLYPHS[kind]}
      <span>
        {direction === "up" ? "↑" : "↓"}
        {level}
      </span>
    </div>
  );
}

/** Diameter (px) of a found thing's dot, and of a dot that stands for several close together. */
export const FOUND_DOT_PX = 12;
export const FOUND_MANY_PX = 18;

export function FoundDot({ count, title }: { count: number; title: string }) {
  return (
    <div className={`found-dot ${count > 1 ? "many" : ""}`} title={title} role="img" aria-label={title}>
      {count > 1 ? count : null}
    </div>
  );
}
