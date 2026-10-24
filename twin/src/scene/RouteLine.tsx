import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import type { Line2 } from "three-stdlib";
import type { Route, RouteSegment } from "../api/types";
import type { BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";

const LIFT = 0.4;
const DRAW_IN_S = 1.4;

interface Props {
  route: Route | null;
  guideSegments: RouteSegment[] | null;
  model: BuildingModel;
  floorY: (floorId: string) => number;
  onlyFloor: string | null;
  reducedMotion: boolean;
  flat?: boolean;
}

function toPoints(segments: RouteSegment[], floorY: (id: string) => number, onlyFloor: string | null): THREE.Vector3[] {
  const points: THREE.Vector3[] = [];
  for (const segment of segments) {
    if (onlyFloor && segment.floor_id !== onlyFloor) continue;
    const y = floorY(segment.floor_id) + LIFT;
    for (const [x, z] of segment.points) points.push(new THREE.Vector3(x, y, -z));
  }
  return points;
}

const closest = new THREE.Vector3();
const segment = new THREE.Line3();

/** Distance along the polyline (cumulative `lengths`) of the point on it nearest to `target`. */
function project(points: THREE.Vector3[], lengths: number[], target: THREE.Vector3): number {
  let best = Infinity;
  let along = 0;
  for (let i = 1; i < points.length; i++) {
    segment.set(points[i - 1], points[i]);
    const t = segment.closestPointToPointParameter(target, true);
    segment.at(t, closest);
    const distance = closest.distanceToSquared(target);
    if (distance < best) {
      best = distance;
      along = lengths[i - 1] + t * (lengths[i] - lengths[i - 1]);
    }
  }
  return along;
}

/** The part of the polyline between the distances s0 and s1 (same points, so it lies exactly on the line). */
function slice(points: THREE.Vector3[], lengths: number[], s0: number, s1: number): THREE.Vector3[] {
  const at = (s: number) => {
    let i = 1;
    while (i < lengths.length - 1 && lengths[i] < s) i++;
    const t = (s - lengths[i - 1]) / Math.max(1e-6, lengths[i] - lengths[i - 1]);
    return new THREE.Vector3().lerpVectors(points[i - 1], points[i], THREE.MathUtils.clamp(t, 0, 1));
  };
  const result = [at(s0)];
  for (let i = 0; i < points.length; i++) if (lengths[i] > s0 && lengths[i] < s1) result.push(points[i]);
  result.push(at(s1));
  return result;
}

/** The route as ONE line with a casing, like a map app (vertical runs at stairs and lifts in 3D), drawn in once.
 * The server's guide leg (door to door) is not drawn as a path of its own: during guidance the part of the route
 * that the current leg covers is emphasised on the same line and the rest is paler. */
export function RouteLine({ route, guideSegments, model, floorY, onlyFloor, reducedMotion, flat = false }: Props) {
  void model;
  const points = useMemo(() => (route?.ok && route.segments ? toPoints(route.segments, floorY, onlyFloor) : []), [route, floorY, onlyFloor]);
  const lengths = useMemo(() => {
    const cumulative = [0];
    for (let i = 1; i < points.length; i++) cumulative.push(cumulative[i - 1] + points[i].distanceTo(points[i - 1]));
    return cumulative;
  }, [points]);
  const total = lengths[lengths.length - 1] ?? 0;
  const legPoints = useMemo(() => {
    if (!guideSegments || points.length < 2) return null;
    const leg = toPoints(guideSegments, floorY, onlyFloor);
    if (leg.length < 2) return null;
    const a = project(points, lengths, leg[0]);
    const b = project(points, lengths, leg[leg.length - 1]);
    const [s0, s1] = a <= b ? [a, b] : [b, a];
    return s1 - s0 > 0.5 ? slice(points, lengths, s0, s1) : null;
  }, [guideSegments, points, lengths, floorY, onlyFloor]);

  const casing = useRef<Line2>(null);
  const line = useRef<Line2>(null);
  const started = useRef(0);
  useEffect(() => {
    started.current = performance.now();
  }, [points]);

  useFrame(({ invalidate }) => {
    const drawn = reducedMotion ? 1 : Math.min(1, (performance.now() - started.current) / 1000 / DRAW_IN_S);
    if (drawn < 1) invalidate(); // keeps the draw-in moving under frameloop="demand", then stops
    for (const ref of [casing, line]) {
      const material = ref.current?.material as (THREE.ShaderMaterial & { dashOffset: number }) | undefined;
      if (material) material.dashOffset = total * (1 - drawn);
    }
  });

  if (points.length < 2) return null;
  const guided = !!legPoints;
  const lineColour = flat ? COLOURS.mapBlue : COLOURS.route;
  // 2D: Google-Maps blue on a white casing. 3D: the teal route on a light casing.
  const casingColour = flat ? "#ffffff" : COLOURS.routeGlow;
  const casingWidth = flat ? 9 : 6;
  const lineWidth = flat ? 5.5 : 3.5;
  return (
    <group>
      <Line
        ref={casing}
        points={points}
        color={casingColour}
        lineWidth={casingWidth}
        transparent={!flat}
        opacity={flat ? 1 : 0.5}
        dashed
        dashSize={total}
        gapSize={total}
        depthTest={false}
        renderOrder={20}
      />
      <Line
        ref={line}
        points={points}
        color={lineColour}
        lineWidth={lineWidth}
        transparent
        opacity={guided ? 0.6 : 1}
        dashed
        dashSize={total}
        gapSize={total}
        depthTest={false}
        renderOrder={21}
      />
      {legPoints && <Line points={legPoints} color={lineColour} lineWidth={lineWidth} depthTest={false} renderOrder={22} />}
      {/* start: a small dot in the line colour with a white rim */}
      <mesh position={points[0]} renderOrder={23}>
        <sphereGeometry args={[0.55, 16, 16]} />
        <meshBasicMaterial color="#ffffff" depthTest={false} />
      </mesh>
      <mesh position={points[0]} renderOrder={24}>
        <sphereGeometry args={[0.38, 16, 16]} />
        <meshBasicMaterial color={lineColour} depthTest={false} />
      </mesh>
      {flat ? (
        <group position={points[points.length - 1]} renderOrder={23}>
          {/* a red pin: ball on a short stem */}
          <mesh position-y={1.6}>
            <sphereGeometry args={[0.7, 16, 16]} />
            <meshBasicMaterial color={COLOURS.mapRed} depthTest={false} />
          </mesh>
          <mesh position-y={0.8}>
            <coneGeometry args={[0.35, 1.4, 12]} />
            <meshBasicMaterial color={COLOURS.mapRed} depthTest={false} />
          </mesh>
          <mesh position-y={1.6}>
            <sphereGeometry args={[0.25, 10, 10]} />
            <meshBasicMaterial color="#ffffff" depthTest={false} />
          </mesh>
        </group>
      ) : (
        <mesh position={points[points.length - 1]} renderOrder={23}>
          <coneGeometry args={[0.55, 1.1, 4]} />
          <meshBasicMaterial color={lineColour} depthTest={false} />
        </mesh>
      )}
    </group>
  );
}
