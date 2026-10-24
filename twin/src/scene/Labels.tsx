import { useMemo, useState } from "react";
import * as THREE from "three";
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import type { FloorModel, BuildingModel } from "../model/model";

interface Props {
  floor: FloorModel;
  model: BuildingModel;
  y: number;
  limit: number;
  flat?: boolean;
}

/** Drops labels whose anchors sit too close to an already kept one (metres), so they never overlap. */
function cullOverlaps<T extends { anchor: [number, number] }>(items: T[], minDistance: number): T[] {
  const kept: T[] = [];
  for (const item of items) {
    if (kept.every((other) => Math.hypot(other.anchor[0] - item.anchor[0], other.anchor[1] - item.anchor[1]) >= minDistance)) kept.push(item);
  }
  return kept;
}

const centre = new THREE.Vector3();

/** Names on the focused floor, by distance: far away only stairs and lifts, closer the biggest rooms, close up
 * every named room (capped). Labels sit above the room anchor and never take pointer events. */
export function Labels({ floor, model, y, limit, flat = false }: Props) {
  const [tier, setTier] = useState(0);
  useFrame(({ camera }) => {
    const size = floor.bounds.size;
    let next: number;
    if ((camera as THREE.OrthographicCamera).isOrthographicCamera) {
      // metres per screen pixel decide what is readable in the plan
      const ortho = camera as THREE.OrthographicCamera;
      const metresPerPixel = (ortho.right - ortho.left) / ortho.zoom / Math.max(1, window.innerWidth);
      next = metresPerPixel > 0.6 ? 0 : metresPerPixel > 0.25 ? 1 : 2;
    } else {
      centre.set(floor.bounds.cx, y, -floor.bounds.cy);
      const distance = camera.position.distanceTo(centre);
      next = distance > size * 1.7 ? 0 : distance > size * 0.9 ? 1 : 2;
    }
    if (next !== tier) setTier(next);
  });
  const labelled = useMemo(() => {
    const named = floor.spaces.filter((space) => space.name && space.type !== "outdoor");
    const connectors = named.filter((space) => model.connectorBySpace.has(space.id)).slice(0, 12);
    const rooms = named
      .filter((space) => !model.connectorBySpace.has(space.id) && space.type !== "corridor")
      .sort((a, b) => b.area_m2 - a.area_m2);
    const lifts = connectors.filter((space) => model.connectorBySpace.get(space.id)?.kind === "lift");
    const size = floor.bounds.size;
    const chosen =
      tier === 0 ? lifts.slice(0, 4) : tier === 1 ? [...connectors.slice(0, 8), ...rooms.slice(0, Math.min(10, limit))] : [...connectors, ...rooms.slice(0, limit)];
    return cullOverlaps(chosen, tier === 0 ? size * 0.08 : tier === 1 ? size * 0.05 : flat ? 2.5 : 3.5);
  }, [floor, model, limit, tier, flat]);
  return (
    <group position-y={y + 0.5}>
      {labelled.map((space) => (
        <Html key={space.id} position={[space.anchor[0], 0, -space.anchor[1]]} center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
          <div className={`label ${model.connectorBySpace.has(space.id) ? "label-connector" : ""}`}>{space.name}</div>
        </Html>
      ))}
    </group>
  );
}
