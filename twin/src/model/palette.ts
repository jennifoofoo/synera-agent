// The look: blue base, colour only for information. Five calm blue groups for room types (they also differ in
// lightness), neutral things, status colours only for exceptions (ok / warn / danger), turquoise as the accent.

export type SpaceGroup = "production" | "logistics" | "office" | "technical" | "circulation" | "outdoor";

export const GROUP_COLOURS: Record<SpaceGroup, { slab: string; wall: string; label: string }> = {
  production: { slab: "#8fb3dc", wall: "#7ea3cf", label: "Production" },
  logistics: { slab: "#a6b8cf", wall: "#95a9c3", label: "Logistics" },
  office: { slab: "#cfdeef", wall: "#bccfe6", label: "Office" },
  technical: { slab: "#6d8cb4", wall: "#5f7da5", label: "Technical" },
  circulation: { slab: "#e4ecf5", wall: "#d2deec", label: "Circulation" },
  outdoor: { slab: "#b7c6d6", wall: "#a7b8ca", label: "Outdoor" },
};

export const COLOURS = {
  edge: "#14305a",
  edgeGhost: "#466a9a",
  ghost: "#7f9fc6",
  ground: "#dfe7f0",
  background: "#edf2f8",
  plan: "#f3f1ec", // 2D map background
  mapBlue: "#4285f4",
  mapBlueDark: "#1a5fd0",
  mapRed: "#ea4335",
  accent: "#5eead4",
  gold: "#e3b45a",
  accentBlue: "#60a5fa",
  thing: "#9fb3c8",
  machine: "#7f95ad",
  ok: "#34d399",
  warn: "#fbbf24",
  danger: "#f43f5e",
  route: "#5eead4",
  routeGlow: "#99f6e4",
  selection: "#e3b45a",
  here: "#2dd4bf",
  added: "#34d399",
  removed: "#94a3b8",
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
