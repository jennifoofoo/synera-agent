// Derived, read-only view of a building: lookups and bounds, computed once per loaded building.

import type { Asset, Building, Connector, Floor, Opening, Point, Space } from "../api/types";

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  cx: number;
  cy: number;
  size: number;
}

export interface FloorModel extends Floor {
  spaces: Space[];
  openings: Opening[];
  assets: Asset[];
  bounds: Bounds;
  /** Vertical placement in the scene for the current floor mode (set by layout). */
}

export interface BuildingModel {
  building: Building;
  floors: FloorModel[];
  floorById: Map<string, FloorModel>;
  spaceById: Map<string, Space>;
  assetById: Map<string, Asset>;
  openingById: Map<string, Opening>;
  connectorById: Map<string, Connector>;
  bounds: Bounds;
  /** Stair/lift spaces: space id -> connector. */
  connectorBySpace: Map<string, Connector>;
}

export function boundsOf(points: Point[]): Bounds {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  for (const [x, y] of points) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }
  if (!isFinite(minX)) minX = minY = maxX = maxY = 0;
  return { minX, minY, maxX, maxY, cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, size: Math.max(maxX - minX, maxY - minY, 1) };
}

export function buildModel(building: Building): BuildingModel {
  const floors: FloorModel[] = [...building.floors]
    .sort((a, b) => a.level - b.level)
    .map((floor) => ({ ...floor, spaces: [], openings: [], assets: [], bounds: boundsOf([]) }));
  const floorById = new Map(floors.map((floor) => [floor.id, floor]));
  const spaceById = new Map<string, Space>();
  for (const space of building.spaces) {
    spaceById.set(space.id, space);
    floorById.get(space.floor_id)?.spaces.push(space);
  }
  const openingById = new Map<string, Opening>();
  for (const opening of building.openings) {
    openingById.set(opening.id, opening);
    floorById.get(opening.floor_id)?.openings.push(opening);
  }
  const assetById = new Map<string, Asset>();
  for (const asset of building.assets) {
    assetById.set(asset.id, asset);
    floorById.get(asset.floor_id)?.assets.push(asset);
  }
  const connectorById = new Map<string, Connector>();
  const connectorBySpace = new Map<string, Connector>();
  for (const connector of building.connectors) {
    connectorById.set(connector.id, connector);
    for (const spaceId of connector.space_ids) connectorBySpace.set(spaceId, connector);
  }
  for (const floor of floors) floor.bounds = boundsOf(floor.spaces.flatMap((space) => space.polygon));
  const bounds = boundsOf(building.spaces.flatMap((space) => space.polygon));
  return { building, floors, floorById, spaceById, assetById, openingById, connectorById, bounds, connectorBySpace };
}

/** Floor elevations in the scene: as built (stacked / single) or pulled apart (exploded). */
export function floorElevation(floor: FloorModel, model: BuildingModel, mode: "stacked" | "exploded" | "single"): number {
  if (mode !== "exploded") return floor.elevation_m;
  const index = model.floors.indexOf(floor);
  const gap = Math.max(6, model.bounds.size * 0.12);
  return floor.elevation_m + index * gap;
}

export function floorLabel(floor: Floor): string {
  return floor.name || `Level ${floor.level}`;
}
