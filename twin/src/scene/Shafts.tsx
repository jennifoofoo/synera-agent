import { useMemo } from "react";
import type { BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { polygonGeometry } from "./geometry";

interface Props {
  model: BuildingModel;
  floorY: (floorId: string) => number;
  floorTop: (floorId: string) => number;
  closed: Set<string>;
}

/** Stairs and lifts as see-through shafts between their stop floors (closed ones red). */
export function Shafts({ model, floorY, floorTop, closed }: Props) {
  const shafts = useMemo(() => {
    return model.building.connectors.flatMap((connector) => {
      const stops = connector.space_ids.map((id) => model.spaceById.get(id)).filter((s): s is NonNullable<typeof s> => !!s);
      if (stops.length < 2) return [];
      const sorted = [...stops].sort((a, b) => (model.floorById.get(a.floor_id)?.level ?? 0) - (model.floorById.get(b.floor_id)?.level ?? 0));
      const bottom = sorted[0];
      const top = sorted[sorted.length - 1];
      return [{ connector, polygon: bottom.polygon, bottomFloor: bottom.floor_id, topFloor: top.floor_id }];
    });
  }, [model]);
  return (
    <group>
      {shafts.map(({ connector, polygon, bottomFloor, topFloor }) => {
        const y0 = floorY(bottomFloor);
        const y1 = floorTop(topFloor);
        const height = Math.max(0.5, y1 - y0);
        const isClosed = closed.has(connector.id);
        return <Shaft key={connector.id} polygon={polygon} y={y0} height={height} colour={isClosed ? COLOURS.danger : connector.kind === "lift" ? COLOURS.accentBlue : COLOURS.accent} opacity={isClosed ? 0.3 : 0.1} />;
      })}
    </group>
  );
}

function Shaft({ polygon, y, height, colour, opacity }: { polygon: [number, number][]; y: number; height: number; colour: string; opacity: number }) {
  const geometry = useMemo(() => polygonGeometry(polygon, height), [polygon, height]);
  return (
    <mesh geometry={geometry} position-y={y} renderOrder={8}>
      <meshBasicMaterial color={colour} transparent opacity={opacity} depthWrite={false} />
    </mesh>
  );
}
