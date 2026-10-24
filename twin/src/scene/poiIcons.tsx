// Point-of-interest pictograms for the 2D map: a white glyph in a small round grey badge, like a street map.
import "./poiIcons.css";

export type PoiKind = "stairs" | "lift" | "toilet" | "entrance" | "step";

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
  // not step-free: a single step (a threshold) on the floor line
  step: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path className="stroke" d="M3.5 17.5h8v-6h9" />
    </svg>
  ),
  // Tabler Icons "door-exit" (MIT, https://tabler.io/icons): a door with an arrow out
  entrance: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path className="stroke" d="M13 12v.01M3 21h18M5 21v-16a2 2 0 0 1 2 -2h7.5m2.5 10.5v7.5M14 7h7m-3 -3l3 3l-3 3" />
    </svg>
  ),
};

export function PoiBadge({ kind, title }: { kind: PoiKind; title: string }) {
  return (
    <div className={`poi-badge poi-${kind}`} title={title} role="img" aria-label={title}>
      {GLYPHS[kind]}
    </div>
  );
}

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
