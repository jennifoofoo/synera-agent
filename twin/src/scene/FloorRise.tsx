import { useFrame, useThree } from "@react-three/fiber";
import { useLayoutEffect, useRef, type ReactNode } from "react";
import type { Group } from "three";
import { useTwin } from "../store";

const RISE_MS = 600;
const FLAT = 0.02;

/** Wraps a floor and makes it rise out of its ground (scale.y 0.02 to 1, cubic ease-out) when `active` turns true.
 *  The children keep their own world y: the pivot is moved to `y` and back. */
export function FloorRise({ active, y, children }: { active: boolean; y: number; children: ReactNode }) {
  const reducedMotion = useTwin((s) => s.reducedMotion);
  const invalidate = useThree((s) => s.invalidate);
  const scaler = useRef<Group>(null);
  const start = useRef<number | null>(null);

  useLayoutEffect(() => {
    const group = scaler.current;
    if (!group) return;
    if (active && !reducedMotion) {
      start.current = performance.now();
      group.scale.y = FLAT;
      invalidate();
    } else {
      start.current = null;
      group.scale.y = 1;
    }
  }, [active, reducedMotion, invalidate]);

  useFrame(() => {
    const group = scaler.current;
    if (!group || start.current === null) return;
    const t = Math.min(1, (performance.now() - start.current) / RISE_MS);
    group.scale.y = FLAT + (1 - FLAT) * (1 - (1 - t) ** 3);
    // One more frame after the end: on demand (phones) the map is drawn at full height without waiting for input.
    if (t >= 1) start.current = null;
    invalidate();
  });

  return (
    <group position-y={y}>
      <group ref={scaler}>
        <group position-y={-y}>{children}</group>
      </group>
    </group>
  );
}
