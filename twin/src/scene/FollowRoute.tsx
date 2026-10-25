// Route extras while Guide me walks (FollowCam.tsx): the part of the line already walked fades out, and the next
// turn or landmark gets a small chip at the point where the current step ends. Both are drawn by RouteLine.

import { useMemo, useRef } from "react";
import * as THREE from "three";
import { Html, Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import type { Line2 } from "three-stdlib";
import type { Route } from "../api/types";
import { COLOURS } from "../model/palette";
import { useTwin, walkSteps } from "../store";
import { TurnIcon, rideUp } from "../ui/Walk";
import { readable } from "../walkInfo";
import { honestLine, useWalkMotion } from "../walkWithMe";
import { buildFollowPath, newPathPoint, pointOnPath } from "./followPath";

const WALKED_GREY = "#8a9099";
const WALKED_OPACITY = 0.35;
/** Above the route's own lines and flow (19 to 21.5), below the guide leg (22, 23). */
const WALKED_ORDER = 21.6;

const closest = new THREE.Vector3();
const segment = new THREE.Line3();
const dot = new THREE.Vector3();

/** Distance along the polyline of the point on it nearest to `target` (like RouteLine's project). */
function along(points: THREE.Vector3[], lengths: number[], target: THREE.Vector3): number {
  let best = Infinity;
  let result = 0;
  for (let i = 1; i < points.length; i++) {
    segment.set(points[i - 1], points[i]);
    const t = segment.closestPointToPointParameter(target, true);
    segment.at(t, closest);
    const distance = closest.distanceToSquared(target);
    if (distance < best) {
      best = distance;
      result = lengths[i - 1] + t * (lengths[i] - lengths[i - 1]);
    }
  }
  return result;
}

interface WalkedProps {
  points: THREE.Vector3[];
  lengths: number[];
  floorY: (floorId: string) => number;
  lift: number;
  lineWidth: number;
  casingWidth: number;
  depthTest: boolean;
}

/** The walked part: the same line again, dashed so that only the first `walked` metres show (dash = walked,
 * gap = the whole line), white over the blue and a grey line on it. Updated per frame without new geometry. */
export function WalkedLine({ points, lengths, floorY, lift, lineWidth, casingWidth, depthTest }: WalkedProps) {
  const walking = useTwin((s) => s.walkStep !== null);
  const wash = useRef<Line2>(null);
  const grey = useRef<Line2>(null);
  const total = lengths[lengths.length - 1] ?? 0;
  const seen = useRef<{ estimate: unknown; walked: number }>({ estimate: null, walked: 0 });
  useFrame(() => {
    const estimate = useWalkMotion.getState().estimate;
    const show = walking && !!estimate;
    if (show && estimate !== seen.current.estimate) {
      dot.set(estimate.point[0], floorY(estimate.floorId) + lift, -estimate.point[1]);
      seen.current.walked = along(points, lengths, dot);
    }
    seen.current.estimate = estimate;
    for (const ref of [wash, grey]) {
      const line = ref.current;
      if (!line) continue;
      line.visible = show && seen.current.walked > 0.05;
      const material = line.material as THREE.ShaderMaterial & { dashSize: number; gapSize: number };
      material.dashSize = Math.max(1e-3, seen.current.walked);
      material.gapSize = total + 1;
    }
  });
  if (!walking || points.length < 2) return null;
  const depth = { depthTest, depthWrite: false };
  return (
    <group name="route-walked">
      <Line ref={wash} points={points} color={COLOURS.routeGlow} lineWidth={casingWidth} transparent opacity={0.7} dashed dashSize={1e-3} gapSize={total + 1} {...depth} renderOrder={WALKED_ORDER} />
      <Line ref={grey} points={points} color={WALKED_GREY} lineWidth={lineWidth} transparent opacity={WALKED_OPACITY} dashed dashSize={1e-3} gapSize={total + 1} {...depth} renderOrder={WALKED_ORDER + 0.05} />
    </group>
  );
}

/** "Walk about 14 m via Office corridor 1.01 into Meeting room 1.06." -> "Walk about 14 m via Office corridor 1.01". */
function shortLine(line: string): string {
  const first = line.replace(/\.$/, "").split(/(?:\. |, | into | to (?=[A-Z]))/)[0];
  const text = first.length >= 8 ? first : line.replace(/\.$/, "");
  return text.length > 34 ? `${text.slice(0, 32).trimEnd()}…` : text;
}

interface BadgeProps {
  route: Route | null;
  floorY: (floorId: string) => number;
  onlyFloor: string | null;
  lift: number;
}

/** The next step as a chip where the current step ends: the turn, the stairs or the lift. Not for the arrival
 * (the destination pin is the landmark there) and not while standing at stairs/lift (the sheet says it). */
export function NextTurnBadge({ route, floorY, onlyFloor, lift }: BadgeProps) {
  const step = useTwin((s) => s.walkStep);
  const walking = step !== null;
  const path = useMemo(() => (walking && route?.ok ? buildFollowPath(route) : null), [walking, route]);
  const badge = useMemo(() => {
    if (step === null || !path || !route) return null;
    const lines = walkSteps().map(readable).map(honestLine);
    const now = path.plan.steps[step];
    const next = lines[step + 1];
    if (!now || !next || now.kind === "ride" || /arrived|should be about here/i.test(next)) return null;
    const at = pointOnPath(path, now.endM, now.group, newPathPoint());
    return { at, next, up: rideUp(route.floor_changes, lines, step + 1) };
  }, [step, path, route]);
  if (!badge || (onlyFloor && badge.at.floorId !== onlyFloor)) return null;
  return (
    <Html position={[badge.at.x, floorY(badge.at.floorId) + lift, -badge.at.y]} center zIndexRange={[6, 0]} style={{ pointerEvents: "none" }}>
      <span className="chip chip-route" data-next-turn style={{ transform: "translateY(-18px)", whiteSpace: "nowrap" }}>
        <TurnIcon line={badge.next} up={badge.up} />
        {shortLine(badge.next)}
      </span>
    </Html>
  );
}
