// The look ("Blueprint minimal"): warm paper, flat graphite greys for the building, one signal colour (Synera blue) for
// the route, selection and primary actions. State colours (green / red) only for exceptions. Values marked "token"
// mirror src/styles/tokens.css; change both together. Spec: docs/specs/room-colours.md.

export type SpaceGroup =
  | "food" // kitchen, canteen
  | "sanitary" // toilet, bathroom, locker room
  | "vertical" // stairs, lifts
  | "meeting" // meeting, seminar, lecture hall, library
  | "walkway" // main aisles and traffic lanes in industrial buildings (floor marking)
  | "circulation" // corridors, lobbies
  | "work" // office, generic room, bedroom, living room
  | "production"
  | "logistics"
  | "technical"
  | "outdoor";

// Hue only for sought-after groups: the four places people look for (food and break, sanitary, stairs and lifts,
// meeting) plus the industrial walkways (pale lemon like a floor marking) get a very pale hue; everything else stays a
// neutral grey that differs by lightness only. Colour is never alone: every hue group also has an icon and a legend
// entry (LEGEND_GROUPS). The signal blue stays reserved for route, selection and primary buttons, and no room is ever
// filled red or green (those are safety and state colours). The hue groups also differ in lightness, so they stay
// apart under red-green colour blindness. Walls are one step (8 %) darker than their slab, never near-black.
// Ink labels (#1d2430) on every slab are at least 7.8:1 (technical, the darkest grey); WCAG AA needs 4.5:1.
export const GROUP_COLOURS: Record<SpaceGroup, { slab: string; wall: string; label: string }> = {
  food: { slab: "#e8d8b8", wall: "#d5c7a9", label: "Food and break" }, // token --room-food
  sanitary: { slab: "#cde2e8", wall: "#bdd0d5", label: "Toilets" }, // token --room-sanitary
  vertical: { slab: "#c5bcd8", wall: "#b5adc7", label: "Stairs and lifts" }, // token --room-vertical
  meeting: { slab: "#c9d6c0", wall: "#b9c5b1", label: "Meeting" }, // token --room-meeting
  walkway: { slab: "#eee7b8", wall: "#dbd5a9", label: "Walkways" }, // token --room-walkway
  circulation: { slab: "#efede8", wall: "#dcdad5", label: "Corridors" },
  work: { slab: "#dcdad4", wall: "#cac9c3", label: "Work and living" },
  production: { slab: "#c4c7cb", wall: "#b4b7bb", label: "Production" },
  logistics: { slab: "#cbc9c3", wall: "#bbb9b3", label: "Logistics" },
  technical: { slab: "#b4b8bd", wall: "#a6a9ae", label: "Technical" },
  outdoor: { slab: "#e2e3dc", wall: "#d0d1ca", label: "Outdoor" },
};

/** Per-vertex group index for the 2D plan shader (geometry.ts). */
export const GROUP_INDEX: Record<SpaceGroup, number> = {
  production: 0,
  logistics: 1,
  work: 2,
  technical: 3,
  circulation: 4,
  outdoor: 5,
  food: 6,
  sanitary: 7,
  vertical: 8,
  meeting: 9,
  walkway: 10,
};

/** Groups the 2D plan keeps in their own colour; all other rooms become a near-white street map. */
const PLAN_KEEPS_COLOUR: SpaceGroup[] = ["food", "sanitary", "vertical", "meeting", "walkway"];

/** GLSL for the 2D plan colour of a slab (`roomGroup` attribute -> `plan`, a vec3; `vColor` is the slab colour). */
export const PLAN_GLSL = `
          vec3 plan = vec3(0.975, 0.97, 0.955);
          if (roomGroup > ${GROUP_INDEX.circulation - 0.5} && roomGroup < ${GROUP_INDEX.circulation + 0.5}) plan = vec3(1.0);
          if (roomGroup > ${GROUP_INDEX.technical - 0.5} && roomGroup < ${GROUP_INDEX.technical + 0.5}) plan = vec3(0.93, 0.93, 0.915);
          if (roomGroup > ${GROUP_INDEX.outdoor - 0.5} && roomGroup < ${GROUP_INDEX.outdoor + 0.5}) plan = vec3(0.925, 0.925, 0.905);
          if (roomGroup > ${Math.min(...PLAN_KEEPS_COLOUR.map((g) => GROUP_INDEX[g])) - 0.5}) plan = vColor.rgb;
          if (wall > 0.5) plan = vec3(0.76, 0.76, 0.74);`;

export type LegendIcon = "food" | "toilet" | "stairs" | "lift" | "meeting" | "walkway";

/** Legend rows for the help card ("Map symbols"): label, slab colour, and the icon that goes with the colour. */
export const LEGEND_GROUPS: { group: SpaceGroup; label: string; colour: string; icons: LegendIcon[] }[] = [
  { group: "food", label: "Kitchen and canteen", colour: GROUP_COLOURS.food.slab, icons: ["food"] },
  { group: "sanitary", label: "Toilets and lockers", colour: GROUP_COLOURS.sanitary.slab, icons: ["toilet"] },
  { group: "vertical", label: "Stairs and lifts", colour: GROUP_COLOURS.vertical.slab, icons: ["stairs", "lift"] },
  { group: "meeting", label: "Meeting", colour: GROUP_COLOURS.meeting.slab, icons: ["meeting"] },
  { group: "walkway", label: "Walkways", colour: GROUP_COLOURS.walkway.slab, icons: ["walkway"] },
];

export const COLOURS = {
  edge: "#48505b", // wall outlines, graphite (readable thin lines, not near-black)
  edgeGhost: "#7b828c",
  ghost: "#9aa0a8",
  ground: "#eae7e1", // token --paper-2
  background: "#f4f2ee", // token --paper
  plan: "#f4f2ee", // 2D map background, token --paper
  signal: "#004fab", // token --signal
  mapBlue: "#004fab", // 2D route line (the signal colour; the name is historic)
  mapBlueDark: "#002478", // 2D route casing
  mapRed: "#1d2430", // 2D destination pin (graphite; the name is historic)
  destination: "#ea4335", // route destination marker: map-app red, used for nothing else
  accent: "#004fab",
  gold: "#004fab",
  stairs: GROUP_COLOURS.vertical.wall, // stairs shafts, the vertical group colour
  accentBlue: GROUP_COLOURS.vertical.wall, // lift shafts, the vertical group colour (the name is historic)
  thing: "#d0d2d4", // furniture: neutral and quiet
  machine: "#aeb2b8", // machines: a little darker, still neutral
  thingEdge: "#8e939a", // furniture outline
  ok: "#2f7d5b", // token --ok
  warn: "#4a5260", // token --warn
  danger: "#b3382c", // token --danger
  safetyRed: "#a52019", // token --safety-red: fire extinguisher (ISO 3864 / RAL 3001), icons only
  safetyGreen: "#237f52", // token --safety-green: first aid, eyewash, defibrillator, exit (RAL 6032), icons only
  route: "#004fab",
  routeGlow: "#ffffff",
  selection: "#004fab",
  here: "#004fab", // token --info
  added: "#2f7d5b",
  removed: "#8a8f96",
};

const FOOD = new Set(["kitchen", "canteen"]);
const SANITARY = new Set(["toilet", "bathroom", "locker_room"]);
const VERTICAL = new Set(["stairwell", "lift"]);
const MEETING = new Set(["meeting_room", "seminar_room", "lecture_hall", "library"]);
const PRODUCTION = new Set(["production_zone", "assembly_zone", "additive_zone", "quality_lab", "lab", "makerspace"]);
const LOGISTICS = new Set(["warehouse_zone", "logistics_zone", "storage"]);
const TECHNICAL = new Set(["technical_room", "server_room", "print_room"]);
const CIRCULATION = new Set(["corridor", "lobby"]);
const HALL_ZONES = new Set(["production_zone", "assembly_zone", "additive_zone", "warehouse_zone", "logistics_zone"]);
const AISLE_NAME = /\b(aisle|forklift|traffic lane|gang|fahrweg)/i;

/** Whether a set of spaces (a floor) is an industrial hall: it has production, warehouse or logistics zones. */
export function isIndustrial(spaces: { room_type: string }[]): boolean {
  return spaces.some((space) => HALL_ZONES.has(space.room_type));
}

/** The one mapping from a space to its colour group. `name` and `industrial` (see isIndustrial) only decide the
 * walkways: spaces named like an aisle, and corridors in industrial halls that are not office corridors. */
export function spaceGroup(type: string, roomType: string, context: { name?: string; industrial?: boolean } = {}): SpaceGroup {
  const name = context.name ?? "";
  if (type === "outdoor" || roomType === "balcony") return "outdoor";
  if (type === "stair" || type === "lift" || VERTICAL.has(roomType)) return "vertical";
  if (FOOD.has(roomType)) return "food";
  if (SANITARY.has(roomType)) return "sanitary";
  if (MEETING.has(roomType)) return "meeting";
  const corridor = type === "corridor" || roomType === "corridor";
  if (AISLE_NAME.test(name) || (context.industrial && corridor && !/office/i.test(name))) return "walkway";
  if (corridor || CIRCULATION.has(roomType)) return "circulation";
  if (PRODUCTION.has(roomType)) return "production";
  if (LOGISTICS.has(roomType)) return "logistics";
  if (TECHNICAL.has(roomType)) return "technical";
  return "work";
}

export function prettyType(roomType: string): string {
  return roomType.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
