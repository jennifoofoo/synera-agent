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
}

const centre = new THREE.Vector3();

/** Names on the focused floor, by distance: far away only stairs and lifts, closer the biggest rooms, close up
 * every named room (capped). Labels sit above the room anchor and never take pointer events. */
export function Labels({ floor, model, y, limit }: Props) {
  const [tier, setTier] = useState(0);
  useFrame(({ camera }) => {
    centre.set(floor.bounds.cx, y, -floor.bounds.cy);
    const distance = camera.position.distanceTo(centre);
    const size = floor.bounds.size;
    const next = distance > size * 1.7 ? 0 : distance > size * 0.9 ? 1 : 2;
    if (next !== tier) setTier(next);
  });
  const labelled = useMemo(() => {
    const named = floor.spaces.filter((space) => space.name && space.type !== "outdoor");
    const connectors = named.filter((space) => model.connectorBySpace.has(space.id)).slice(0, 12);
    const rooms = named
      .filter((space) => !model.connectorBySpace.has(space.id) && space.type !== "corridor")
      .sort((a, b) => b.area_m2 - a.area_m2);
    const lifts = connectors.filter((space) => model.connectorBySpace.get(space.id)?.kind === "lift");
    if (tier === 0) return lifts.slice(0, 4);
    if (tier === 1) return [...connectors.slice(0, 8), ...rooms.slice(0, Math.min(10, limit))];
    return [...connectors, ...rooms.slice(0, limit)];
  }, [floor, model, limit, tier]);
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
