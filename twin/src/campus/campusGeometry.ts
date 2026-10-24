// Display geometry for the site view: building metres -> campus metres with the building's origin and rotation
// (the same formula as building_agent.campus.world_point). No routing or distances here; those come from the API.

import type { CampusBuilding, CampusLeg, CampusView } from "../api/campus";
import type { Building, Point } from "../api/types";

export function toWorld(building: CampusBuilding, point: Point): Point {
  const [ox, oy] = building.origin ?? [0, 0];
  const angle = (building.rotation_deg * Math.PI) / 180;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  return [ox + point[0] * cos - point[1] * sin, oy + point[0] * sin + point[1] * cos];
}

export interface FloorRings {
  floorId: string;
  level: number;
  elevation: number;
  height: number;
  rings: Point[][]; // room polygons in campus metres
}

/** Every floor of a building as room polygons in campus metres, lowest floor first. */
export function floorRings(building: CampusBuilding, detail: Building | undefined): FloorRings[] {
  if (!detail) return [];
  return [...detail.floors]
    .sort((a, b) => a.level - b.level)
    .map((floor) => ({
      floorId: floor.id,
      level: floor.level,
      elevation: floor.elevation_m,
      height: floor.height_m || 3.5,
      rings: detail.spaces
        .filter((space) => space.floor_id === floor.id && space.type !== "outdoor" && space.polygon.length >= 3)
        .map((space) => space.polygon.map((point) => toWorld(building, point))),
    }));
}

/** The footprint shown on the site map: the ground floor (level 0), else the lowest floor. */
export function groundRings(building: CampusBuilding, detail: Building | undefined): Point[][] {
  const floors = floorRings(building, detail);
  return (floors.find((floor) => floor.level === 0) ?? floors[0])?.rings ?? [];
}

/** Height of floor `level` above the building's ground floor (a bridge with level_delta 1 is one floor up). */
export function levelElevation(building: CampusBuilding | null, level: number): number {
  if (!building || level === 0) return 0;
  const floor = building.floors.find((item) => item.level === level);
  return floor ? floor.elevation_m : level * 3.5;
}

/** The campus route as one line in campus metres (building legs: their world points; links: from -> to). */
export function routeLine(view: CampusView, legs: CampusLeg[]): Point[] {
  const line: Point[] = [];
  const push = (point: Point | null | undefined) => {
    if (!point) return;
    const last = line[line.length - 1];
    if (!last || Math.hypot(last[0] - point[0], last[1] - point[1]) > 0.01) line.push(point);
  };
  for (const leg of legs) {
    if (leg.kind === "link") {
      push(leg.from.world_point);
      push(leg.to.world_point);
    } else {
      const building = view.buildings.find((item) => item.id === leg.building_id);
      if (leg.world_points) leg.world_points.forEach(push);
      else if (building) leg.points.forEach((point) => push(toWorld(building, point)));
    }
  }
  return line;
}

export function boundsOf(points: Point[]) {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  for (const [x, y] of points) {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  if (!isFinite(minX)) return { minX: -50, minY: -50, maxX: 50, maxY: 50 };
  return { minX, minY, maxX, maxY };
}

/** All points worth framing: building outlines and both ends of every link. */
export function campusPoints(view: CampusView, details: Record<string, Building>): Point[] {
  const points: Point[] = [];
  for (const building of view.buildings) {
    for (const ring of groundRings(building, details[building.id])) points.push(...ring);
    if (building.world_center) points.push(building.world_center);
  }
  for (const link of view.links) {
    if (link.from.world_point) points.push(link.from.world_point);
    if (link.to.world_point) points.push(link.to.world_point);
  }
  return points;
}

export function linkIcon(kind: string): string {
  if (kind === "bridge") return "⌒";
  if (kind === "tunnel") return "◡";
  return "";
}
