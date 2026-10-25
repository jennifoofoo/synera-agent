// Pure parts of the inspection round (no store, no fetch), so they can be tested: which assets match, which area
// a room belongs to, and the visiting order (nearest neighbour, then 2-opt) over a distance matrix.

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

/** Does a room belong to the area? Whole building, a floor by name ("Ground floor", "Floor 1", "Level 1"),
 * "Hall A" (zones H-A1, H-A2, ...), "Hall" (all hall zones), or any part of the room name ("Server room"). */
export function inArea(space: Space, floor: Floor | undefined, area: string): boolean {
  const a = area.trim().toLowerCase();
  if (!a || a === "whole building" || a === "all" || a === "building") return true;
  if (floor) {
    const name = (floor.name || "").toLowerCase();
    if (a === name || a === `level ${floor.level}` || a === `floor ${floor.level}` || (a === "ground floor" && floor.level === 0)) return true;
    if (/^(level|floor) \d+$/.test(a) || a === "ground floor" || a === name) return false;
  }
  const hall = /^hall(?:\s+([a-z]))?$/.exec(a);
  if (hall) return hall[1] ? hallOf(space.name)?.toLowerCase() === hall[1] : hallOf(space.name) !== null;
  const words = `${space.name} ${space.ref ?? ""}`.toLowerCase();
  return words.includes(a);
}

/** Where a round starts when nobody is placed: the room behind the building's first entrance (by room id). */
export function entranceRoom(openings: Opening[]): string | null {
  const rooms = openings.filter((opening) => opening.kind === "entrance" && opening.space_ids.length).map((opening) => opening.space_ids[0]);
  return rooms.sort()[0] ?? null;
}

/** Visit order over nodes 0..n-1 starting at node 0, open path (no return): nearest neighbour (ties: lower index),
 * then 2-opt (reverse a stretch while that shortens the path). Returns the order without the start node. */
export function orderRound(distance: number[][]): number[] {
  const n = distance.length;
  if (n <= 1) return [];
  const order = [0];
  const left = new Set(Array.from({ length: n - 1 }, (_, i) => i + 1));
  while (left.size) {
    const current = order[order.length - 1];
    let best = -1;
    for (const j of left) if (best < 0 || distance[current][j] < distance[current][best]) best = j;
    order.push(best);
    left.delete(best);
  }
  const length = (path: number[]) => path.slice(1).reduce((sum, node, i) => sum + distance[path[i]][node], 0);
  let improved = true;
  let current = order;
  let currentLength = length(current);
  while (improved) {
    improved = false;
    for (let i = 1; i < current.length - 1; i++) {
      for (let k = i + 1; k < current.length; k++) {
        const next = [...current.slice(0, i), ...current.slice(i, k + 1).reverse(), ...current.slice(k + 1)];
        const nextLength = length(next);
        if (nextLength < currentLength - 1e-6) {
          current = next;
          currentLength = nextLength;
          improved = true;
        }
      }
    }
  }
  return current.slice(1);
}

/** Straight-line stand-in when there are too many stops to ask the router for every pair: distance between room
 * anchors plus 20 m per floor change (stairs are a detour). */
export function straightLine(a: Space, b: Space, levelOf: (floorId: string) => number): number {
  const floors = Math.abs(levelOf(a.floor_id) - levelOf(b.floor_id));
  return Math.hypot(a.anchor[0] - b.anchor[0], a.anchor[1] - b.anchor[1]) + floors * 20;
}
