// Closed lifts and stairs, and what a route goes around. One place for the "closed" language of the map:
// the stop spaces of a closed connector get the prohibition glyph, the hatched fill and a "Closed" tag
// (scene/Labels.tsx, scene/Markers.tsx); other closed rooms and doors keep the red disc / red bar.

import type { Route } from "../api/types";
import type { BuildingModel } from "./model";

/** Stop spaces of closed lifts and stairs -> the connector's name. A stair or lift space closed by its own id counts too. */
export function closedConnectorStops(model: BuildingModel, closed: readonly string[]): Map<string, string> {
  const out = new Map<string, string>();
  for (const id of closed) {
    const connector = model.connectorById.get(id) ?? model.connectorBySpace.get(id);
    if (!connector) continue;
    const name = connector.name || (connector.kind === "lift" ? "Lift" : "Stairs");
    const stops = model.connectorById.has(id) ? connector.space_ids : [id];
    for (const spaceId of stops) if (model.spaceById.has(spaceId)) out.set(spaceId, name);
  }
  return out;
}

/** Names of the closed elements on the route's floors (the server already routes around every closure). */
export function closedOnRoute(model: BuildingModel, route: Route, closed: readonly string[]): string[] {
  if (!route.ok || !closed.length) return [];
  const floors = new Set(route.floors?.length ? route.floors : (route.segments ?? []).map((segment) => segment.floor_id));
  const names: string[] = [];
  let doors = 0;
  for (const id of closed) {
    const connector = model.connectorById.get(id) ?? model.connectorBySpace.get(id);
    const space = model.spaceById.get(id);
    const opening = model.openingById.get(id);
    if (connector) {
      const onFloors = connector.space_ids.some((spaceId) => floors.has(model.spaceById.get(spaceId)?.floor_id ?? ""));
      if (onFloors) names.push(connector.name || (connector.kind === "lift" ? "Lift" : "Stairs"));
    } else if (space) {
      if (floors.has(space.floor_id)) names.push(space.name || "a room");
    } else if (opening) {
      if (floors.has(opening.floor_id)) doors++;
    }
  }
  const unique = [...new Set(names)];
  if (doors) unique.push(doors === 1 ? "a door" : `${doors} doors`);
  return unique;
}

/** "Avoids closed Lift 1", "Avoids closed Lift 1 and Stairs B", "Avoids 4 closed places"; "" when nothing is closed. */
export function avoidsLine(names: string[]): string {
  if (!names.length) return "";
  if (names.length > 3) return `Avoids ${names.length} closed places`;
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  return `Avoids closed ${list}`;
}
