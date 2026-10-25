import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { Billboard, Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import type { Line2 } from "three-stdlib";
import type { Route, RouteSegment } from "../api/types";
import type { BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";
import { PIN_HEAD_PX, PIN_HEAD_Y_PX, Pulse, START_DOT_PX, ScreenSized } from "./markerLayout";

/** Height of the route line above the floor (m): high enough above the slab that it never flickers with the floor,
 * so in 3D it can be depth-tested (walls hide it); the flat 2D plan draws it without depth test. Labels.tsx anchors a
 * route end's label at the same height. */
export const LIFT = 0.15;
const DRAW_IN_S = 1.4;
/** Route line width on screen (px), 2D and 3D, and its white casing on each side. */
const LINE_PX = 6;
const LINE_PX_3D = 5.5;
const CASING_PX = 2;
/** A soft halo of the signal colour under the casing (px each side) and its opacity. */
const HALO_PX = 7;
const HALO_OPACITY = 0.16;
/** The travelling flow on the line: thin white dashes (px wide, metres long) that move at walking pace. */
const FLOW_PX = 2.2;
const FLOW_DASH_M = 1.0;
const FLOW_GAP_M = 2.2;
const FLOW_SPEED_MPS = 2.4;
const FLOW_OPACITY = 0.6;
/** The destination pin pops when it appears (seconds). */
const POP_S = 0.26;
/** Depth handling of the route lines in one place: hidden by walls in 3D, always on top on the 2D plan. */
const depthOf = (flat: boolean) => ({ depthTest: !flat, depthWrite: false });

interface Props {
  route: Route | null;
  guideSegments: RouteSegment[] | null;
  model: BuildingModel;
  floorY: (floorId: string) => number;
  onlyFloor: string | null;
  reducedMotion: boolean;
  flat?: boolean;
  /** Phones render on demand: the flow animation runs there only while guiding. */
  worker?: boolean;
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
export function RouteLine({ route, guideSegments, model, floorY, onlyFloor, reducedMotion, flat = false, worker = false }: Props) {
  void model;
  const here = useTwin((s) => s.state?.position ?? null);
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

  const halo = useRef<Line2>(null);
  const casing = useRef<Line2>(null);
  const line = useRef<Line2>(null);
  const flow = useRef<Line2>(null);
  const started = useRef(0);
  useEffect(() => {
    started.current = performance.now();
  }, [points]);

  const guided = !!legPoints;
  // The flow keeps asking for frames; on a phone (frameloop "demand") only while guiding, never under reduced motion.
  const flowOn = !reducedMotion && (!worker || guided);
  useFrame(({ invalidate }, delta) => {
    const drawn = reducedMotion ? 1 : Math.min(1, (performance.now() - started.current) / 1000 / DRAW_IN_S);
    if (drawn < 1) invalidate(); // keeps the draw-in moving under frameloop="demand", then stops
    for (const ref of [halo, casing, line]) {
      const material = ref.current?.material as (THREE.ShaderMaterial & { dashOffset: number }) | undefined;
      if (material) material.dashOffset = total * (1 - drawn);
    }
    const flowMaterial = flow.current?.material as (THREE.ShaderMaterial & { dashOffset: number; opacity: number }) | undefined;
    if (flowMaterial) {
      // fades in as the draw-in ends, so the two dash patterns never fight
      flowMaterial.opacity = flowOn ? FLOW_OPACITY * THREE.MathUtils.clamp((drawn - 0.85) / 0.15, 0, 1) : 0;
      if (flowOn) {
        flowMaterial.dashOffset -= FLOW_SPEED_MPS * Math.min(delta, 0.1);
        invalidate();
      }
    }
  });

  if (points.length < 2 || !route?.segments) return null;
  // On a single floor the line may only run to the stairs: the start dot and the destination belong to their own floor.
  const startsHere = !onlyFloor || route.segments[0].floor_id === onlyFloor;
  const endsHere = !onlyFloor || route.segments[route.segments.length - 1].floor_id === onlyFloor;
  // One signal blue in both views, on a white casing (2 px each side) and a soft halo of its own colour under it,
  // so it is the one thing with depth and glow in the picture. Widths are screen px (Line2), so the line keeps its
  // width at any zoom.
  const lineColour = COLOURS.signal;
  const lineWidth = flat ? LINE_PX : LINE_PX_3D;
  const casingWidth = lineWidth + 2 * CASING_PX;
  // "You are here" stands at the start: that dot is the start, no second marker on it.
  const first = route?.segments?.[0];
  const hereAtStart =
    !!here &&
    !!first &&
    here.floor_id === first.floor_id &&
    (here.space_id === route?.start || (!!here.point && Math.hypot(here.point[0] - first.points[0][0], here.point[1] - first.points[0][1]) < 3));
  const depth = depthOf(flat);
  return (
    <group>
      {/* halo: the same line, wide and faint, drawn in with the route (normal blending: additive would vanish on white) */}
      <Line
        ref={halo}
        points={points}
        color={lineColour}
        lineWidth={lineWidth + 2 * HALO_PX}
        transparent
        opacity={guided ? HALO_OPACITY * 0.5 : HALO_OPACITY}
        dashed
        dashSize={total}
        gapSize={total}
        {...depth}
        renderOrder={19}
      />
      <Line
        ref={casing}
        points={points}
        color={COLOURS.routeGlow}
        lineWidth={casingWidth}
        transparent
        opacity={guided ? 0.6 : 1}
        dashed
        dashSize={total}
        gapSize={total}
        {...depth}
        renderOrder={20}
      />
      <Line
        ref={line}
        name="route-line"
        points={points}
        color={lineColour}
        lineWidth={lineWidth}
        transparent
        opacity={guided ? 0.35 : 1}
        dashed
        dashSize={total}
        gapSize={total}
        {...depth}
        renderOrder={21}
      />
      {/* flow: thin white dashes travelling along the line at walking pace (opacity set per frame above) */}
      <Line ref={flow} points={points} color={COLOURS.routeGlow} lineWidth={FLOW_PX} transparent opacity={0} dashed dashSize={FLOW_DASH_M} gapSize={FLOW_GAP_M} {...depth} renderOrder={21.5} />
      {legPoints && (
        <>
          <Line points={legPoints} color={COLOURS.routeGlow} lineWidth={casingWidth} transparent {...depth} renderOrder={22} />
          <Line points={legPoints} color={lineColour} lineWidth={lineWidth} transparent {...depth} renderOrder={23} />
        </>
      )}
      {/* ends: constant size on screen. The start is a paper dot with a blue ring (or nothing when "You are here"
          stands there), the destination a slim red pin on its tip. The room labels move above them (Labels.tsx). */}
      {startsHere && (
        <group position={points[0]} name="route-start">
          {!hereAtStart && (
            <ScreenSized>
              <Pulse reducedMotion={reducedMotion || worker} amount={0.35} speed={1}>
                <EndDisc radius={START_DOT_PX + 8} colour={lineColour} order={23} opacity={0.18} />
              </Pulse>
              <EndDisc radius={START_DOT_PX} colour={lineColour} order={24} />
              <EndDisc radius={START_DOT_PX - 2} colour={COLOURS.routeGlow} order={25} />
            </ScreenSized>
          )}
        </group>
      )}
      {/* the destination in map-app red (its own colour token), only on the floor where the route ends */}
      {endsHere && (
        <group position={points[points.length - 1]} name="route-end">
          <DestinationPin key={`${route.start}|${route.destination}`} colour={COLOURS.destination} reducedMotion={reducedMotion} />
        </group>
      )}
    </group>
  );
}

function EndDisc({ radius, colour, order, opacity = 1 }: { radius: number; colour: string; order: number; opacity?: number }) {
  return (
    <mesh rotation-x={-Math.PI / 2} renderOrder={order}>
      <circleGeometry args={[radius, 32]} />
      <meshBasicMaterial color={colour} transparent opacity={opacity} depthTest={false} depthWrite={false} side={THREE.DoubleSide} />
    </mesh>
  );
}

/** Outline of a pin standing on its tip at (0, 0): a circle of `radius` around (0, `headY`) and the two tangents
 * from the tip to it (px). */
function pinShape(radius: number, headY: number, tipY = 0): THREE.Shape {
  const d = headY - tipY;
  const phi = Math.acos(Math.min(1, radius / d)); // angle between "down" and a tangent point, seen from the centre
  const start = -Math.PI / 2 + phi;
  const shape = new THREE.Shape();
  shape.moveTo(0, tipY);
  shape.lineTo(radius * Math.cos(start), headY + radius * Math.sin(start));
  shape.absarc(0, headY, radius, start, start + 2 * Math.PI - 2 * phi, false);
  shape.lineTo(0, tipY);
  return shape;
}

/** The destination: a slim red pin with a white core on a thin white casing, always upright on screen and
 * at a constant size; its tip marks the spot (on the floor in 3D, on the plan in 2D). */
function DestinationPin({ colour, reducedMotion }: { colour: string; reducedMotion: boolean }) {
  // pops once when it appears (260 ms), then rests at scale 1
  const pop = useRef<THREE.Group>(null);
  const born = useRef(performance.now());
  useFrame(({ invalidate }) => {
    if (!pop.current) return;
    const t = reducedMotion ? 1 : (performance.now() - born.current) / 1000 / POP_S;
    if (t >= 1) {
      pop.current.scale.setScalar(1);
      return;
    }
    pop.current.scale.setScalar(1 + 0.12 * Math.sin(Math.PI * t));
    invalidate();
  });
  const shapes = useMemo(
    () => ({
      casing: new THREE.ShapeGeometry(pinShape(PIN_HEAD_PX + CASING_PX, PIN_HEAD_Y_PX, -CASING_PX * 1.6), 24),
      body: new THREE.ShapeGeometry(pinShape(PIN_HEAD_PX, PIN_HEAD_Y_PX), 24),
      core: new THREE.CircleGeometry(PIN_HEAD_PX * 0.42, 24).translate(0, PIN_HEAD_Y_PX, 0),
    }),
    [],
  );
  useEffect(() => () => Object.values(shapes).forEach((geometry) => geometry.dispose()), [shapes]);
  return (
    <Billboard>
      <ScreenSized uniform>
        <group ref={pop}>
        <mesh geometry={shapes.casing} renderOrder={26}>
          <meshBasicMaterial color={COLOURS.routeGlow} transparent depthTest={false} depthWrite={false} />
        </mesh>
        <mesh geometry={shapes.body} renderOrder={27}>
          <meshBasicMaterial color={colour} transparent depthTest={false} depthWrite={false} />
        </mesh>
        <mesh geometry={shapes.core} renderOrder={28}>
          <meshBasicMaterial color={COLOURS.routeGlow} transparent depthTest={false} depthWrite={false} />
        </mesh>
        </group>
      </ScreenSized>
    </Billboard>
  );
}
