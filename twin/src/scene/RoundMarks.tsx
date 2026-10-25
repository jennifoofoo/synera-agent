// The what-if door of an inspection round (owner: round session): a pulsing blue ring on the new door, so the
// change that shortened the round is easy to find. Rings and pulse from Markers.tsx (imported, not changed).

import { useRound } from "../round/round";
import { Disc, Pulse, Ring } from "./Markers";

const BLUE = "#004fab";

export function RoundMarks({ floorY, visibleFloors, reducedMotion }: { floorY: (floorId: string) => number; visibleFloors: Set<string>; reducedMotion: boolean }) {
  const whatIf = useRound((s) => s.whatIf);
  if (!whatIf?.position || !visibleFloors.has(whatIf.floorId)) return null;
  const [x, y] = whatIf.position;
  return (
    <group position={[x, floorY(whatIf.floorId) + 0.1, -y]}>
      <Pulse reducedMotion={reducedMotion} speed={1.2} amount={0.25}>
        <Ring radius={1.6} colour={BLUE} width={0.28} through />
        <Disc radius={1.3} colour={BLUE} opacity={0.18} through />
      </Pulse>
    </group>
  );
}
