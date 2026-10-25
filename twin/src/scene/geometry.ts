// Merged geometry per floor: slabs and low walls of every room in one BufferGeometry (vertex colours per room
// group, a per-vertex room index for picking, an outward wall normal for the dollhouse cutaway) plus one line
// geometry for the fine dark edges. Model metres: x east, y north -> scene x, -z. Local y = 0 is the floor.

import * as THREE from "three";
import { computeBoundsTree, disposeBoundsTree, acceleratedRaycast } from "three-mesh-bvh";
import type { BuildingState, Opening, Point, Space } from "../api/types";
import { GROUP_COLOURS, GROUP_INDEX, PLAN_GLSL, isIndustrial, spaceGroup } from "../model/palette";

import type { FloorModel } from "../model/model";

THREE.BufferGeometry.prototype.computeBoundsTree = computeBoundsTree;
THREE.BufferGeometry.prototype.disposeBoundsTree = disposeBoundsTree;
THREE.Mesh.prototype.raycast = acceleratedRaycast;

export const SLAB_THICKNESS = 0.14;
export const WALL_THICKNESS = 0.12;
export const CUTAWAY_HEIGHT = 0.3;

export interface FloorGeometry {
  solid: THREE.BufferGeometry;
  edges: THREE.BufferGeometry;
  /** dashed zone lines where a wide opening joins two halves of one hall (no wall there) */
  zones: THREE.BufferGeometry;
  /** space index (into floor.spaces) per vertex of `solid`, for picking */
  spaceIndexOf: (vertexIndex: number) => number;
  /** true when the vertex belongs to a wall piece (not a slab) */
  isWall: (vertexIndex: number) => boolean;
  wallHeight: number;
  spaceCount: number;
}

export function wallHeightFor(floor: FloorModel, scale = 0.42): number {
  return Math.min(3.2, Math.max(1.1, floor.height_m * scale));
}

function signedArea(polygon: Point[]): number {
  let area = 0;
  for (let i = 0; i < polygon.length; i++) {
    const [x1, y1] = polygon[i];
    const [x2, y2] = polygon[(i + 1) % polygon.length];
    area += x1 * y2 - x2 * y1;
  }
  return area / 2;
}

function ccw(polygon: Point[]): Point[] {
  const cleaned = polygon.filter((p, i) => {
    const q = polygon[(i + 1) % polygon.length];
    return Math.abs(p[0] - q[0]) > 1e-6 || Math.abs(p[1] - q[1]) > 1e-6;
  });
  return signedArea(cleaned) < 0 ? cleaned.reverse() : cleaned;
}

function edgeKey(a: Point, b: Point): string {
  const ka = `${a[0].toFixed(2)},${a[1].toFixed(2)}`;
  const kb = `${b[0].toFixed(2)},${b[1].toFixed(2)}`;
  return ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`;
}

class Builder {
  positions: number[] = [];
  normals: number[] = [];
  colours: number[] = [];
  wallNormals: number[] = [];
  walls: number[] = []; // 1 for wall vertices (flattened in the 2D plan), 0 for slabs
  groups: number[] = []; // room group index per vertex (plan colours in 2D)
  currentGroup = 2;
  spaceIndices: number[] = [];
  indices: number[] = [];
  lines: number[] = [];
  zoneLines: number[] = []; // dashed hall zone lines (their own geometry: lighter than walls)
  lineWallNormals: number[] = [];
  lineWalls: number[] = [];

  vertex(x: number, y: number, z: number, n: [number, number, number], c: THREE.Color, wn: [number, number], sid: number, wall = 0): number {
    this.positions.push(x, y, -z);
    this.normals.push(n[0], n[1], n[2]);
    this.colours.push(c.r, c.g, c.b);
    this.wallNormals.push(wn[0], wn[1]);
    this.walls.push(wall);
    this.groups.push(this.currentGroup);
    this.spaceIndices.push(sid);
    return this.positions.length / 3 - 1;
  }

  line(a: [number, number, number], b: [number, number, number], wn: [number, number], wall = 0) {
    this.lines.push(a[0], a[1], -a[2], b[0], b[1], -b[2]);
    this.lineWallNormals.push(wn[0], wn[1], wn[0], wn[1]);
    this.lineWalls.push(wall, wall);
  }

  /** Jamb ticks at both ends of a gap: perpendicular hairlines about a wall thickness long, on the floor. */
  jambs([p, q]: Gap) {
    const length = Math.hypot(q[0] - p[0], q[1] - p[1]);
    if (length < 0.05) return;
    const nx = (-(q[1] - p[1]) / length) * JAMB_HALF;
    const ny = ((q[0] - p[0]) / length) * JAMB_HALF;
    for (const end of [p, q]) this.line([end[0] - nx, 0.02, end[1] - ny], [end[0] + nx, 0.02, end[1] + ny], [0, 0], 0);
  }

  /** A dashed zone line along a gap (lighter than the walls; the hall continues on both sides). */
  zone([p, q]: Gap) {
    const length = Math.hypot(q[0] - p[0], q[1] - p[1]);
    for (let s = 0; s < length; s += DASH * 2) {
      const a = pointOnEdge(p, q, s);
      const b = pointOnEdge(p, q, Math.min(length, s + DASH));
      this.zoneLines.push(a[0], 0.02, -a[1], b[0], 0.02, -b[1]);
    }
  }

  /** A vertical quad (wall piece) between two ground points, from y0 to y1, both sides. */
  wallPiece(a: Point, b: Point, y0: number, y1: number, colour: THREE.Color, outward: [number, number], sid: number, thickness: number) {
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const length = Math.hypot(dx, dy);
    if (length < 0.02) return;
    const nx = dy / length;
    const ny = -dx / length; // right-hand normal (outward for CCW polygons)
    const hx = (nx * thickness) / 2;
    const hy = (ny * thickness) / 2;
    const corners: Point[] = [
      [a[0] + hx, a[1] + hy],
      [b[0] + hx, b[1] + hy],
      [b[0] - hx, b[1] - hy],
      [a[0] - hx, a[1] - hy],
    ];
    // Box: 4 sides + top. Scene normal: model (nx, ny) -> scene (nx, -ny) because z = -y.
    const sides: [Point, Point, [number, number, number]][] = [
      [corners[0], corners[1], [nx, 0, -ny]],
      [corners[2], corners[3], [-nx, 0, ny]],
      [corners[1], corners[2], [dx / length, 0, -dy / length]],
      [corners[3], corners[0], [-dx / length, 0, dy / length]],
    ];
    for (const [p, q, n] of sides) {
      const i0 = this.vertex(p[0], y0, p[1], n, colour, outward, sid, 1);
      const i1 = this.vertex(q[0], y0, q[1], n, colour, outward, sid, 1);
      const i2 = this.vertex(q[0], y1, q[1], n, colour, outward, sid, 1);
      const i3 = this.vertex(p[0], y1, p[1], n, colour, outward, sid, 1);
      this.indices.push(i0, i1, i2, i0, i2, i3);
    }
    // The top face is a step darker than the sides: with the light edge line it reads as a crisp wall top.
    const topColour = colour.clone().multiplyScalar(0.94);
    const t = corners.map((c) => this.vertex(c[0], y1, c[1], [0, 1, 0], topColour, outward, sid, 1));
    this.indices.push(t[0], t[1], t[2], t[0], t[2], t[3]);
    // Edge lines along the top of the wall (both long sides); in the 2D plan they become the wall lines.
    this.line([corners[0][0], y1, corners[0][1]], [corners[1][0], y1, corners[1][1]], outward, 1);
    this.line([corners[3][0], y1, corners[3][1]], [corners[2][0], y1, corners[2][1]], outward, 1);
  }

  slab(polygon: Point[], top: number, colour: THREE.Color, sid: number, gaps: Gap[] = []) {
    const shape = polygon.map(([x, y]) => new THREE.Vector2(x, y));
    const triangles = THREE.ShapeUtils.triangulateShape(shape, []);
    const base = this.positions.length / 3;
    for (const [x, y] of polygon) this.vertex(x, top, y, [0, 1, 0], colour, [0, 0], sid);
    for (const [a, b, c] of triangles) this.indices.push(base + a, base + b, base + c);
    // Sides of the slab (thin), darker so the stack reads as plates. Left out where an opening cuts the edge, so the
    // plan has no outline across a gap.
    const sideColour = colour.clone().multiplyScalar(0.9);
    for (let i = 0; i < polygon.length; i++) {
      const edgeStart = polygon[i];
      const edgeEnd = polygon[(i + 1) % polygon.length];
      const dx = edgeEnd[0] - edgeStart[0];
      const dy = edgeEnd[1] - edgeStart[1];
      const length = Math.hypot(dx, dy) || 1;
      const n: [number, number, number] = [dy / length, 0, dx / length];
      for (const [t0, t1] of keptPieces(edgeStart, edgeEnd, gaps)) {
        const p = lerp(edgeStart, edgeEnd, t0);
        const q = lerp(edgeStart, edgeEnd, t1);
        const i0 = this.vertex(p[0], top - SLAB_THICKNESS, p[1], n, sideColour, [0, 0], sid);
        const i1 = this.vertex(q[0], top - SLAB_THICKNESS, q[1], n, sideColour, [0, 0], sid);
        const i2 = this.vertex(q[0], top, q[1], n, sideColour, [0, 0], sid);
        const i3 = this.vertex(p[0], top, p[1], n, sideColour, [0, 0], sid);
        this.indices.push(i0, i1, i2, i0, i2, i3);
        this.line([p[0], top, p[1]], [q[0], top, q[1]], [0, 0]);
      }
    }
  }

  build(spaceIndexByVertex: Int32Array | null): { solid: THREE.BufferGeometry; edges: THREE.BufferGeometry; zones: THREE.BufferGeometry } {
    const solid = new THREE.BufferGeometry();
    solid.setAttribute("position", new THREE.Float32BufferAttribute(this.positions, 3));
    solid.setAttribute("normal", new THREE.Float32BufferAttribute(this.normals, 3));
    solid.setAttribute("color", new THREE.Float32BufferAttribute(this.colours, 3));
    solid.setAttribute("wallNormal", new THREE.Float32BufferAttribute(this.wallNormals, 2));
    solid.setAttribute("wall", new THREE.Float32BufferAttribute(this.walls, 1));
    solid.setAttribute("roomGroup", new THREE.Float32BufferAttribute(this.groups, 1));
    solid.setAttribute("spaceIndex", new THREE.Float32BufferAttribute(this.spaceIndices, 1));
    // Focus mode (FloorMesh.tsx): 1 = the room is on the shown route (or no route), 0 = it fades toward the paper.
    solid.setAttribute("focus", new THREE.Float32BufferAttribute(new Float32Array(this.spaceIndices.length).fill(1), 1));
    solid.setIndex(this.indices);
    solid.computeBoundingSphere();
    solid.computeBoundsTree();
    void spaceIndexByVertex;
    const edges = new THREE.BufferGeometry();
    edges.setAttribute("position", new THREE.Float32BufferAttribute(this.lines, 3));
    edges.setAttribute("wallNormal", new THREE.Float32BufferAttribute(this.lineWallNormals, 2));
    edges.setAttribute("wall", new THREE.Float32BufferAttribute(this.lineWalls, 1));
    edges.computeBoundingSphere();
    const zones = new THREE.BufferGeometry();
    zones.setAttribute("position", new THREE.Float32BufferAttribute(this.zoneLines, 3));
    zones.computeBoundingSphere();
    return { solid, edges, zones };
  }
}

type Gap = [Point, Point];

/** One cut an opening makes: the gap, whether it gets jamb ticks, whether it is a hall zone line (no wall at all). */
export interface Cut {
  gap: Gap;
  jambs: boolean;
  zone: boolean;
}

/** An opening this wide that spans most of the shared boundary is one hall in two zones, not two rooms. */
const ZONE_MIN_WIDTH = 4;
const ZONE_MIN_SHARE = 0.6;
const JAMB_HALF = 0.1; // jamb tick: perpendicular hairline, 0.2 m long
const DASH = 0.5; // zone line dash and gap length in metres

const PERP_TOL = 0.35; // a gap cuts an edge that runs within this distance of it
const SHARED_TOL = 0.35; // two polygon edges count as one shared boundary within this distance
const CORNER_TIE = 0.05; // edges this much farther than the nearest one still count as meeting it (a corner)
const DOOR_REACH = 0.8; // a door or entrance belongs to the polygon edge within this distance of its position

function pointOnEdge(a: Point, b: Point, s: number): Point {
  const length = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
  return [a[0] + ((b[0] - a[0]) / length) * s, a[1] + ((b[1] - a[1]) / length) * s];
}

/** Metres along edge a-b of the point nearest to p, and its distance to the edge (clamped to the edge). */
function nearestOnEdge(a: Point, b: Point, p: Point): { s: number; distance: number; length: number } {
  const length = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1e-9;
  const s = Math.max(0, Math.min(length, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / length));
  const q = pointOnEdge(a, b, s);
  return { s, distance: Math.hypot(p[0] - q[0], p[1] - q[1]), length };
}

/** The stretches where two polygons share a boundary (collinear, overlapping edges), as segments in model metres. */
function sharedBoundaries(first: Point[], second: Point[]): Gap[] {
  const found: Gap[] = [];
  for (let i = 0; i < first.length; i++) {
    const a = first[i];
    const b = first[(i + 1) % first.length];
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (length < 0.05) continue;
    const ux = (b[0] - a[0]) / length;
    const uy = (b[1] - a[1]) / length;
    for (let j = 0; j < second.length; j++) {
      const c = second[j];
      const d = second[(j + 1) % second.length];
      const off = (r: Point) => Math.abs((r[0] - a[0]) * uy - (r[1] - a[1]) * ux);
      if (off(c) > SHARED_TOL || off(d) > SHARED_TOL) continue;
      const along = (r: Point) => (r[0] - a[0]) * ux + (r[1] - a[1]) * uy;
      const s0 = Math.max(0, Math.min(along(c), along(d)));
      const s1 = Math.min(length, Math.max(along(c), along(d)));
      if (s1 - s0 > 0.05) found.push([pointOnEdge(a, b, s0), pointOnEdge(a, b, s1)]);
    }
  }
  return found;
}

/**
 * The cuts an opening makes into the walls, gaps as segments in model metres (empty: nothing to cut).
 * - between two spaces: width_m centred on `position` projected onto the shared boundary of the two polygons,
 *   clamped to that boundary (an opening of kind "opening" wider than the boundary opens all of it).
 * - entrances, and doors with no shared boundary near them: width_m centred on `position` along the polygon edge nearest to it; at a
 *   polygon corner (two edges equally near) both edges open.
 */
export function openingCuts(opening: Opening, polygons: Point[][]): Cut[] {
  if (!polygons.length) return [];
  const width = opening.width_m && opening.width_m > 0 ? opening.width_m : 0.9;
  if (polygons.length >= 2) {
    // Between two spaces the gap lies on their shared boundary, whatever else is near the position.
    let best: { segment: Gap; s: number; length: number; distance: number } | null = null;
    for (const segment of sharedBoundaries(polygons[0], polygons[1])) {
      const hit = nearestOnEdge(segment[0], segment[1], opening.position);
      if (!best || hit.distance < best.distance) best = { segment, ...hit };
    }
    if (best && (opening.kind === "opening" || best.distance <= DOOR_REACH)) {
      const { segment, s, length } = best;
      const half = opening.kind === "opening" ? width / 2 : Math.max(0.3, width / 2);
      const zone = opening.kind === "opening" && width >= ZONE_MIN_WIDTH && width >= length * ZONE_MIN_SHARE;
      const whole = zone || (opening.kind === "opening" && width >= length - 0.01);
      const gap: Gap = [pointOnEdge(segment[0], segment[1], whole ? 0 : Math.max(0, s - half)), pointOnEdge(segment[0], segment[1], whole ? length : Math.min(length, s + half))];
      return [{ gap, jambs: opening.kind !== "opening", zone }];
    }
  }
  const near: { a: Point; b: Point; s: number; distance: number; length: number }[] = [];
  for (const polygon of polygons) {
    for (let i = 0; i < polygon.length; i++) {
      const a = polygon[i];
      const b = polygon[(i + 1) % polygon.length];
      const hit = nearestOnEdge(a, b, opening.position);
      if (hit.length >= 0.05) near.push({ a, b, ...hit });
    }
  }
  if (!near.length) return [];
  const closest = Math.min(...near.map((edge) => edge.distance));
  if (closest > DOOR_REACH) return [];
  const half = Math.max(0.3, width / 2);
  return near
    .filter((edge) => edge.distance <= closest + CORNER_TIE)
    .map((edge): Cut => ({
      gap: [pointOnEdge(edge.a, edge.b, Math.max(0, edge.s - half)), pointOnEdge(edge.a, edge.b, Math.min(edge.length, edge.s + half))],
      jambs: opening.kind !== "opening",
      zone: false,
    }));
}

/** The pieces of [0, 1] (parameter along edge a-b) that stay after cutting the gaps that lie along the edge. */
function keptPieces(a: Point, b: Point, gaps: Gap[]): [number, number][] {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const length = Math.hypot(dx, dy);
  if (!gaps.length) return [[0, 1]];
  if (length < 0.05) {
    // A stub (data noise at a corner): its direction means nothing, so it goes when it sits inside a gap.
    const mid: Point = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    const inside = gaps.some(([p, q]) => nearestOnEdge(p, q, mid).distance <= PERP_TOL);
    return inside ? [] : [[0, 1]];
  }
  const cuts: [number, number][] = [];
  for (const [p, q] of gaps) {
    const off = (r: Point) => Math.abs((r[0] - a[0]) * dy - (r[1] - a[1]) * dx) / length;
    if (off(p) > PERP_TOL || off(q) > PERP_TOL) continue;
    const t = (r: Point) => ((r[0] - a[0]) * dx + (r[1] - a[1]) * dy) / (length * length);
    const t0 = Math.max(0, Math.min(t(p), t(q)));
    const t1 = Math.min(1, Math.max(t(p), t(q)));
    if (t1 > t0 + 1e-3) cuts.push([t0, t1]);
  }
  if (!cuts.length) return [[0, 1]];
  cuts.sort((g, h) => g[0] - h[0]);
  const minPiece = 0.03 / length;
  const pieces: [number, number][] = [];
  let cursor = 0;
  for (const [start, end] of cuts) {
    if (start > cursor + minPiece) pieces.push([cursor, start]);
    cursor = Math.max(cursor, end);
  }
  if (cursor < 1 - minPiece) pieces.push([cursor, 1]);
  return pieces;
}

function lerp(a: Point, b: Point, t: number): Point {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/** What of `state` changes the walls: doors added, removed or widened since the building was loaded. */
export interface OpeningEdits {
  added: BuildingState["added_doors"];
  removed: string[];
  widened: Record<string, number>;
}

export function openingEditsOf(state: BuildingState | null): OpeningEdits {
  return { added: state?.added_doors ?? [], removed: state?.removed_openings ?? [], widened: state?.widened_openings ?? {} };
}

/** The floor's openings with the session's edits applied (a removed door is wall again, a widened one opens more). */
export function effectiveOpenings(floor: FloorModel, edits?: OpeningEdits): Opening[] {
  if (!edits) return floor.openings;
  const removed = new Set(edits.removed);
  const known = new Set(floor.openings.map((opening) => opening.id));
  const kept = floor.openings
    .filter((opening) => !removed.has(opening.id))
    .map((opening) => (edits.widened[opening.id] ? { ...opening, width_m: edits.widened[opening.id] } : opening));
  const added: Opening[] = edits.added
    .filter((door) => door.floor_id === floor.id && !known.has(door.id) && !removed.has(door.id))
    .map((door) => ({ id: door.id, floor_id: door.floor_id, space_ids: door.space_ids, kind: "door", position: door.position, width_m: 0.9, step_free: door.step_free, added: true }));
  return [...kept, ...added];
}

/** Where a floor's walls stand: the CCW polygons, how many rooms own each edge (1 = outer wall) and the gaps the
 * openings cut per space. Shared by the floor mesh and the selection's wall-top outline, so both agree exactly. */
interface WallLayout {
  polygons: Point[][];
  edgeOwners: Map<string, number>;
  gapsBySpace: Map<string, Gap[]>;
  allCuts: Cut[];
}

function wallLayout(floor: FloorModel, edits?: OpeningEdits): WallLayout {
  // Which edges are shared by two rooms (interior) and which face outside.
  const edgeOwners = new Map<string, number>();
  const polygons: Point[][] = floor.spaces.map((space) => ccw(space.polygon));
  polygons.forEach((polygon) => {
    for (let i = 0; i < polygon.length; i++) {
      const key = edgeKey(polygon[i], polygon[(i + 1) % polygon.length]);
      edgeOwners.set(key, (edgeOwners.get(key) ?? 0) + 1);
    }
  });
  // Gaps per space: every opening cuts the walls and the outline of the spaces it joins.
  const indexById = new Map(floor.spaces.map((space, index) => [space.id, index]));
  const gapsBySpace = new Map<string, Gap[]>();
  const allCuts: Cut[] = [];
  for (const opening of effectiveOpenings(floor, edits)) {
    const joined = opening.space_ids.filter((id) => indexById.has(id));
    const cuts = openingCuts(
      opening,
      joined.map((id) => polygons[indexById.get(id)!]),
    );
    allCuts.push(...cuts);
    for (const spaceId of joined) {
      const list = gapsBySpace.get(spaceId) ?? [];
      list.push(...cuts.map((cut) => cut.gap));
      gapsBySpace.set(spaceId, list);
    }
  }
  return { polygons, edgeOwners, gapsBySpace, allCuts };
}

/** Outward wall normal in scene xz for an outer edge a-b of a CCW polygon (the cutaway lowers walls facing the
 * camera along it); interior edges get none. */
function outwardOf(a: Point, b: Point, outer: boolean): [number, number] {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const length = Math.hypot(dx, dy) || 1;
  // Model (dy, -dx)/len -> scene (dy, dx)/len (z = -y flips the sign of y).
  return outer ? [dy / length, dx / length] : [0, 0];
}

export function buildFloorGeometry(floor: FloorModel, edits?: OpeningEdits): FloorGeometry {
  const builder = new Builder();
  const wallHeight = wallHeightFor(floor);
  const colourCache = new Map<string, THREE.Color>();
  const colourFor = (hex: string) => {
    let colour = colourCache.get(hex);
    if (!colour) colourCache.set(hex, (colour = new THREE.Color(hex)));
    return colour;
  };
  const { polygons, edgeOwners, gapsBySpace, allCuts } = wallLayout(floor, edits);
  const drawnEdges = new Set<string>();
  const industrial = isIndustrial(floor.spaces);
  floor.spaces.forEach((space: Space, sid) => {
    const polygon = polygons[sid];
    if (polygon.length < 3) return;
    const group = spaceGroup(space.type, space.room_type, { name: space.name, industrial });
    const palette = GROUP_COLOURS[group];
    builder.currentGroup = GROUP_INDEX[group];
    const gaps = gapsBySpace.get(space.id) ?? [];
    builder.slab(polygon, 0, colourFor(palette.slab), sid, gaps);
    const isOutdoor = space.type === "outdoor";
    const height = isOutdoor ? Math.min(wallHeight, 0.5) : wallHeight;
    for (let i = 0; i < polygon.length; i++) {
      const a = polygon[i];
      const b = polygon[(i + 1) % polygon.length];
      const key = edgeKey(a, b);
      // Edges shared by two spaces are built once, with the gaps of both.
      if (drawnEdges.has(key)) continue;
      drawnEdges.add(key);
      const outward = outwardOf(a, b, (edgeOwners.get(key) ?? 1) === 1);
      for (const [t0, t1] of keptPieces(a, b, gaps)) {
        builder.wallPiece(lerp(a, b, t0), lerp(a, b, t1), 0, height, colourFor(palette.wall), outward, sid, WALL_THICKNESS);
      }
    }
  });
  for (const cut of allCuts) {
    if (cut.zone) builder.zone(cut.gap);
    else if (cut.jambs) builder.jambs(cut.gap);
  }
  const { solid, edges, zones } = builder.build(null);
  const spaceIndex = solid.getAttribute("spaceIndex") as THREE.BufferAttribute;
  const wall = solid.getAttribute("wall") as THREE.BufferAttribute;
  return {
    solid,
    edges,
    zones,
    spaceIndexOf: (vertexIndex) => spaceIndex.getX(vertexIndex),
    isWall: (vertexIndex) => wall.getX(vertexIndex) > 0.5,
    wallHeight,
    spaceCount: floor.spaces.length,
  };
}

/** One extruded shape for a polygon (highlights, selection, shafts). Local y = 0 is the base. */
export function polygonGeometry(polygon: Point[], height: number): THREE.ExtrudeGeometry | THREE.ShapeGeometry {
  const ring = ccw(polygon).map(([x, y]) => new THREE.Vector2(x, y));
  const shape = new THREE.Shape(ring);
  const geometry = height > 0 ? new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false }) : new THREE.ShapeGeometry(shape);
  geometry.rotateX(-Math.PI / 2); // shape (x, y) -> scene (x, 0, -y); the extrusion runs along +y
  geometry.computeVertexNormals();
  return geometry;
}

/** Polygon outline as line segments, at height y. */
export function outlineGeometry(polygon: Point[], y: number): THREE.BufferGeometry {
  const points: number[] = [];
  const ring = ccw(polygon);
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i];
    const b = ring[(i + 1) % ring.length];
    points.push(a[0], y, -a[1], b[0], y, -b[1]);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
  return geometry;
}

/** Even-odd point-in-polygon test in model metres. */
export function insidePolygon([x, y]: Point, polygon: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/**
 * The room a tap on a wall means, and the spot for its pin. A wall piece belongs to whichever of its two rooms was
 * built first, and its hit point lies on the room's edge; so the room is the one on the side of the face the camera
 * sees (a wall top: the room beyond it, the one the camera looks into), and the spot is that room's anchor.
 * `normal` is the hit face's normal, `ray` the view direction (both scene xz; scene z = -model y).
 */
export function roomBehindWall(spaces: Space[], fallback: Space, hit: Point, normal: [number, number, number], ray: [number, number, number]): { space: Space; point: Point } {
  let [nx, ny, nz] = normal;
  if (nx * ray[0] + ny * ray[1] + nz * ray[2] > 0) [nx, ny, nz] = [-nx, -ny, -nz]; // the side facing the camera
  let [dx, dz] = Math.abs(ny) > 0.7 ? [ray[0], ray[2]] : [nx, nz];
  const length = Math.hypot(dx, dz) || 1;
  [dx, dz] = [dx / length, dz / length];
  const probe: Point = [hit[0] + dx * (WALL_THICKNESS + 0.2), hit[1] - dz * (WALL_THICKNESS + 0.2)];
  const space = spaces.find((candidate) => candidate.polygon.length >= 3 && insidePolygon(probe, candidate.polygon)) ?? fallback;
  return { space, point: space.anchor };
}

/** Width of the selection band on the wall tops: a touch wider than the wall, so it reads as painting the wall top. */
export const WALL_TOP_BAND = WALL_THICKNESS + 0.04;

/**
 * The selected room's outline on top of its walls (3D): one flat band per wall piece, centred on the polygon edge at
 * the floor's wall height, with the floor mesh's `wallNormal` and `wall` attributes. With the withCutaway material it
 * follows the walls exactly: lowered where the dollhouse cutaway lowers an outer wall; across door gaps and hall zone
 * lines (no wall) it lies on the floor. Drawn
 * on the floor instead, a see-through outline showed the room's floor edge through the near wall, so it seemed to
 * stick out into the corridor (the camera looks over the wall tops, which is where people see a room's boundary).
 */
export function wallTopOutline(floor: FloorModel, spaceId: string, edits?: OpeningEdits): THREE.BufferGeometry {
  const index = floor.spaces.findIndex((space) => space.id === spaceId);
  const geometry = new THREE.BufferGeometry();
  const positions: number[] = [];
  const wallNormals: number[] = [];
  const walls: number[] = [];
  if (index >= 0 && floor.spaces[index].polygon.length >= 3) {
    const { polygons, edgeOwners, gapsBySpace } = wallLayout(floor, edits);
    const polygon = polygons[index];
    const gaps = gapsBySpace.get(spaceId) ?? [];
    const y = (floor.spaces[index].type === "outdoor" ? Math.min(wallHeightFor(floor), 0.5) : wallHeightFor(floor)) + 0.015;
    const floorY = 0.03;
    const half = WALL_TOP_BAND / 2;
    for (let i = 0; i < polygon.length; i++) {
      const a = polygon[i];
      const b = polygon[(i + 1) % polygon.length];
      const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (length < 0.02) continue;
      const ux = (b[0] - a[0]) / length;
      const uy = (b[1] - a[1]) / length;
      const outward = outwardOf(a, b, (edgeOwners.get(edgeKey(a, b)) ?? 1) === 1);
      // Wall pieces get the band on their top; door gaps and hall zone lines (no wall) get it on the floor, so the
      // room's outline stays closed.
      const kept = keptPieces(a, b, gaps);
      const pieces: [number, number, number][] = [];
      let cursor = 0;
      for (const [t0, t1] of kept) {
        if (t0 > cursor + 1e-6) pieces.push([cursor, t0, floorY]);
        pieces.push([t0, t1, y]);
        cursor = t1;
      }
      if (cursor < 1 - 1e-6) pieces.push([cursor, 1, floorY]);
      for (const [t0, t1, height] of pieces) {
        // At the polygon's corners the band runs on by half its width, so neighbouring bands close the corner.
        const p = lerp(a, b, t0);
        const q = lerp(a, b, t1);
        const s0 = t0 <= 1e-6 ? half : 0;
        const s1 = t1 >= 1 - 1e-6 ? half : 0;
        const p0: Point = [p[0] - ux * s0, p[1] - uy * s0];
        const q0: Point = [q[0] + ux * s1, q[1] + uy * s1];
        const corners: Point[] = [
          [p0[0] + uy * half, p0[1] - ux * half],
          [q0[0] + uy * half, q0[1] - ux * half],
          [q0[0] - uy * half, q0[1] + ux * half],
          [p0[0] - uy * half, p0[1] + ux * half],
        ];
        for (const k of [0, 1, 2, 0, 2, 3]) {
          positions.push(corners[k][0], height, -corners[k][1]);
          wallNormals.push(outward[0], outward[1]);
          walls.push(1);
        }
      }
    }
  }
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("wallNormal", new THREE.Float32BufferAttribute(wallNormals, 2));
  geometry.setAttribute("wall", new THREE.Float32BufferAttribute(walls, 1));
  geometry.computeBoundingSphere();
  return geometry;
}

export const FLAT_WALL_HEIGHT = 0.05;

/** Share of the paper tone an off-route room takes in focus mode (it reads at about 40 % strength). */
export const FOCUS_FADE = 0.6;

/** Injects the dollhouse cutaway (outer walls facing the camera lowered to CUTAWAY_HEIGHT), the 2D plan
 * (uFlat = 1: every wall lowered to FLAT_WALL_HEIGHT, so the wall-top edge lines become the plan's wall lines) and
 * focus mode (uFocus = 1 while a route is shown: vertices with `focus` 0 blend FOCUS_FADE toward uPaper). */
export function withCutaway<T extends THREE.Material>(
  material: T,
  uniforms: {
    uCamDir: { value: THREE.Vector2 };
    uCut: { value: number };
    uFlat: { value: number };
    uFocus: { value: number };
    uPaper: { value: THREE.Color };
  },
): T {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uCamDir = uniforms.uCamDir;
    shader.uniforms.uCut = uniforms.uCut;
    shader.uniforms.uFlat = uniforms.uFlat;
    shader.uniforms.uFocus = uniforms.uFocus;
    shader.uniforms.uPaper = uniforms.uPaper;
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        `#include <common>
        attribute vec2 wallNormal;
        attribute float wall;
        attribute float roomGroup;
        attribute float focus;
        uniform vec2 uCamDir;
        uniform float uCut;
        uniform float uFlat;
        uniform float uFocus;
        uniform vec3 uPaper;`,
      )
      .replace(
        "#include <color_vertex>",
        `#include <color_vertex>
        #ifdef USE_COLOR
        {
          // 2D plan: map colours like a street map. Corridors white, rooms near-white, the sought-after groups keep
          // their pale hue, walls grey (palette.ts PLAN_GLSL).${PLAN_GLSL}
          vColor.rgb = mix(vColor.rgb, plan, uFlat);
          // Focus mode: rooms off the route step back toward the paper, slab and walls together.
          vColor.rgb = mix(vColor.rgb, uPaper, uFocus * (1.0 - focus) * ${FOCUS_FADE.toFixed(2)});
        }
        #endif`,
      )
      .replace(
        "#include <begin_vertex>",
        `#include <begin_vertex>
        {
          float facing = dot(wallNormal, uCamDir);
          float cut = step(0.3, facing) * uCut;
          transformed.y = mix(transformed.y, min(transformed.y, ${CUTAWAY_HEIGHT.toFixed(2)}), cut);
          transformed.y = mix(transformed.y, min(transformed.y, ${FLAT_WALL_HEIGHT.toFixed(2)}), uFlat * wall);
        }`,
      );
  };
  material.customProgramCacheKey = () => "cutaway";
  return material;
}
