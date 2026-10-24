// Probe for the drawn-vs-data audit (scripts/twin_audit.sh, tests/e2e/test_twin_audit.py): `window.__twinAudit`
// reads what is actually in the three.js scene (not the data) so a test can compare it with the API.
// Read-only; nothing in the app uses it. Scene objects it relies on: group `floor:<id>` (FloorMesh), the Line2 named
// `route-line` (RouteLine), groups named `closed-marker` (Markers) and the instanced meshes of Things.

import * as THREE from "three";
import { useTwin } from "./store";

type Pt = [number, number];

function sceneRoot(): THREE.Object3D | null {
  return (window as unknown as { __twinScene?: THREE.Object3D }).__twinScene ?? null;
}

/** Model point -> scene xz. */
const toScene = (p: Pt): Pt => [p[0], -p[1]];

function floorGroups(): Map<string, THREE.Object3D> {
  const found = new Map<string, THREE.Object3D>();
  sceneRoot()?.traverse((o) => {
    if (o.name.startsWith("floor:")) found.set(o.name.slice(6), o);
  });
  return found;
}

function inTriangle(p: Pt, a: Pt, b: Pt, c: Pt, tol: number): boolean {
  const d = (q: Pt, r: Pt) => (p[0] - r[0]) * (q[1] - r[1]) - (q[0] - r[0]) * (p[1] - r[1]);
  const area = Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]));
  if (area < 1e-6) return false; // vertical faces project to nothing
  const d1 = d(a, b);
  const d2 = d(b, c);
  const d3 = d(c, a);
  const neg = d1 < -tol || d2 < -tol || d3 < -tol;
  const pos = d1 > tol || d2 > tol || d3 > tol;
  return !(neg && pos);
}

/** Whether the floor's rendered geometry has a wall top or any edge line at the model point. */
export function blockedAt(floorId: string, point: Pt, radius = 0.04): { wall: boolean; line: boolean } {
  const group = floorGroups().get(floorId);
  const result = { wall: false, line: false };
  if (!group) return result;
  const p = toScene(point);
  group.traverse((o) => {
    const mesh = o as THREE.Mesh;
    const geometry = mesh.geometry as THREE.BufferGeometry | undefined;
    if (!geometry) return;
    if ((o as THREE.LineSegments).isLineSegments) {
      const pos = geometry.getAttribute("position");
      for (let i = 0; i + 1 < pos.count && !result.line; i += 2) {
        const ax = pos.getX(i), az = pos.getZ(i), bx = pos.getX(i + 1), bz = pos.getZ(i + 1);
        const dx = bx - ax, dz = bz - az;
        const len2 = dx * dx + dz * dz || 1e-9;
        const t = Math.max(0, Math.min(1, ((p[0] - ax) * dx + (p[1] - az) * dz) / len2));
        if (Math.hypot(ax + dx * t - p[0], az + dz * t - p[1]) <= radius) result.line = true;
      }
    } else if (mesh.isMesh && geometry.getAttribute("wall")) {
      const pos = geometry.getAttribute("position");
      const wall = geometry.getAttribute("wall");
      const index = geometry.getIndex();
      const count = index ? index.count : pos.count;
      for (let i = 0; i + 2 < count && !result.wall; i += 3) {
        const [i0, i1, i2] = index ? [index.getX(i), index.getX(i + 1), index.getX(i + 2)] : [i, i + 1, i + 2];
        if (wall.getX(i0) < 0.5 || wall.getX(i1) < 0.5 || wall.getX(i2) < 0.5) continue;
        if (inTriangle(p, [pos.getX(i0), pos.getZ(i0)], [pos.getX(i1), pos.getZ(i1)], [pos.getX(i2), pos.getZ(i2)], 1e-4)) result.wall = true;
      }
    }
  });
  return result;
}

/** The route line as drawn: x/z of each vertex converted back to model metres. */
export function drawnRoute(): Pt[] {
  let points: Pt[] = [];
  sceneRoot()?.traverse((o) => {
    if (o.name !== "route-line") return;
    const geometry = (o as THREE.Mesh).geometry as THREE.BufferGeometry;
    const start = geometry.getAttribute("instanceStart") as THREE.BufferAttribute | undefined;
    const end = geometry.getAttribute("instanceEnd") as THREE.BufferAttribute | undefined;
    if (!start || !end || !start.count) return;
    const out: Pt[] = [];
    for (let i = 0; i < start.count; i++) out.push([start.getX(i), -start.getZ(i)]);
    out.push([end.getX(end.count - 1), -end.getZ(end.count - 1)]);
    points = out;
  });
  return points;
}

/** Instances of things drawn (the solid instanced meshes, not their outline hulls). */
export function drawnThings(): number {
  let total = 0;
  sceneRoot()?.traverse((o) => {
    const mesh = o as THREE.InstancedMesh;
    if (!mesh.isInstancedMesh) return;
    const material = mesh.material as THREE.Material;
    if (material.side === THREE.BackSide) return;
    total += mesh.count;
  });
  return total;
}

/** Closed-element markers: one per cluster, `elements` = elements in them. */
export function drawnClosed(): { markers: number; elements: number } {
  let markers = 0;
  let elements = 0;
  sceneRoot()?.traverse((o) => {
    if (o.name === "closed-marker") {
      markers++;
      elements += Number(o.userData.count ?? 1);
    }
  });
  return { markers, elements };
}

/** Number of distinct spaces with at least one drawn vertex across all mounted floors. */
export function drawnSpaces(): number {
  const seen = new Set<string>();
  const model = useTwin.getState().model;
  if (!model) return 0;
  for (const [floorId, group] of floorGroups()) {
    const floor = model.floorById.get(floorId);
    if (!floor) continue;
    group.traverse((o) => {
      const mesh = o as THREE.Mesh;
      const index = mesh.geometry?.getAttribute("spaceIndex");
      if (!index || !mesh.isMesh) return;
      for (let i = 0; i < index.count; i++) {
        const space = floor.spaces[index.getX(i)];
        if (space) seen.add(space.id);
      }
    });
  }
  return seen.size;
}

if (typeof window !== "undefined") {
  (window as unknown as { __twinAudit: unknown }).__twinAudit = { store: useTwin, blockedAt, drawnRoute, drawnThings, drawnClosed, drawnSpaces };
}
