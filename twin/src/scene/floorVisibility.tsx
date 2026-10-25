import { useEffect, useMemo } from "react";
import * as THREE from "three";
import type { Route } from "../api/types";
import { floorElevation, type BuildingModel, type FloorModel } from "../model/model";
import { COLOURS } from "../model/palette";
import type { FloorMode } from "../store";

/** How a floor is drawn in the scene: fully, as a thin footprint outline, or not at all. */
export type FloorRole = "full" | "outline" | "hidden";

/** The floors a route runs over (in route order), or null when it stays on one floor. */
export function routeFloorIds(route: Route | null | undefined): string[] | null {
  if (!route?.ok || !route.segments?.length) return null;
  const ids: string[] = [];
  for (const segment of route.segments) if (!ids.includes(segment.floor_id)) ids.push(segment.floor_id);
  return ids.length >= 2 ? ids : null;
}

/** The floor rule (3D):
 * - the active floor is drawn fully, standing on the plinth (Studio.tsx);
 * - floors above and below it are not drawn (the plinth sits right under the active floor and would hide them);
 * - a route over several floors shows only its floors, fully and stacked apart (the only case with two full floors);
 * - "all floors" (exploded, no plinth) shows the active floor fully and the others as outlines: floors below as fine
 *   lines just under it, floors above pulled apart (floorLayout).
 * The 2D plan shows only the active floor. */
export function floorRoles(model: BuildingModel, focused: string | null, mode: FloorMode, flat: boolean, routeFloors: string[] | null): Map<string, FloorRole> {
  const roles = new Map<string, FloorRole>();
  for (const floor of model.floors) {
    let role: FloorRole;
    if (floor.id === focused) role = "full";
    else if (flat) role = "hidden";
    else if (routeFloors) role = routeFloors.includes(floor.id) ? "full" : "hidden";
    else if (mode === "exploded") role = "outline";
    else role = "hidden";
    roles.set(floor.id, role);
  }
  return roles;
}

/** Vertical step between the outlines of the floors below the active one in "all floors" (m): fine lines just under
 * it, not a full storey lower. */
export const OUTLINE_STEP_M = 0.35;

/** Floor heights: a multi-floor route pulls its floors apart; "all floors" keeps the active floor at its real height,
 * draws the floors below as outlines a small step under it each and pulls the floors above apart; otherwise the real
 * elevations. */
export function floorLayout(floor: FloorModel, model: BuildingModel, mode: FloorMode, routeFloors: string[] | null, focused: string | null = null): number {
  if (routeFloors) return floorElevation(floor, model, "exploded");
  const active = model.floorById.get(focused ?? "");
  if (mode !== "exploded" || !active) return floorElevation(floor, model, mode);
  const i = model.floors.indexOf(floor);
  const ia = model.floors.indexOf(active);
  if (i === ia) return active.elevation_m;
  if (i < ia) return active.elevation_m - OUTLINE_STEP_M * (ia - i);
  return floorElevation(floor, model, "exploded") - floorElevation(active, model, "exploded") + active.elevation_m;
}

/** The outer edge of a floor: the edges of its space polygons that no other space shares (outdoor areas left out). */
export function footprintSegments(floor: FloorModel): number[] {
  const key = (x: number, y: number) => `${Math.round(x * 20)},${Math.round(y * 20)}`;
  const edges = new Map<string, { a: [number, number]; b: [number, number]; count: number }>();
  for (const space of floor.spaces) {
    if (space.type === "outdoor") continue;
    const ring = space.polygon;
    for (let i = 0; i < ring.length; i++) {
      const a = ring[i];
      const b = ring[(i + 1) % ring.length];
      const ka = key(a[0], a[1]);
      const kb = key(b[0], b[1]);
      if (ka === kb) continue;
      const id = ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`;
      const edge = edges.get(id);
      if (edge) edge.count += 1;
      else edges.set(id, { a: [a[0], a[1]], b: [b[0], b[1]], count: 1 });
    }
  }
  const out: number[] = [];
  for (const { a, b, count } of edges.values()) if (count === 1) out.push(a[0], a[1], b[0], b[1]);
  return out;
}

/** A floor below the active one: only its footprint as a faint line, no walls, no things, not clickable. */
export function FloorOutline({ floor, y }: { floor: FloorModel; y: number }) {
  const geometry = useMemo(() => {
    const flat = footprintSegments(floor);
    const points: number[] = [];
    for (let i = 0; i < flat.length; i += 4) points.push(flat[i], 0.02, -flat[i + 1], flat[i + 2], 0.02, -flat[i + 3]);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
    return g;
  }, [floor]);
  const material = useMemo(() => new THREE.LineBasicMaterial({ color: COLOURS.edge, transparent: true, opacity: 0.55, depthWrite: false }), []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);
  return <lineSegments name={`floor-outline:${floor.id}`} geometry={geometry} material={material} position-y={y} renderOrder={5} raycast={() => null} />;
}
