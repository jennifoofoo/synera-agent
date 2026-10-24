import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import type { Line2 } from "three-stdlib";
import type { Route, RouteSegment } from "../api/types";
import type { BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";

const LIFT = 0.4;

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

/** The route as a glowing line through the floors (vertical runs at stairs and lifts), drawn in, then a pulse
 * travels along it. With reduced motion the line is simply there. */
export function RouteLine({ route, guideSegments, model, floorY, onlyFloor, reducedMotion, flat = false }: Props) {
  void model;
  const points = useMemo(() => (route?.ok && route.segments ? toPoints(route.segments, floorY, onlyFloor) : []), [route, floorY, onlyFloor]);
  const guidePoints = useMemo(() => (guideSegments ? toPoints(guideSegments, floorY, onlyFloor) : []), [guideSegments, floorY, onlyFloor]);
  const lengths = useMemo(() => {
    const cumulative = [0];
    for (let i = 1; i < points.length; i++) cumulative.push(cumulative[i - 1] + points[i].distanceTo(points[i - 1]));
    return cumulative;
  }, [points]);
  const total = lengths[lengths.length - 1] ?? 0;
  const line = useRef<Line2>(null);
  const glow = useRef<Line2>(null);
  const pulse = useRef<THREE.Mesh>(null);
  const started = useRef(0);
  useEffect(() => {
    started.current = performance.now();
  }, [points]);

  useFrame(({ invalidate }) => {
    const elapsed = (performance.now() - started.current) / 1000;
    const drawn = reducedMotion ? 1 : Math.min(1, elapsed / 1.4);
    if (!reducedMotion && points.length > 1) invalidate(); // keeps the draw-in and the pulse moving under frameloop="demand"
    for (const ref of [line, glow]) {
      const material = ref.current?.material as THREE.ShaderMaterial & { dashOffset: number } | undefined;
      if (material) material.dashOffset = total * (1 - drawn);
    }
    if (pulse.current && points.length > 1) {
      if (reducedMotion || drawn < 1) {
        pulse.current.visible = false;
        return;
      }
      pulse.current.visible = true;
      const speed = Math.max(4, total / 8);
      const distance = ((elapsed - 1.4) * speed) % total;
      let i = 1;
      while (i < lengths.length - 1 && lengths[i] < distance) i++;
      const t = (distance - lengths[i - 1]) / Math.max(1e-6, lengths[i] - lengths[i - 1]);
      pulse.current.position.lerpVectors(points[i - 1], points[i], THREE.MathUtils.clamp(t, 0, 1));
    }
  });

  if (points.length < 2) return null;
  const guided = guidePoints.length > 1;
  const lineColour = flat ? COLOURS.mapBlue : COLOURS.route;
  const casingColour = flat ? COLOURS.mapBlueDark : COLOURS.routeGlow;
  return (
    <group>
      <Line
        ref={glow}
        points={points}
        color={casingColour}
        lineWidth={flat ? (guided ? 7 : 9) : guided ? 5 : 9}
        transparent
        opacity={flat ? (guided ? 0.5 : 1) : guided ? 0.18 : 0.28}
        dashed
        dashSize={total}
        gapSize={total}
        depthTest={false}
        renderOrder={20}
      />
      <Line
        ref={line}
        name="route-line"
        points={points}
        color={lineColour}
        lineWidth={flat ? (guided ? 4 : 6) : guided ? 2 : 3.5}
        transparent
        opacity={guided ? 0.55 : 1}
        dashed
        dashSize={total}
        gapSize={total}
        depthTest={false}
        renderOrder={21}
      />
      {guided && <Line points={guidePoints} color={lineColour} lineWidth={flat ? 7 : 5} depthTest={false} renderOrder={22} />}
      <mesh ref={pulse} renderOrder={23}>
        <sphereGeometry args={[0.35, 12, 12]} />
        <meshBasicMaterial color={flat ? "#ffffff" : COLOURS.routeGlow} depthTest={false} transparent opacity={0.95} />
      </mesh>
      <mesh position={points[0]} renderOrder={23}>
        <sphereGeometry args={[0.45, 14, 14]} />
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
