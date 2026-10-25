import { useEffect, useMemo } from "react";
import * as THREE from "three";
import type { Point, Route } from "../api/types";
import { floorElevation, type BuildingModel, type FloorModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin, type FloorMode } from "../store";

/** Where a route changes floor, as seen from one floor: where it leaves ("↑ Floor 1 via Main Stairs") or where it
 * arrives ("↓ from Ground floor, Main Stairs"). The arrow points to the other floor; the stairs or lift is named from
 * the model's connector (the route's own name, else "Stairs" / "Lift"). */
export interface FloorChangeMark {
  key: string;
  connectorId: string;
  point: Point;
  kind: "stairs" | "lift";
  /** the floor at the other end: a tap shows it */
  otherFloor: string;
  leaving: boolean;
  text: string;
}

export function floorChangeMarks(route: Route | null | undefined, floorId: string, model: BuildingModel): FloorChangeMark[] {
  if (!route?.ok) return [];
  const marks: FloorChangeMark[] = [];
  for (const change of route.floor_changes ?? []) {
    const leaving = change.from_floor === floorId;
    if (!leaving && change.to_floor !== floorId) continue;
    const kind = change.kind === "lift" ? "lift" : "stairs";
    const via = model.connectorById.get(change.connector_id)?.name || change.name || (kind === "lift" ? "Lift" : "Stairs");
    const otherFloor = leaving ? change.to_floor : change.from_floor;
    const otherName = model.floorById.get(otherFloor)?.name || otherFloor;
    const up = (change.direction === "up") === leaving;
    marks.push({
      key: `fc-${change.connector_id}-${change.from_floor}-${change.to_floor}-${leaving ? "out" : "in"}`,
      connectorId: change.connector_id,
      point: leaving ? change.from_point : change.to_point,
      kind,
      otherFloor,
      leaving,
      text: leaving ? `${up ? "↑" : "↓"} ${otherName} via ${via}` : `${up ? "↑" : "↓"} from ${otherName}, ${via}`,
    });
  }
  return marks;
}

/** How a floor is drawn in the scene: fully, as a thin footprint outline, or not at all. */
export type FloorRole = "full" | "outline" | "hidden";

/** The floors a route runs over (in route order), or null when it stays on one floor. */
export function routeFloorIds(route: Route | null | undefined): string[] | null {
  if (!route?.ok || !route.segments?.length) return null;
  const ids: string[] = [];
  for (const segment of route.segments) if (!ids.includes(segment.floor_id)) ids.push(segment.floor_id);
  return ids.length >= 2 ? ids : null;
}

/** Identifies a multi-floor route for the rail's "only this floor" choice ("" = no such route). */
export function routeStackKey(route: Route | null | undefined): string {
  const ids = routeFloorIds(route);
  return ids && route?.ok ? `${ids.join("|")}>${route.destination ?? ""}` : "";
}

/** The floors the scene stacks for the shown route, joined by "|" ("" = none): a multi-floor route in 3D, unless the
 * user picked a single floor in the rail for this route (store.routeStackOff). Guidance still moves the focused floor. */
export function useRouteFloorsKey(): string {
  return useTwin((s) => {
    if (s.viewMode === "2d") return "";
    const route = s.state?.route;
    const key = routeStackKey(route);
    if (!key || key === s.routeStackOff) return "";
    return routeFloorIds(route)!.join("|");
  });
}

/** The floor rule (3D):
 * - the active floor is drawn fully, standing on the plinth (Studio.tsx);
 * - floors above and below it are not drawn (the plinth sits right under the active floor and would hide them);
 * - a route over several floors shows only its floors, fully and stacked apart (the only case with two full floors),
 *   until the user picks one floor in the rail (useRouteFloorsKey: then the usual rule applies to that floor);
 * - "all floors" (exploded, no plinth) shows every floor fully, pulled apart (floorLayout): a hairline outline of a
 *   larger floor below (a hall under an office strip) read as a stray frame, not as a floor.
 * The 2D plan shows only the active floor. */
export function floorRoles(model: BuildingModel, focused: string | null, mode: FloorMode, flat: boolean, routeFloors: string[] | null): Map<string, FloorRole> {
  const roles = new Map<string, FloorRole>();
  for (const floor of model.floors) {
    let role: FloorRole;
    if (floor.id === focused) role = "full";
    else if (flat) role = "hidden";
    else if (routeFloors) role = routeFloors.includes(floor.id) ? "full" : "hidden";
    else if (mode === "exploded") role = "full";
    else role = "hidden";
    roles.set(floor.id, role);
  }
  return roles;
}

/** Vertical step between the outlines of the floors below the active one in "all floors" (m): fine lines just under
 * it, not a full storey lower. */
export const OUTLINE_STEP_M = 0.35;

/** Camera tilt (polar angle from straight down, rad) that the route stack is framed at (CameraRig) and laid out for. */
export const STACK_POLAR = 0.95;
/** Share of the worst case (the diagonal straight along the view) the gap covers: the far corner of the lower floor
 * may just touch the near corner of the upper one, the plans and their routes stay apart. */
const STACK_SHARE = 0.8;

/** Vertical gap between two stacked route floors (m): seen from STACK_POLAR, the lower floor's plan must end on screen
 * before the upper floor's begins, whichever way the camera looks. A floor of horizontal extent D projects to about
 * D·cos(polar) on screen, the gap to gap·sin(polar), so gap > D·cot(polar); D is the diagonal of both
 * floors' footprints together (any heading), plus the cut wall height and a little air. */
export function routeStackGap(lower: FloorModel, upper: FloorModel): number {
  // the two floors together (an upper floor may sit off to one side of the one below)
  const width = Math.max(lower.bounds.maxX, upper.bounds.maxX) - Math.min(lower.bounds.minX, upper.bounds.minX);
  const depth = Math.max(lower.bounds.maxY, upper.bounds.maxY) - Math.min(lower.bounds.minY, upper.bounds.minY);
  const extent = Math.hypot(width, depth);
  return Math.max(lower.height_m + 6, (extent / Math.tan(STACK_POLAR)) * STACK_SHARE + lower.height_m);
}

/** Heights of a route's floors stacked apart: the lowest stays at its real elevation, each next one (in floor order)
 * a routeStackGap higher. Floors not on the route keep their real elevation (they are hidden). */
export function routeStackElevations(model: BuildingModel, routeFloors: string[]): Map<string, number> {
  const floors = model.floors.filter((floor) => routeFloors.includes(floor.id)).sort((a, b) => a.elevation_m - b.elevation_m || a.level - b.level);
  const out = new Map<string, number>();
  floors.forEach((floor, i) => out.set(floor.id, i === 0 ? floor.elevation_m : out.get(floors[i - 1].id)! + routeStackGap(floors[i - 1], floor)));
  return out;
}

/** Floor heights: a multi-floor route stacks its floors far enough apart to read each one (routeStackElevations),
 * "all floors" pulls every floor apart; otherwise the real elevations. */
export function floorLayout(floor: FloorModel, model: BuildingModel, mode: FloorMode, routeFloors: string[] | null, focused: string | null = null): number {
  void focused;
  if (routeFloors) return routeStackElevations(model, routeFloors).get(floor.id) ?? floor.elevation_m;
  return floorElevation(floor, model, mode);
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
