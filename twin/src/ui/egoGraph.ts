// Ego graph of one room from the building's JSON-LD knowledge graph (GET /api/graph, Brick/RealEstateCore types),
// for the Knowledge panel (KnowledgeGraph.tsx, docs/specs/knowledge-graph-view.md). Pure: no DOM, no fetch.
// Rings: 0 the room, 1 the things that carry a note plus lifts/stairs (everything else collapses into one "+N more"
// node; a room without notes shows its 6 most relevant things instead), 2 the facts anchored there, 3 the persons who
// reported them. Radii and the viewBox follow the node count, labels are wrapped (never cut) next to their node. Facts are filtered by time t on the client (validFrom / validTo).

export interface LdNode {
  "@id": string;
  "@type"?: string | string[];
  name?: string;
  kind?: string;
  text?: string;
  category?: string;
  isLocatedIn?: string;
  connects?: string[];
  anchoredAt?: string[];
  related?: string[];
  reportedBy?: string;
  validFrom?: string;
  validTo?: string;
  resolves?: string;
}

export type FactState = "open" | "ended" | "future" | "resolving";
export type Role = "room" | "asset" | "door" | "connector" | "more" | "note" | "issue" | "closure" | "event" | "person";

export interface EgoNode {
  id: string; // the JSON-LD @id ("more" for the +N node)
  ring: 0 | 1 | 2 | 3;
  role: Role;
  label: string;
  types: string[];
  /** facts only: open or ended at t; number = stable 1-based index over all facts of the room (oldest first) */
  state?: "open" | "ended";
  number?: number;
  text?: string;
  /** ring 1 only: one or more facts hang on it */
  hasFacts?: boolean;
  /** ring 1 and persons: the label wrapped to at most two lines (never cut) */
  lines?: string[];
  /** ring 1 only: which side of the node the label sits on (outside, away from the room) */
  side?: "left" | "right";
  /** facts only: who and where, for the list under the graph */
  person?: string;
  anchor?: string;
  x: number;
  y: number;
}

export interface EgoEdge {
  from: string;
  to: string;
  faded: boolean;
}

export interface MoreItem {
  id: string;
  label: string;
  types: string[];
}

export interface EgoGraph {
  nodes: EgoNode[];
  edges: EgoEdge[];
  /** how many things sit behind the "+N more" node, and which (for the plain text list under the graph) */
  more: number;
  moreItems: MoreItem[];
  /** the SVG viewBox: as wide as the panel, as high as the drawing needs */
  view: { x: number; y: number; width: number; height: number };
  /** validFrom (ms) of the oldest fact of the room, null without facts */
  oldest: number | null;
}

export interface EgoOptions {
  at: number;
  showEnded?: boolean;
  cap?: number;
  width?: number;
}

export const RING1_CAP = 16;
/** A room without notes shows this many things. */
export const QUIET_SHOWN = 6;
const CATEGORY_RANK: Record<string, number> = { machine: 0, equipment: 1, fixture: 4, furniture: 5 };
const SAFETY = /fire|extinguish|alarm|defibrill|first.?aid|smoke|sprinkler|hydrant|emergency|\baed\b/i;

export function typesOf(node: LdNode): string[] {
  const types = node["@type"];
  return Array.isArray(types) ? types : types ? [types] : [];
}

/** The building's own id of a node: "urn:synera:<building>:<kind>:<id>" -> "<id>". */
export function localId(iri: string): string {
  return iri.split(":").slice(4).join(":");
}

/** The type shown in the tag: the most specific one (Brick/REC classes before the generic wanda:Fact). */
export function mainType(types: string[]): string {
  const generic = new Set(["brick:Equipment", "brick:Space", "wanda:Fact", "wanda:Person"]);
  return types.find((type) => !generic.has(type)) ?? types[0] ?? "";
}

function ms(value: string | undefined): number | null {
  if (!value) return null;
  const time = Date.parse(value);
  return Number.isNaN(time) ? null : time;
}

/** A fact as seen at time t: future before validFrom, ended from validTo on, resolving facts are never drawn. */
export function factStateAt(fact: LdNode, at: number): FactState {
  if (fact.resolves) return "resolving";
  const from = ms(fact.validFrom);
  if (from !== null && from > at) return "future";
  const to = ms(fact.validTo);
  if (to !== null && to <= at) return "ended";
  return "open";
}

function isFact(node: LdNode): boolean {
  return typesOf(node).includes("wanda:Fact");
}

/**
 * A label on at most two lines, balanced, split after spaces or - _ / (a single long word is split in the middle with
 * a hyphen). Never cut with "…": the text is always complete, `max` is only the width after which it wraps.
 */
export function wrapLabel(text: string, max: number): string[] {
  const clean = text.trim().replace(/\s+/g, " ");
  if (clean.length <= max) return [clean];
  const cuts: Array<[string, string]> = [];
  for (let i = 1; i < clean.length; i += 1) {
    if (clean[i - 1] === " ") cuts.push([clean.slice(0, i - 1), clean.slice(i)]);
    else if ("-_/".includes(clean[i - 1]) && clean[i] !== " ") cuts.push([clean.slice(0, i), clean.slice(i)]);
  }
  if (cuts.length === 0) {
    const mid = Math.ceil(clean.length / 2);
    return [`${clean.slice(0, mid)}-`, clean.slice(mid)];
  }
  const size = ([x, y]: [string, string]) => Math.max(x.length, y.length);
  const best = cuts.reduce((m, c) => (size(c) < size(m) ? c : m));
  return [best[0], best[1]];
}

/** Build the ego graph of room `roomId` (the building's space id) at time `at`, with positions for width x height. */
export function egoGraph(graph: LdNode[], roomId: string, options: EgoOptions): EgoGraph {
  const { at, showEnded = false, cap = RING1_CAP, width = 400 } = options;
  const room = graph.find((node) => typesOf(node).some((type) => type.startsWith("rec:")) && localId(node["@id"]) === roomId && node["@id"].includes(":space:"));
  if (!room) return { nodes: [], edges: [], more: 0, moreItems: [], view: { x: 0, y: 0, width, height: 0 }, oldest: null };
  const roomIri = room["@id"];
  const byId = new Map(graph.map((node) => [node["@id"], node]));

  // ring 1 candidates: assets in the room, doors/openings and lifts/stairs connecting it
  const around = graph.filter((node) => !isFact(node) && (node.isLocatedIn === roomIri || (node.connects ?? []).includes(roomIri)));
  const aroundIds = new Set(around.map((node) => node["@id"]));

  // facts of the room: anchored at the room or a ring 1 candidate, or located in the room (all times, oldest first)
  const facts = graph
    .filter(isFact)
    .filter((fact) => factStateAt(fact, at) !== "resolving")
    .filter((fact) => fact.isLocatedIn === roomIri || [...(fact.anchoredAt ?? []), ...(fact.related ?? [])].some((id) => id === roomIri || aroundIds.has(id)))
    .sort((a, b) => (ms(a.validFrom) ?? 0) - (ms(b.validFrom) ?? 0) || a["@id"].localeCompare(b["@id"]));
  const oldest = facts.length ? ms(facts[0].validFrom) : null;
  const visible = facts
    .map((fact, index) => ({ fact, index, state: factStateAt(fact, at) }))
    .filter(({ state }) => state === "open" || (state === "ended" && showEnded));

  // unnamed doors and openings are named after the room on the other side ("Door to Flur Nord")
  const nameOf = (node: LdNode | undefined): string => {
    if (!node) return "Door";
    if (node.name) return node.name;
    const other = (node.connects ?? []).find((id) => id !== roomIri);
    return other && byId.get(other)?.name ? `Door to ${byId.get(other)?.name}` : "Door";
  };
  const anchorOf = (fact: LdNode): string => (fact.anchoredAt ?? []).find((id) => aroundIds.has(id)) ?? roomIri;
  const withFacts = new Set(visible.map(({ fact }) => anchorOf(fact)));

  const isConnector = (node: LdNode): boolean => !!node.connects && !typesOf(node).includes("rec:Door");
  const isSafety = (node: LdNode): boolean => SAFETY.test(`${typesOf(node).join(" ")} ${node.name ?? ""}`);
  // relevance: things with notes, lifts/stairs, doors, safety devices, then the rest (machines before furniture)
  const rank = (node: LdNode): number => {
    if (withFacts.has(node["@id"])) return -1;
    if (isConnector(node)) return 0;
    if (node.connects) return 1;
    if (isSafety(node)) return 2;
    return 3 + (CATEGORY_RANK[node.category ?? ""] ?? 1);
  };
  const sorted = [...around].sort((a, b) => rank(a) - rank(b) || (a.name ?? a["@id"]).localeCompare(b.name ?? b["@id"]));
  // with notes: only what carries one, plus lifts/stairs; without any note: the most relevant few, named
  const quiet = visible.length === 0;
  const core = quiet ? sorted.slice(0, QUIET_SHOWN) : sorted.filter((node) => rank(node) <= 0);
  const picked = core.length > cap ? core.slice(0, cap - 1) : core;
  const pickedIds = new Set(picked.map((node) => node["@id"]));
  const rest = sorted.filter((node) => !pickedIds.has(node["@id"]));
  const more = rest.length;
  const moreItems: MoreItem[] = rest.map((node) => ({ id: node["@id"], label: node.connects ? nameOf(node) : (node.name ?? localId(node["@id"])), types: typesOf(node) }));
  const shown = spreadOut(picked, (node) => withFacts.has(node["@id"]));

  // radii follow the node count, so a small graph is compact (a ring leaves room for the labels beside its nodes)
  const cx = width / 2;
  const ring1Count = shown.length + (more > 0 ? 1 : 0);
  const personCount = new Set(visible.map(({ fact }) => fact.reportedBy).filter(Boolean)).size;
  const outer = Math.max(cx - 40, 90); // outermost ring: persons, their names sit beneath
  let r1 = Math.min(Math.max(30 + 10 * ring1Count, 56), 120);
  let gap = 42;
  if (visible.length > 0) {
    const rings = personCount > 0 ? 3 : 2;
    if (r1 + (rings - 1) * gap > outer) {
      r1 = Math.max(44, outer - (rings - 1) * gap);
      gap = Math.max(30, (outer - r1) / (rings - 1));
    }
  }
  const r2 = r1 + gap;
  const r3 = r2 + gap;
  const cy = 0; // shifted into view afterwards
  const polar = (r: number, angle: number) => ({ x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) });

  const nodes: EgoNode[] = [{ id: roomIri, ring: 0, role: "room", label: room.name ?? roomId, types: typesOf(room), x: cx, y: cy }];
  const edges: EgoEdge[] = [];
  const angleOf = new Map<string, number>();
  const step = (2 * Math.PI) / Math.max(ring1Count, 1);
  const start = -Math.PI / 2 + step / 2;
  // label beside its node, on the outside: left of nodes on the left half, right of nodes on the right half
  const labelFor = (label: string, point: { x: number; y: number }) => {
    const side: "left" | "right" = point.x >= cx ? "right" : "left";
    const room = (side === "right" ? width - point.x : point.x) - 20;
    return { side, lines: wrapLabel(label, Math.min(Math.max(Math.floor(room / 5.8), 10), 22)) };
  };
  shown.forEach((node, index) => {
    const angle = start + index * step;
    angleOf.set(node["@id"], angle);
    const role: Role = node.connects ? (typesOf(node).includes("rec:Door") ? "door" : "connector") : "asset";
    const label = role === "asset" ? (node.name ?? localId(node["@id"])) : nameOf(node);
    const point = polar(r1, angle);
    nodes.push({ id: node["@id"], ring: 1, role, label, types: typesOf(node), hasFacts: withFacts.has(node["@id"]), ...labelFor(label, point), ...point });
    edges.push({ from: roomIri, to: node["@id"], faded: false });
  });
  if (more > 0) {
    const angle = start + shown.length * step;
    angleOf.set("more", angle);
    const point = polar(r1, angle);
    nodes.push({ id: "more", ring: 1, role: "more", label: `+${more} more`, types: [], ...labelFor(`+${more} more`, point), ...point });
    edges.push({ from: roomIri, to: "more", faded: false });
  }

  // ring 2: facts near the angle of their anchor (fanned out when several share one); room facts fill the gaps
  const groups = new Map<string, typeof visible>();
  for (const entry of visible) {
    const anchor = anchorOf(entry.fact);
    groups.set(anchor, [...(groups.get(anchor) ?? []), entry]);
  }
  const free = freeAngles(
    [...angleOf.entries()].filter(([id]) => withFacts.has(id) || id === "more").map(([, angle]) => angle), // keep clear of the +N node too
    groups.get(roomIri)?.length ?? 0,
    start + step / 2,
  );
  const personAngles = new Map<string, number[]>();
  for (const [anchor, entries] of groups) {
    entries.forEach(({ fact, index, state }, k) => {
      const base = anchor === roomIri ? free[k] : (angleOf.get(anchor) ?? start);
      // The anchor's label runs sideways at the anchor's height, so turn the fact away from the horizontal
      // (further up in the top half, further down in the bottom half), else it sits on the label.
      const away = Math.sign(Math.sin(base) * Math.cos(base)) || 1;
      const spread = anchor === roomIri ? 0 : away * 0.5 + (k - (entries.length - 1) / 2) * 0.34;
      const angle = base + spread;
      const kind = (fact.kind ?? "note") as Role;
      const role: Role = kind === "issue" || kind === "closure" || kind === "event" ? kind : "note";
      const person = fact.reportedBy ? byId.get(fact.reportedBy) : undefined;
      nodes.push({
        id: fact["@id"],
        ring: 2,
        role,
        label: String(index + 1),
        types: typesOf(fact),
        state: state === "ended" ? "ended" : "open",
        number: index + 1,
        text: fact.text ?? "",
        person: person?.name,
        anchor: anchor === roomIri ? (room.name ?? roomId) : nameOf(byId.get(anchor)),
        ...polar(r2, angle),
      });
      edges.push({ from: anchor, to: fact["@id"], faded: state === "ended" });
      if (fact.reportedBy) {
        personAngles.set(fact.reportedBy, [...(personAngles.get(fact.reportedBy) ?? []), angle]);
        edges.push({ from: fact["@id"], to: fact.reportedBy, faded: state === "ended" });
      }
    });
  }

  // ring 3: persons at the mean angle of what they said, the name (wrapped, never cut) beneath
  for (const [personId, angles] of personAngles) {
    const person = byId.get(personId);
    const angle = Math.atan2(
      angles.reduce((sum, a) => sum + Math.sin(a), 0),
      angles.reduce((sum, a) => sum + Math.cos(a), 0),
    );
    const name = person?.name ?? localId(personId);
    nodes.push({ id: personId, ring: 3, role: "person", label: name, lines: wrapLabel(name, 12), types: person ? typesOf(person) : ["rec:Person"], ...polar(r3, angle) });
  }

  // the viewBox hugs the drawing: no empty band above or below a small graph
  let top = Infinity;
  let bottom = -Infinity;
  for (const node of nodes) {
    const lineCount = node.lines?.length ?? 0;
    const above = node.ring === 1 ? (lineCount * LINE_H) / 2 : 0;
    const below = node.role === "person" ? PERSON_R + 6 + lineCount * LINE_H : above;
    const body = node.ring === 0 ? ROOM_R + 3 : node.ring === 2 ? FACT_R : node.ring === 3 ? PERSON_R : ASSET_R + 2;
    top = Math.min(top, node.y - Math.max(body, above));
    bottom = Math.max(bottom, node.y + Math.max(body, below));
  }
  const pad = 8;
  const view = { x: 0, y: top - pad, width, height: bottom - top + 2 * pad };
  return { nodes, edges, more, moreItems, view, oldest };
}

/** Sizes shared with KnowledgeGraph.tsx: node radii per ring and the line heights of labels. */
export const ROOM_R = 22;
export const ASSET_R = 7;
export const FACT_R = 10;
export const PERSON_R = 12;
export const LINE_H = 12;

/** The flagged items on evenly spaced slots (so things with notes do not bunch up), the rest in order between. */
export function spreadOut<T>(items: T[], flagged: (item: T) => boolean): T[] {
  const hot = items.filter(flagged);
  const cold = items.filter((item) => !flagged(item));
  if (hot.length === 0 || cold.length === 0) return items;
  const slots = new Set(hot.map((_, k) => Math.floor((k * items.length) / hot.length)));
  const out: T[] = [];
  let h = 0;
  let c = 0;
  for (let i = 0; i < items.length; i += 1) out.push(slots.has(i) ? hot[h++] : cold[c++]);
  return out;
}

/** `count` angles spread into the widest gaps between `taken` angles (all if nothing is taken). */
function freeAngles(taken: number[], count: number, start: number): number[] {
  if (count === 0) return [];
  if (taken.length === 0) return Array.from({ length: count }, (_, i) => start + (i * 2 * Math.PI) / count);
  const sorted = [...taken].sort((a, b) => a - b);
  const gaps = sorted.map((angle, i) => {
    const next = i + 1 < sorted.length ? sorted[i + 1] : sorted[0] + 2 * Math.PI;
    return { from: angle, size: next - angle };
  });
  gaps.sort((a, b) => b.size - a.size);
  return Array.from({ length: count }, (_, i) => {
    const gap = gaps[i % gaps.length];
    const slot = Math.floor(i / gaps.length) + 1;
    const slots = Math.ceil(count / gaps.length) + 1;
    return gap.from + (gap.size * slot) / slots;
  });
}

/** "Now", "Tomorrow 18:00", "Mon 27 Oct, 09:00": the slider's label. */
export function momentLabel(at: number, now: number): string {
  if (Math.abs(at - now) < 30 * 60 * 1000) return "Now";
  const date = new Date(at);
  const time = date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const day = (value: number) => new Date(value).toDateString();
  if (day(at) === day(now)) return `Today ${time}`;
  if (day(at) === day(now + 86_400_000)) return `Tomorrow ${time}`;
  if (day(at) === day(now - 86_400_000)) return `Yesterday ${time}`;
  return `${date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })}, ${time}`;
}

export const HOUR_MS = 3_600_000;
export const DAY_MS = 24 * HOUR_MS;

/** Slider range: the oldest fact (or a day back) to three days ahead, whole hours. */
export function timeRange(oldest: number | null, now: number): { min: number; max: number } {
  const min = Math.floor(Math.min(oldest ?? now, now - DAY_MS) / HOUR_MS) * HOUR_MS;
  const max = Math.ceil((now + 3 * DAY_MS) / HOUR_MS) * HOUR_MS;
  return { min, max };
}
