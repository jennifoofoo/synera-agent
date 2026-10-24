// Areas of a floor for the overview tier of the 2D map (spec: docs/specs/semantic-zoom.md, level 1): adjacent rooms
// of the same kind are merged into one area with one calm name ("Production", "Logistics", "Offices", "Social").
// Kinds come from the colour groups (model/palette.ts spaceGroup), so the areas match the room colours. Corridors,
// walkways, stairs, lifts and outdoor spaces join no area: they are the gaps between areas (and stairs, lifts and
// toilets carry their own symbols). Two rooms are adjacent when they share a piece of wall: an edge of each lies on
// the same line (within TOLERANCE_M) and the two edges overlap by at least MIN_SHARED_M. A small area beside a much
// larger one of another kind joins it (ABSORB), so a lone kitchen among offices does not break up "Offices".
// Computed once per floor (a few ms for the largest floors).

import type { Point, Space } from "../api/types";
import type { FloorModel } from "../model/model";
import { isIndustrial, spaceGroup } from "../model/palette";

export interface Area {
  id: string;
  name: string;
  /** Where the name goes: the area-weighted centre of its rooms, or the nearest room anchor if that is outside. */
  point: Point;
  /** Bounding box size in metres (for the "does the name fit" test). */
  width: number;
  height: number;
  area_m2: number;
  space_ids: string[];
  polygons: Point[][];
}

const TOLERANCE_M = 0.35;
const MIN_SHARED_M = 0.5;
/** A service area (SERVICE) of at most SMALL_ROOMS rooms, or smaller than ABSORB of its neighbour, joins it. */
const ABSORB = 0.5;
const SMALL_ROOMS = 2;
const SERVICE = new Set(["Social", "Technical", "Kitchen", "Bath"]);
const WORK = new Set(["Offices", "Living"]);
/** Generic rooms merge into areas but get no name (it would say nothing) and take in no service rooms. */
const UNNAMED = "Rooms";

const RESIDENTIAL = new Set(["bedroom", "living_room"]);

/** The area kind of a room (its name on the map), or null for rooms that join no area. */
function kindOf(space: Space, industrial: boolean, residential: boolean): string | null {
  const group = spaceGroup(space.type, space.room_type, { name: space.name, industrial });
  switch (group) {
    case "production":
      return "Production";
    case "logistics":
      return "Logistics";
    case "technical":
      return "Technical";
    case "food":
      return residential ? "Kitchen" : "Social";
    case "sanitary":
      return residential ? "Bath" : "Social";
    case "meeting":
      return "Social";
    case "work":
      return space.room_type === "office" ? "Offices" : RESIDENTIAL.has(space.room_type) ? "Living" : "Rooms";
    default:
      return null; // walkway, circulation, vertical, outdoor
  }
}

interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

function boxOf(polygon: Point[]): Box {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of polygon) {
    x0 = Math.min(x0, x);
    y0 = Math.min(y0, y);
    x1 = Math.max(x1, x);
    y1 = Math.max(y1, y);
  }
  return { x0, y0, x1, y1 };
}

/** Do two edges lie on one line (within the tolerance) and overlap by at least MIN_SHARED_M? */
function shareWall(a0: Point, a1: Point, b0: Point, b1: Point): boolean {
  const dx = a1[0] - a0[0];
  const dy = a1[1] - a0[1];
  const length = Math.hypot(dx, dy);
  if (length < MIN_SHARED_M) return false;
  const ux = dx / length;
  const uy = dy / length;
  // distance of b's ends from a's line
  const d0 = Math.abs((b0[0] - a0[0]) * uy - (b0[1] - a0[1]) * ux);
  const d1 = Math.abs((b1[0] - a0[0]) * uy - (b1[1] - a0[1]) * ux);
  if (d0 > TOLERANCE_M || d1 > TOLERANCE_M) return false;
  // overlap of the projections onto a's direction
  const t0 = (b0[0] - a0[0]) * ux + (b0[1] - a0[1]) * uy;
  const t1 = (b1[0] - a0[0]) * ux + (b1[1] - a0[1]) * uy;
  return Math.min(length, Math.max(t0, t1)) - Math.max(0, Math.min(t0, t1)) >= MIN_SHARED_M;
}

export function adjacent(a: Point[], b: Point[]): boolean {
  for (let i = 0; i < a.length; i++) {
    const a0 = a[i];
    const a1 = a[(i + 1) % a.length];
    for (let j = 0; j < b.length; j++) {
      if (shareWall(a0, a1, b[j], b[(j + 1) % b.length])) return true;
    }
  }
  return false;
}

function insidePolygon([x, y]: Point, polygon: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Merge the rooms of a floor into areas (connected components of same-kind, wall-sharing rooms). */
export function computeAreas(spaces: Space[]): Area[] {
  const industrial = isIndustrial(spaces);
  const residential = !industrial && spaces.some((space) => RESIDENTIAL.has(space.room_type)) && !spaces.some((space) => space.room_type === "office");
  const rooms = spaces.flatMap((space) => {
    const kind = space.polygon.length >= 3 ? kindOf(space, industrial, residential) : null;
    return kind ? [{ space, kind, box: boxOf(space.polygon) }] : [];
  });
  // Pairs of rooms that share a wall (any kind). Sweep along x: only rooms whose boxes overlap (with the
  // tolerance) are compared edge by edge.
  const pairs: [number, number][] = [];
  const order = rooms.map((_, i) => i).sort((i, j) => rooms[i].box.x0 - rooms[j].box.x0);
  for (let oi = 0; oi < order.length; oi++) {
    const a = rooms[order[oi]];
    for (let oj = oi + 1; oj < order.length; oj++) {
      const b = rooms[order[oj]];
      if (b.box.x0 > a.box.x1 + TOLERANCE_M) break;
      if (b.box.y0 > a.box.y1 + TOLERANCE_M || a.box.y0 > b.box.y1 + TOLERANCE_M) continue;
      if (adjacent(a.space.polygon, b.space.polygon)) pairs.push([order[oi], order[oj]]);
    }
  }
  // 1. Union-find: rooms of the same kind that share a wall form one area.
  const parent = rooms.map((_, i) => i);
  const find = (i: number): number => {
    while (parent[i] !== i) i = parent[i] = parent[parent[i]];
    return i;
  };
  for (const [i, j] of pairs) if (rooms[i].kind === rooms[j].kind) parent[find(i)] = find(j);
  // 2. Small service areas (kitchens, toilets, meeting rooms, technical rooms) join the area beside them, preferably
  // a work area (a single kitchen among offices does not break up "Offices"; its colour and coffee symbol already
  // say what it is). Then same-kind areas that now touch merge too. Smallest first, until nothing changes.
  const name = new Map<number, string>();
  const size = new Map<number, number>();
  const count = new Map<number, number>();
  rooms.forEach((room, i) => {
    const root = find(i);
    if (!name.has(root)) name.set(root, room.kind);
    size.set(root, (size.get(root) ?? 0) + room.space.area_m2);
    count.set(root, (count.get(root) ?? 0) + 1);
  });
  const join = (from: number, into: number) => {
    parent[from] = into;
    size.set(into, size.get(into)! + size.get(from)!);
    count.set(into, count.get(into)! + count.get(from)!);
    size.delete(from);
  };
  const preference = (root: number) => (WORK.has(name.get(root)!) ? 1 : 0);
  for (let changed = true; changed; ) {
    changed = false;
    for (const [i, j] of pairs) {
      const ri = find(i);
      const rj = find(j);
      if (ri !== rj && name.get(ri) === name.get(rj)) {
        join(ri, rj);
        changed = true;
      }
    }
    const roots = [...size.keys()].sort((a, b) => size.get(a)! - size.get(b)! || rooms[a].space.id.localeCompare(rooms[b].space.id));
    for (const root of roots) {
      if (!SERVICE.has(name.get(root)!)) continue;
      let best = -1;
      for (const [i, j] of pairs) {
        const ri = find(i);
        const rj = find(j);
        if (ri === rj || (ri !== root && rj !== root)) continue;
        const other = ri === root ? rj : ri;
        if (SERVICE.has(name.get(other)!) || name.get(other) === UNNAMED) continue;
        const better =
          best < 0 ||
          preference(other) > preference(best) ||
          (preference(other) === preference(best) && (size.get(other)! > size.get(best)! || (size.get(other) === size.get(best) && other < best)));
        if (better) best = other;
      }
      const small = count.get(root)! <= SMALL_ROOMS || size.get(root)! < ABSORB * (best < 0 ? 0 : size.get(best)!);
      if (best < 0 || !small) continue;
      join(root, best);
      changed = true;
      break;
    }
  }
  const groups = new Map<number, typeof rooms>();
  rooms.forEach((room, i) => {
    const root = find(i);
    const list = groups.get(root);
    if (list) list.push(room);
    else groups.set(root, [room]);
  });
  const areas: Area[] = [];
  for (const [root, members] of groups) {
    members.sort((a, b) => a.space.id.localeCompare(b.space.id));
    let total = 0, cx = 0, cy = 0;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const { space, box } of members) {
      const weight = Math.max(0.1, space.area_m2);
      total += weight;
      cx += space.anchor[0] * weight;
      cy += space.anchor[1] * weight;
      x0 = Math.min(x0, box.x0);
      y0 = Math.min(y0, box.y0);
      x1 = Math.max(x1, box.x1);
      y1 = Math.max(y1, box.y1);
    }
    let point: Point = [cx / total, cy / total];
    if (!members.some(({ space }) => insidePolygon(point, space.polygon))) {
      const nearest = members.reduce((best, room) =>
        Math.hypot(room.space.anchor[0] - point[0], room.space.anchor[1] - point[1]) < Math.hypot(best.space.anchor[0] - point[0], best.space.anchor[1] - point[1]) ? room : best,
      );
      point = nearest.space.anchor;
    }
    areas.push({
      id: `area-${members[0].space.id}`,
      name: name.get(root) ?? members[0].kind,
      point,
      width: x1 - x0,
      height: y1 - y0,
      area_m2: members.reduce((sum, { space }) => sum + space.area_m2, 0),
      space_ids: members.map(({ space }) => space.id),
      polygons: members.map(({ space }) => space.polygon),
    });
  }
  // largest first (they win collisions), id as tie-break so the order is stable
  return areas.filter((area) => area.name !== UNNAMED).sort((a, b) => b.area_m2 - a.area_m2 || a.id.localeCompare(b.id));
}

const cache = new WeakMap<FloorModel, Area[]>();

/** The areas of a floor, computed once per floor (the model is rebuilt when the building changes). */
export function areasOf(floor: FloorModel): Area[] {
  let areas = cache.get(floor);
  if (!areas) {
    areas = computeAreas(floor.spaces);
    cache.set(floor, areas);
  }
  return areas;
}
