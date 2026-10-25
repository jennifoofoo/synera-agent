// Pure parts of the inspection round panel (no store, no fetch), so they can be tested: which type an asset is, the
// area choices of a building and where a round starts when nobody is placed. The order itself is planned on the server
// (POST /api/round, the same plan_round the chat agent uses).

import type { Asset, Floor, Opening, Space } from "../api/types";

/** "Fire extinguishers", "fire_extinguisher" and "Fire extinguisher" are the same type. */
export function normType(text: string): string {
  return text.trim().toLowerCase().replace(/[_-]+/g, " ").replace(/\s+/g, " ").replace(/(?<=\w)(es|s)$/, "");
}

export function typeMatches(asset: Asset, query: string): boolean {
  const q = normType(query);
  return !!q && normType(asset.type) === q;
}

/** The hall group of a zone name: "Production zone H-A3" -> "A" (factories name their hall bays H-A1, H-B2, ...). */
export function hallOf(name: string): string | null {
  return /\bH-([A-Z])\d+\b/.exec(name)?.[1] ?? null;
}

/** Area choices for a building: whole building, each floor, each hall group found in the room names. */
export function areaOptions(floors: Floor[], spaces: Space[]): string[] {
  const halls = [...new Set(spaces.map((space) => hallOf(space.name)).filter((hall): hall is string => !!hall))].sort();
  return ["Whole building", ...[...floors].sort((a, b) => a.level - b.level).map((floor) => floor.name || `Level ${floor.level}`), ...halls.map((hall) => `Hall ${hall}`)];
}

/** Whether an asset lies in an area choice of the panel ("Whole building", a floor name or "Level n", "Hall A"). */
export function assetInArea(asset: Asset, area: string, floors: Floor[], spaceName: (id: string) => string): boolean {
  if (!area || area === "Whole building") return true;
  const hall = /^Hall ([A-Z])$/.exec(area)?.[1];
  if (hall) return hallOf(spaceName(asset.space_id)) === hall;
  const floor = floors.find((candidate) => (candidate.name || `Level ${candidate.level}`) === area);
  return floor ? asset.floor_id === floor.id : true;
}

/** Where a round starts when nobody is placed: the room behind the building's first entrance (by room id). */
export function entranceRoom(openings: Opening[], spaces: Space[] = []): string | null {
  const rooms = [...new Set(openings.filter((opening) => opening.kind === "entrance" && opening.space_ids.length).map((opening) => opening.space_ids[0]))];
  // The main entrance: a lobby or entrance hall first, then a corridor, then any room (the first by id breaks ties).
  const rank = (id: string) => {
    const space = spaces.find((s) => s.id === id);
    const kind = `${space?.room_type ?? ""} ${space?.type ?? ""} ${space?.name ?? ""}`.toLowerCase();
    return /lobby|foyer|entrance|reception/.test(kind) ? 0 : /corridor|hall/.test(kind) ? 1 : 2;
  };
  return rooms.sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))[0] ?? null;
}

/** Why no round can be planned on this map, or null: no devices at all, or none of the type asked for. */
export function missingDevicesNote(assets: Asset[], type?: string): string | null {
  if (!assets.length) return "This map has no devices yet, so there is no round to plan.";
  if (type && !assets.some((asset) => typeMatches(asset, type))) return `This map has no ${normType(type)}s yet.`;
  return null;
}
