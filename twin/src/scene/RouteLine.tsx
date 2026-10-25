import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Billboard, Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import type { Line2 } from "three-stdlib";
import type { Route, RouteSegment } from "../api/types";
import type { BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";
import { PIN_HEAD_PX, PIN_HEAD_Y_PX, START_DOT_PX, ScreenSized } from "./markerLayout";
import { NextTurnBadge, WalkedLine } from "./FollowRoute";
import { ROUTE_CASING_PX, ROUTE_LINE_PX, routeLayers, simplifyPolyline } from "./routeLook";

/** Height of the route line above the floor (m): high enough above the slab that it never flickers with the floor,
 * so in 3D it can be depth-tested (walls hide it); the flat 2D plan draws it without depth test. Labels.tsx anchors a
 * route end's label at the same height. */
export const LIFT = 0.15;
const DRAW_IN_S = 1.0;
/** The pin's white casing (px). */
const CASING_PX = 1.5;
/** The destination pin pops when it appears (seconds). */
const POP_S = 0.26;
/** The route lies on the floor like a map app's line, in 2D and 3D alike: never cut into pieces by walls or
 * furniture, above the room fills, below the labels (HTML). */
const DEPTH = { depthTest: false, depthWrite: false } as const;

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
    for (const [x, z] of simplifyPolyline(segment.points)) points.push(new THREE.Vector3(x, y, -z));
  }
  return points;
}

/** The runs between floors of a stacked route (3D, all its floors drawn): from the last point on one floor to the
 * first on the next, as pairs [from, to, from, to, ...] for one LineSegments. */
export function floorRuns(segments: RouteSegment[], floorY: (id: string) => number): THREE.Vector3[] {
  const runs: THREE.Vector3[] = [];
  for (let i = 1; i < segments.length; i++) {
    const a = segments[i - 1];
    const b = segments[i];
    if (a.floor_id === b.floor_id || !a.points.length || !b.points.length) continue;
    const [ax, az] = a.points[a.points.length - 1];
    const [bx, bz] = b.points[0];
    runs.push(new THREE.Vector3(ax, floorY(a.floor_id) + LIFT, -az), new THREE.Vector3(bx, floorY(b.floor_id) + LIFT, -bz));
  }
  return runs;
}
/** The run at the stairs reads as dashed: white gaps (m) laid over the blue line. */
const RUN_DASH_M = 1.1;
const RUN_GAP_M = 1.1;

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

/** The route as ONE line, like a map app: one solid blue line on a thin darker casing (routeLook.ts), drawn in once
 * (vertical runs at stairs and lifts in 3D). Only the current route is ever drawn: a new route replaces the old line
 * at once, nothing of the old one stays or fades. The server's guide leg (door to door) is not a path of its own:
 * during guidance the part of the route that the current leg covers keeps the full blue and the rest turns pale. */
export function RouteLine({ route, guideSegments, model, floorY, onlyFloor, reducedMotion, flat = false, worker = false }: Props) {
  void model;
  void flat;
  const here = useTwin((s) => s.state?.position ?? null);
  const points = useMemo(() => (route?.ok && route.segments ? toPoints(route.segments, floorY, onlyFloor) : []), [route, floorY, onlyFloor]);
  const lengths = useMemo(() => {
    const cumulative = [0];
    for (let i = 1; i < points.length; i++) cumulative.push(cumulative[i - 1] + points[i].distanceTo(points[i - 1]));
    return cumulative;
  }, [points]);
  const total = lengths[lengths.length - 1] ?? 0;
  // 3D with every floor of the route drawn (stacked apart): the vertical runs at stairs and lifts, dashed.
  const runs = useMemo(() => (!flat && !onlyFloor && route?.ok && route.segments ? floorRuns(route.segments, floorY) : []), [flat, onlyFloor, route, floorY]);
  const legPoints = useMemo(() => {
    if (!guideSegments || points.length < 2) return null;
    const leg = toPoints(guideSegments, floorY, onlyFloor);
    if (leg.length < 2) return null;
    const a = project(points, lengths, leg[0]);
    const b = project(points, lengths, leg[leg.length - 1]);
    const [s0, s1] = a <= b ? [a, b] : [b, a];
    return s1 - s0 > 0.5 ? slice(points, lengths, s0, s1) : null;
  }, [guideSegments, points, lengths, floorY, onlyFloor]);

  const layerRefs = [useRef<Line2>(null), useRef<Line2>(null)];
  const runGaps = useRef<Line2>(null);
  const started = useRef(0);
  // A new line draws in from its start (a floor switch too); set before the first frame, so the new line never shows
  // whole for a frame. The draw-in uses the dash pattern, and Line2 draws round caps (round joints) only without
  // dashes: once drawn, the line drops the dashes again.
  const [drawingIn, setDrawingIn] = useState(false);
  useLayoutEffect(() => {
    started.current = performance.now();
    setDrawingIn(!reducedMotion);
  }, [points, reducedMotion]);

  useFrame(({ invalidate }) => {
    const drawn = reducedMotion ? 1 : Math.min(1, Math.max(0, performance.now() - started.current) / 1000 / DRAW_IN_S);
    if (drawn < 1) invalidate(); // keeps the draw-in moving under frameloop="demand", then stops
    else if (drawingIn) setDrawingIn(false);
    for (const ref of layerRefs) {
      const material = ref.current?.material as (THREE.ShaderMaterial & { dashOffset: number }) | undefined;
      if (material) material.dashOffset = total * (1 - drawn);
    }
    const runMaterial = runGaps.current?.material as THREE.ShaderMaterial | undefined;
    if (runMaterial) runMaterial.opacity = THREE.MathUtils.clamp((drawn - 0.6) / 0.4, 0, 1); // once the line got there
  });

  if (points.length < 2 || !route?.segments) return null;
  // On a single floor the line may only run to the stairs: the start dot and the destination belong to their own floor.
  const startsHere = !onlyFloor || route.segments[0].floor_id === onlyFloor;
  const endsHere = !onlyFloor || route.segments[route.segments.length - 1].floor_id === onlyFloor;
  const guided = !!legPoints;
  const layers = routeLayers(guided);
  const lineColour = COLOURS.signal;
  const lineWidth = ROUTE_LINE_PX;
  const casingWidth = ROUTE_LINE_PX + 2 * ROUTE_CASING_PX;
  // "You are here" stands at the start: that dot is the start, no second marker on it.
  const first = route?.segments?.[0];
  const hereAtStart =
    !!here &&
    !!first &&
    here.floor_id === first.floor_id &&
    (here.space_id === route?.start || (!!here.point && Math.hypot(here.point[0] - first.points[0][0], here.point[1] - first.points[0][1]) < 3));
  return (
    <group>
      {/* casing then line, both opaque (no halo, glow or flow: translucent layers double-blend at every joint) */}
      {layers.map((layer, i) => (
        <Line
          key={layer.name}
          ref={layerRefs[i]}
          name={layer.name}
          points={points}
          color={layer.colour}
          lineWidth={layer.widthPx}
          dashed={drawingIn}
          dashSize={total}
          gapSize={total}
          {...DEPTH}
          renderOrder={layer.renderOrder}
        />
      ))}
      {/* the run between two floors: white gaps over the blue make it a dashed line (the "↑ 1" badge sits at its foot) */}
      {runs.length >= 2 && (
        <Line ref={runGaps} name="route-floor-run" points={runs} segments color={COLOURS.routeGlow} lineWidth={lineWidth + 0.5} transparent opacity={0} dashed dashSize={RUN_GAP_M} gapSize={RUN_DASH_M} {...DEPTH} renderOrder={21.6} />
      )}
      {legPoints && (
        <>
          <Line points={legPoints} color={COLOURS.mapBlueDark} lineWidth={casingWidth} {...DEPTH} renderOrder={22} />
          <Line points={legPoints} color={lineColour} lineWidth={lineWidth} {...DEPTH} renderOrder={23} />
        </>
      )}
      {/* Guide me follow-cam (FollowRoute.tsx): the walked part turns grey, the next turn gets a chip. */}
      <WalkedLine points={points} lengths={lengths} floorY={floorY} lift={LIFT} lineWidth={lineWidth} casingWidth={casingWidth} depthTest={false} />
      <NextTurnBadge route={route} floorY={floorY} onlyFloor={onlyFloor} lift={LIFT} />
      {/* ends: constant size on screen. The start is a white dot in a blue ring (or nothing when "You are here"
          stands there), the destination a slim red pin on its tip. The room labels move above them (Labels.tsx). */}
      {startsHere && (
        <group position={points[0]} name="route-start">
          {!hereAtStart && (
            <ScreenSized>
              <EndDisc radius={START_DOT_PX + 1} colour={COLOURS.mapBlueDark} order={24} />
              <EndDisc radius={START_DOT_PX} colour={lineColour} order={24.5} />
              <EndDisc radius={START_DOT_PX - 2.5} colour={COLOURS.routeGlow} order={25} />
            </ScreenSized>
          )}
        </group>
      )}
      {/* the destination in map-app red (its own colour token), only on the floor where the route ends */}
      {endsHere && (
        <group position={points[points.length - 1]} name="route-end">
          <DestinationPin key={`${route.start}|${route.destination}|${route.length_m}`} colour={COLOURS.destination} reducedMotion={reducedMotion || worker} />
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
