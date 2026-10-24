// The look ("Blueprint minimal"): warm paper, flat graphite greys for the building, one signal colour (Synera blue) for
// the route, selection and primary actions. State colours (green / red) only for exceptions. Values marked "token"
// mirror src/styles/tokens.css; change both together.

export type SpaceGroup = "production" | "logistics" | "office" | "technical" | "circulation" | "outdoor";

// Room types differ by lightness only, never by hue.
export const GROUP_COLOURS: Record<SpaceGroup, { slab: string; wall: string; label: string }> = {
  production: { slab: "#b4b8bd", wall: "#a2a7ad", label: "Production" },
  logistics: { slab: "#c2c2bd", wall: "#b0b0ab", label: "Logistics" },
  office: { slab: "#dcdad4", wall: "#cbc9c2", label: "Office" },
  technical: { slab: "#9ea4ac", wall: "#8d949c", label: "Technical" },
  circulation: { slab: "#ebe8e2", wall: "#dbd8d1", label: "Circulation" },
  outdoor: { slab: "#cfd0c8", wall: "#bfc0b8", label: "Outdoor" },
};

export const COLOURS = {
  edge: "#2b323d", // wall outlines, graphite
  edgeGhost: "#7b828c",
  ghost: "#9aa0a8",
  ground: "#eae7e1", // token --paper-2
  background: "#f4f2ee", // token --paper
  plan: "#f4f2ee", // 2D map background, token --paper
  signal: "#004fab", // token --signal
  mapBlue: "#004fab", // 2D route line (the signal colour; the name is historic)
  mapBlueDark: "#002478", // 2D route casing
  mapRed: "#1d2430", // 2D destination pin (graphite; the name is historic)
  accent: "#004fab",
  gold: "#004fab",
  stairs: "#8a8372", // stairs shafts, muted taupe
  accentBlue: "#7a6a9a", // lift shafts, muted violet
  thing: "#b3b6ba",
  machine: "#8c929a",
  ok: "#2f7d5b", // token --ok
  warn: "#4a5260", // token --warn
  danger: "#b3382c", // token --danger
  route: "#004fab",
  routeGlow: "#ffffff",
  selection: "#004fab",
  here: "#004fab", // token --info
  added: "#2f7d5b",
  removed: "#8a8f96",
};

const PRODUCTION = new Set(["production_zone", "assembly_zone", "additive_zone", "quality_lab", "lab", "makerspace"]);
const LOGISTICS = new Set(["warehouse_zone", "logistics_zone", "storage"]);
const TECHNICAL = new Set(["technical_room", "server_room", "lift", "stairwell", "print_room"]);
const CIRCULATION = new Set(["corridor", "lobby"]);

export function spaceGroup(type: string, roomType: string): SpaceGroup {
  if (type === "outdoor" || roomType === "balcony") return "outdoor";
  if (type === "stair" || type === "lift") return "technical";
  if (type === "corridor" || CIRCULATION.has(roomType)) return "circulation";
  if (PRODUCTION.has(roomType)) return "production";
  if (LOGISTICS.has(roomType)) return "logistics";
  if (TECHNICAL.has(roomType)) return "technical";
  return "office";
}

export function prettyType(roomType: string): string {
  return roomType.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
