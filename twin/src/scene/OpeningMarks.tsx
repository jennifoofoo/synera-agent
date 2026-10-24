// Marks on openings that the wall geometry cannot carry: a closed door or opening gets a short bar across its gap in
// the closed red. (Jamb ticks, hall zone lines and the step-free glyph live in geometry.ts and Labels.tsx.)

import { useMemo } from "react";
import type { BuildingState, Opening, Point } from "../api/types";
import type { BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { openingCuts } from "./geometry";

interface Props {
  model: BuildingModel;
  state: BuildingState | null;
  floorY: (floorId: string) => number;
  visibleFloors: Set<string>;
}

interface Bar {
  id: string;
  floor_id: string;
  from: Point;
  to: Point;
}

export function OpeningMarks({ model, state, floorY, visibleFloors }: Props) {
  const bars = useMemo(() => {
    const list: Bar[] = [];
    for (const id of state?.closed ?? []) {
      const added = state?.added_doors.find((door) => door.id === id);
      const opening: Opening | undefined = model.openingById.get(id) ?? (added ? { ...added, kind: "door", width_m: 0.9, added: true } : undefined);
      if (!opening) continue;
      const polygons = opening.space_ids.map((spaceId) => model.spaceById.get(spaceId)?.polygon).filter((polygon): polygon is Point[] => !!polygon);
      const cut = openingCuts(opening, polygons)[0];
      if (cut) list.push({ id, floor_id: opening.floor_id, from: cut.gap[0], to: cut.gap[1] });
    }
    return list;
  }, [model, state?.closed, state?.added_doors]);

  return (
    <group>
      {bars
        .filter((bar) => visibleFloors.has(bar.floor_id))
        .map((bar) => {
          const length = Math.hypot(bar.to[0] - bar.from[0], bar.to[1] - bar.from[1]);
          return (
            <mesh
              key={bar.id}
              name="closed-bar"
              position={[(bar.from[0] + bar.to[0]) / 2, floorY(bar.floor_id) + 0.2, -(bar.from[1] + bar.to[1]) / 2]}
              rotation-y={Math.atan2(bar.to[1] - bar.from[1], bar.to[0] - bar.from[0])}
              renderOrder={16}
            >
              <boxGeometry args={[Math.max(0.3, length), 0.4, 0.22]} />
              <meshBasicMaterial color={COLOURS.danger} depthTest={false} />
            </mesh>
          );
        })}
    </group>
  );
}
