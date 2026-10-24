// Merged geometry per floor: slabs and low walls of every room in one BufferGeometry (vertex colours per room
// group, a per-vertex room index for picking, an outward wall normal for the dollhouse cutaway) plus one line
// geometry for the fine dark edges. Model metres: x east, y north -> scene x, -z. Local y = 0 is the floor.

import * as THREE from "three";
import { computeBoundsTree, disposeBoundsTree, acceleratedRaycast } from "three-mesh-bvh";
import type { Opening, Point, Space } from "../api/types";
import { GROUP_COLOURS, spaceGroup } from "../model/palette";
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
  /** space index (into floor.spaces) per vertex of `solid`, for picking */
  spaceIndexOf: (vertexIndex: number) => number;
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
  spaceIndices: number[] = [];
  indices: number[] = [];
  lines: number[] = [];
  lineWallNormals: number[] = [];

  vertex(x: number, y: number, z: number, n: [number, number, number], c: THREE.Color, wn: [number, number], sid: number): number {
    this.positions.push(x, y, -z);
    this.normals.push(n[0], n[1], n[2]);
    this.colours.push(c.r, c.g, c.b);
    this.wallNormals.push(wn[0], wn[1]);
    this.spaceIndices.push(sid);
    return this.positions.length / 3 - 1;
  }

  line(a: [number, number, number], b: [number, number, number], wn: [number, number]) {
    this.lines.push(a[0], a[1], -a[2], b[0], b[1], -b[2]);
    this.lineWallNormals.push(wn[0], wn[1], wn[0], wn[1]);
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
      const i0 = this.vertex(p[0], y0, p[1], n, colour, outward, sid);
      const i1 = this.vertex(q[0], y0, q[1], n, colour, outward, sid);
      const i2 = this.vertex(q[0], y1, q[1], n, colour, outward, sid);
      const i3 = this.vertex(p[0], y1, p[1], n, colour, outward, sid);
      this.indices.push(i0, i1, i2, i0, i2, i3);
    }
    const t = corners.map((c) => this.vertex(c[0], y1, c[1], [0, 1, 0], colour, outward, sid));
    this.indices.push(t[0], t[1], t[2], t[0], t[2], t[3]);
    // Edge lines along the top of the wall (both long sides) and along the bottom of the outer face.
    this.line([corners[0][0], y1, corners[0][1]], [corners[1][0], y1, corners[1][1]], outward);
    this.line([corners[3][0], y1, corners[3][1]], [corners[2][0], y1, corners[2][1]], outward);
  }

  slab(polygon: Point[], top: number, colour: THREE.Color, sid: number) {
    const shape = polygon.map(([x, y]) => new THREE.Vector2(x, y));
    const triangles = THREE.ShapeUtils.triangulateShape(shape, []);
    const base = this.positions.length / 3;
    for (const [x, y] of polygon) this.vertex(x, top, y, [0, 1, 0], colour, [0, 0], sid);
    for (const [a, b, c] of triangles) this.indices.push(base + a, base + b, base + c);
    // Sides of the slab (thin), darker so the stack reads as plates.
    const sideColour = colour.clone().multiplyScalar(0.82);
    for (let i = 0; i < polygon.length; i++) {
      const p = polygon[i];
      const q = polygon[(i + 1) % polygon.length];
      const dx = q[0] - p[0];
      const dy = q[1] - p[1];
      const length = Math.hypot(dx, dy) || 1;
      const n: [number, number, number] = [dy / length, 0, dx / length];
      const i0 = this.vertex(p[0], top - SLAB_THICKNESS, p[1], n, sideColour, [0, 0], sid);
      const i1 = this.vertex(q[0], top - SLAB_THICKNESS, q[1], n, sideColour, [0, 0], sid);
      const i2 = this.vertex(q[0], top, q[1], n, sideColour, [0, 0], sid);
      const i3 = this.vertex(p[0], top, p[1], n, sideColour, [0, 0], sid);
      this.indices.push(i0, i1, i2, i0, i2, i3);
      this.line([p[0], top, p[1]], [q[0], top, q[1]], [0, 0]);
    }
  }

  build(spaceIndexByVertex: Int32Array | null): { solid: THREE.BufferGeometry; edges: THREE.BufferGeometry } {
    const solid = new THREE.BufferGeometry();
    solid.setAttribute("position", new THREE.Float32BufferAttribute(this.positions, 3));
    solid.setAttribute("normal", new THREE.Float32BufferAttribute(this.normals, 3));
    solid.setAttribute("color", new THREE.Float32BufferAttribute(this.colours, 3));
    solid.setAttribute("wallNormal", new THREE.Float32BufferAttribute(this.wallNormals, 2));
    solid.setAttribute("spaceIndex", new THREE.Float32BufferAttribute(this.spaceIndices, 1));
    solid.setIndex(this.indices);
    solid.computeBoundingSphere();
    solid.computeBoundsTree();
    void spaceIndexByVertex;
    const edges = new THREE.BufferGeometry();
    edges.setAttribute("position", new THREE.Float32BufferAttribute(this.lines, 3));
    edges.setAttribute("wallNormal", new THREE.Float32BufferAttribute(this.lineWallNormals, 2));
    edges.computeBoundingSphere();
    return { solid, edges };
  }
}

/** Split a wall edge by the doors on it: returns the pieces of [0, 1] (parameter along the edge) that stay wall. */
function wallPieces(a: Point, b: Point, openings: Opening[]): [number, number][] {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const length = Math.hypot(dx, dy);
  if (length < 0.05) return [[0, 1]];
  const gaps: [number, number][] = [];
  for (const opening of openings) {
    const px = opening.position[0] - a[0];
    const py = opening.position[1] - a[1];
    const t = (px * dx + py * dy) / (length * length);
    if (t < -0.02 || t > 1.02) continue;
    const offAxis = Math.abs(px * dy - py * dx) / length;
    if (offAxis > 0.35) continue;
    const half = Math.max(0.45, (opening.width_m ?? 0.9) / 2) / length;
    gaps.push([Math.max(0, t - half), Math.min(1, t + half)]);
  }
  if (!gaps.length) return [[0, 1]];
  gaps.sort((g, h) => g[0] - h[0]);
  const pieces: [number, number][] = [];
  let cursor = 0;
  for (const [start, end] of gaps) {
    if (start > cursor + 0.01) pieces.push([cursor, start]);
    cursor = Math.max(cursor, end);
  }
  if (cursor < 0.99) pieces.push([cursor, 1]);
  return pieces;
}

function lerp(a: Point, b: Point, t: number): Point {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

export function buildFloorGeometry(floor: FloorModel): FloorGeometry {
  const builder = new Builder();
  const wallHeight = wallHeightFor(floor);
  const colourCache = new Map<string, THREE.Color>();
  const colourFor = (hex: string) => {
    let colour = colourCache.get(hex);
    if (!colour) colourCache.set(hex, (colour = new THREE.Color(hex)));
    return colour;
  };
  // Which edges are shared by two rooms (interior) and which face outside.
  const edgeOwners = new Map<string, number>();
  const polygons: Point[][] = floor.spaces.map((space) => ccw(space.polygon));
  polygons.forEach((polygon) => {
    for (let i = 0; i < polygon.length; i++) {
      const key = edgeKey(polygon[i], polygon[(i + 1) % polygon.length]);
      edgeOwners.set(key, (edgeOwners.get(key) ?? 0) + 1);
    }
  });
  const drawnEdges = new Set<string>();
  const openingsBySpace = new Map<string, Opening[]>();
  for (const opening of floor.openings) {
    for (const spaceId of opening.space_ids) {
      const list = openingsBySpace.get(spaceId) ?? [];
      list.push(opening);
      openingsBySpace.set(spaceId, list);
    }
  }
  floor.spaces.forEach((space: Space, sid) => {
    const polygon = polygons[sid];
    if (polygon.length < 3) return;
    const group = spaceGroup(space.type, space.room_type);
    const palette = GROUP_COLOURS[group];
    builder.slab(polygon, 0, colourFor(palette.slab), sid);
    const isOutdoor = space.type === "outdoor";
    const height = isOutdoor ? Math.min(wallHeight, 0.5) : wallHeight;
    const openings = openingsBySpace.get(space.id) ?? [];
    for (let i = 0; i < polygon.length; i++) {
      const a = polygon[i];
      const b = polygon[(i + 1) % polygon.length];
      const key = edgeKey(a, b);
      if (drawnEdges.has(key)) continue;
      drawnEdges.add(key);
      const outer = (edgeOwners.get(key) ?? 1) === 1;
      const dx = b[0] - a[0];
      const dy = b[1] - a[1];
      const length = Math.hypot(dx, dy) || 1;
      // Outward normal in scene xz: model (dy, -dx)/len -> scene (dy, dx)/len (z = -y flips the sign of y).
      const outward: [number, number] = outer ? [dy / length, dx / length] : [0, 0];
      for (const [t0, t1] of wallPieces(a, b, openings)) {
        builder.wallPiece(lerp(a, b, t0), lerp(a, b, t1), 0, height, colourFor(palette.wall), outward, sid, WALL_THICKNESS);
      }
    }
  });
  const { solid, edges } = builder.build(null);
  const spaceIndex = solid.getAttribute("spaceIndex") as THREE.BufferAttribute;
  return {
    solid,
    edges,
    spaceIndexOf: (vertexIndex) => spaceIndex.getX(vertexIndex),
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

/** Injects the dollhouse cutaway: outer walls facing the camera are lowered to CUTAWAY_HEIGHT. */
export function withCutaway<T extends THREE.Material>(material: T, uniforms: { uCamDir: { value: THREE.Vector2 }; uCut: { value: number } }): T {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uCamDir = uniforms.uCamDir;
    shader.uniforms.uCut = uniforms.uCut;
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        `#include <common>
        attribute vec2 wallNormal;
        uniform vec2 uCamDir;
        uniform float uCut;`,
      )
      .replace(
        "#include <begin_vertex>",
        `#include <begin_vertex>
        {
          float facing = dot(wallNormal, uCamDir);
          float cut = step(0.3, facing) * uCut;
          transformed.y = mix(transformed.y, min(transformed.y, ${CUTAWAY_HEIGHT.toFixed(2)}), cut);
        }`,
      );
  };
  material.customProgramCacheKey = () => "cutaway";
  return material;
}
