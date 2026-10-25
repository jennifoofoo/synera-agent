// Guide me as a follow-cam, like the turn-by-turn view of a maps app (not first person): while walking, the
// "You are here" dot moves along the current step at walking pace and the camera follows behind and above it,
// heading up. The dot waits at the end of each step (and at stairs/lifts) until Next; Back jumps to the step start.
//
// The simulated position goes through the Walk with me estimate channel (useWalkMotion.estimate), so HereDot draws
// it as "estimated" and never as a located position. When Walk with me itself drives (step counter on), its
// estimate wins and this file only moves the camera. Reduced motion: no continuous motion, the dot and the camera
// jump per step. A drag or wheel on the canvas pauses following for 3 s; leaving the walk glides back to the view
// from before Guide me.

import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import type CameraControlsImpl from "camera-controls";
import type { BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { useWalkMotion, walkWithMeDriving } from "../walkWithMe";
import { controlsRef } from "./FloorMesh";
import { angleTo, behindAzimuth, buildFollowPath, newPathPoint, pointOnPath } from "./followPath";
import { routeFloorIds } from "./floorVisibility";

/** Walking pace indoors (m/s), the same 1.2 m/s as walkMinutes and the auto-pace spec. */
const WALK_MPS = 1.2;
/** 3D: polar angle of the camera (from straight down; 0.6 rad = 56° pitch) and its distance to the target. */
const POLAR = 0.6;
const DISTANCE_M = 16;
const MIN_DISTANCE_M = 10;
/** The target sits this far ahead of the dot (3D, metres). Small: the dot must stay clear of the step card at the
 * bottom of the screen; the tilted view shows the route ahead anyway. */
const AHEAD_M = 0.5;
/** 2D: metres across the shorter side of the canvas, and the share of it the target leads the dot. */
const PLAN_SPAN_M = 26;
const PLAN_AHEAD = 0.2;
/** Heading: look this far along the route to get the walking direction (smooths corners), low-pass time constant
 * and the largest turn rate. */
const LOOK_M = 3;
const HEADING_TAU_S = 0.45;
const MAX_TURN_RAD_S = 1.2;
/** Damping time constants: target across the floor, target up/down (floor changes glide), distance and pitch. */
const MOVE_TAU_S = 0.25;
const RISE_TAU_S = 0.45;
const FRAME_TAU_S = 0.6;
const PAUSE_MS = 3000;
const REQUEST_PAUSE_MS = 4000;
const UNCERTAINTY_M = 1.5;

interface Props {
  model: BuildingModel;
  floorY: (floorId: string) => number;
}

interface Saved {
  controls: CameraControlsImpl;
  model: BuildingModel;
  position: THREE.Vector3;
  target: THREE.Vector3;
  zoom: number;
}

export function FollowCam({ model, floorY }: Props) {
  const gl = useThree((s) => s.gl);
  const camera = useThree((s) => s.camera);
  const viewport = useThree((s) => s.size);
  const invalidate = useThree((s) => s.invalidate);
  const walking = useTwin((s) => s.walkStep !== null);
  const route = useTwin((s) => s.state?.route ?? null);
  const flat = useTwin((s) => s.viewMode === "2d");
  const reducedMotion = useTwin((s) => s.reducedMotion);
  const path = useMemo(() => (walking && route?.ok ? buildFollowPath(route) : null), [walking, route]);
  const routeFloors = useMemo(() => routeFloorIds(route) ?? [], [route]);

  // Everything the frame loop changes lives in one ref: no React state, no allocations per frame.
  const sim = useRef({
    step: -1,
    group: 0,
    along: 0,
    published: false,
    driving: false,
    needInit: true,
    pausedUntil: 0,
    pointerDown: false,
    azimuth: 0,
    wantAzimuth: 0,
    polar: POLAR,
    distance: DISTANCE_M,
    zoom: 1,
    target: new THREE.Vector3(),
    want: new THREE.Vector3(),
    position: new THREE.Vector3(),
  });
  const point = useMemo(newPathPoint, []);
  const saved = useRef<Saved | null>(null);

  // Start: remember the view to come back to. End (Done, End route, Esc, route gone): clear the simulated dot and
  // glide back to that view.
  useEffect(() => {
    if (!walking) return;
    const c = controlsRef.current;
    if (c) {
      saved.current = {
        controls: c,
        model,
        position: c.getPosition(new THREE.Vector3()),
        target: c.getTarget(new THREE.Vector3()),
        zoom: camera.zoom,
      };
    }
    const s = sim.current;
    s.step = -1;
    s.needInit = true;
    s.pausedUntil = 0;
    invalidate();
    return () => {
      if (s.published) {
        s.published = false;
        if (!walkWithMeDriving()) useWalkMotion.setState({ estimate: null, uncertaintyM: 0, arrived: false });
      }
      const back = saved.current;
      saved.current = null;
      const now = controlsRef.current;
      // Only the same controls on the same building (2D/3D switch or a new building: nothing to go back to).
      if (!back || !now || now !== back.controls || back.model !== useTwin.getState().model) return;
      const animate = !useTwin.getState().reducedMotion;
      const smooth = now.smoothTime;
      if (animate) now.smoothTime = 0.45;
      const done = [now.setLookAt(back.position.x, back.position.y, back.position.z, back.target.x, back.target.y, back.target.z, animate)];
      if ((camera as THREE.OrthographicCamera).isOrthographicCamera) done.push(now.zoomTo(back.zoom, animate));
      void Promise.all(done).then(() => {
        now.smoothTime = smooth;
      });
      invalidate();
      setTimeout(invalidate, 0);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [walking]);

  // The person takes the camera (drag, wheel, pinch): stop following while the pointer is down and 3 s after.
  // A fly-to from the store (a room asked about while walking) gets a little longer.
  useEffect(() => {
    if (!walking) return;
    const element = gl.domElement;
    const s = sim.current;
    const onDown = () => {
      s.pointerDown = true;
      s.pausedUntil = Infinity;
    };
    const onUp = () => {
      if (!s.pointerDown) return;
      s.pointerDown = false;
      s.pausedUntil = performance.now() + PAUSE_MS;
    };
    const onWheel = () => {
      if (!s.pointerDown) s.pausedUntil = performance.now() + PAUSE_MS;
    };
    element.addEventListener("pointerdown", onDown);
    element.addEventListener("wheel", onWheel, { passive: true });
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    const unsubscribe = useTwin.subscribe((state, prev) => {
      if (state.camera.nonce !== prev.camera.nonce) s.pausedUntil = Math.max(s.pausedUntil, performance.now() + REQUEST_PAUSE_MS);
    });
    return () => {
      element.removeEventListener("pointerdown", onDown);
      element.removeEventListener("wheel", onWheel);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      unsubscribe();
    };
  }, [walking, gl]);

  // A new step, view or route: ask for a frame (phones render on demand).
  const walkStep = useTwin((s) => s.walkStep);
  useEffect(() => {
    if (walking) invalidate();
  }, [walking, walkStep, flat, path, invalidate]);

  useFrame((_, delta) => {
    const store = useTwin.getState();
    const step = store.walkStep;
    const c = controlsRef.current;
    if (step === null || !path || !c) return;
    const s = sim.current;
    const dt = Math.min(delta, 0.1);
    const instant = reducedMotion;
    let moving = false;

    // 1. The dot: Walk with me's estimate when it drives, otherwise our own walk along the current step.
    const driving = walkWithMeDriving();
    if (driving !== s.driving) {
      s.driving = driving;
      s.step = -1; // switched off mid-walk: start again at the current step
      s.published = false;
    }
    if (driving) {
      const e = useWalkMotion.getState().estimate;
      if (!e || !path.legs[e.legIndex]) return;
      point.x = e.point[0];
      point.y = e.point[1];
      point.floorId = e.floorId;
      point.leg = e.legIndex;
      point.alongLeg = e.alongLegM;
    } else {
      const plan = path.plan.steps[step];
      if (!plan) return;
      let changed = false;
      if (step !== s.step) {
        // Back, a floor change, the first step or reduced motion: jump to the step's start. Forward on the same
        // floor: keep walking from where the dot is (it catches up quickly if Next came early).
        if (s.step < 0 || plan.group !== s.group || s.along > plan.startM + 0.05 || instant) s.along = plan.startM;
        s.group = plan.group;
        s.step = step;
        changed = true;
      }
      const goal = instant ? plan.startM : plan.endM;
      if (s.along < goal - 1e-4) {
        const behind = plan.startM - s.along;
        const speed = behind > 0.3 ? Math.max(WALK_MPS, behind / 1.2) : WALK_MPS;
        s.along = Math.min(goal, s.along + speed * dt);
        moving = true;
      }
      pointOnPath(path, s.along, s.group, point);
      if (moving || changed || !s.published) {
        const leg = path.legs[point.leg];
        const last = step >= path.plan.steps.length - 1;
        const there = s.along >= plan.endM - 0.01;
        useWalkMotion.setState({
          estimate: {
            estimated: true,
            point: [point.x, point.y],
            floorId: point.floorId,
            legIndex: point.leg,
            legCount: path.legs.length,
            alongLegM: point.alongLeg,
            legLengthM: leg.lengthM,
            alongRouteM: s.along,
            routeLengthM: path.lengthM,
            distanceLeftM: Math.max(0, path.lengthM - s.along),
            legLeftM: Math.max(0, leg.lengthM - point.alongLeg),
            atConnector: plan.kind === "ride" && there,
            arrived: last && there,
            offRoute: false,
            steps: 0,
          },
          uncertaintyM: UNCERTAINTY_M,
          arrived: last && there,
        });
        s.published = true;
      }
    }

    // 2. The camera, unless the person holds it.
    if (performance.now() < s.pausedUntil) {
      s.needInit = true;
      if (moving) invalidate();
      return;
    }
    const ortho = (camera as THREE.OrthographicCamera).isOrthographicCamera;
    if (s.needInit) {
      // Start from the current view, so entering (and resuming after a drag) glides instead of jumping.
      c.getTarget(s.target);
      s.azimuth = c.azimuthAngle;
      s.wantAzimuth = s.azimuth;
      s.polar = c.polarAngle;
      s.distance = c.distance;
      s.zoom = camera.zoom;
      s.needInit = false;
    }
    const heading = behindAzimuth(path, point, LOOK_M);
    if (heading !== null) s.wantAzimuth = heading;
    const turn = angleTo(s.azimuth, s.wantAzimuth);
    if (instant) s.azimuth += turn;
    else {
      const cap = MAX_TURN_RAD_S * dt;
      s.azimuth += THREE.MathUtils.clamp(turn * (1 - Math.exp(-dt / HEADING_TAU_S)), -cap, cap);
    }

    const y = floorY(point.floorId);
    let wantPolar = POLAR;
    let wantDistance = DISTANCE_M;
    let lead = AHEAD_M;
    let wantZoom = s.zoom;
    if (flat) {
      wantPolar = c.polarAngle; // the plan stays straight down (CameraRig locks the tilt)
      wantDistance = c.distance;
      wantZoom = Math.min(viewport.width, viewport.height) / PLAN_SPAN_M;
      lead = PLAN_SPAN_M * PLAN_AHEAD;
    } else {
      // A route over several floors stacks them apart: stay under the next floor up, flatter if needed.
      let ceiling = Infinity;
      for (const id of routeFloors) {
        const above = floorY(id) - y;
        if (above > 0.5 && above < ceiling) ceiling = above;
      }
      const room = ceiling - 1;
      if (room < wantDistance * Math.cos(wantPolar)) {
        wantDistance = Math.max(MIN_DISTANCE_M, room / Math.cos(POLAR));
        wantPolar = Math.acos(THREE.MathUtils.clamp(room / wantDistance, 0.2, 1));
      }
    }
    // Ahead of the dot along the smoothed heading: the walking direction is -(sin θ, cos θ) in world x/z.
    s.want.set(point.x - Math.sin(s.azimuth) * lead, y, -point.y - Math.cos(s.azimuth) * lead);
    const kMove = instant ? 1 : 1 - Math.exp(-dt / MOVE_TAU_S);
    const kRise = instant ? 1 : 1 - Math.exp(-dt / RISE_TAU_S);
    const kFrame = instant ? 1 : 1 - Math.exp(-dt / FRAME_TAU_S);
    const gap = s.want.distanceTo(s.target);
    s.target.x += (s.want.x - s.target.x) * kMove;
    s.target.z += (s.want.z - s.target.z) * kMove;
    s.target.y += (s.want.y - s.target.y) * kRise;
    s.polar += (wantPolar - s.polar) * kFrame;
    s.distance += (wantDistance - s.distance) * kFrame;
    s.zoom += (wantZoom - s.zoom) * kFrame;

    const sinPolar = Math.sin(s.polar);
    s.position.set(
      s.target.x + s.distance * sinPolar * Math.sin(s.azimuth),
      s.target.y + s.distance * Math.cos(s.polar),
      s.target.z + s.distance * sinPolar * Math.cos(s.azimuth),
    );
    void c.setLookAt(s.position.x, s.position.y, s.position.z, s.target.x, s.target.y, s.target.z, false);
    if (ortho && Math.abs(camera.zoom - s.zoom) > 1e-3) void c.zoomTo(s.zoom, false);

    const settled =
      gap < 0.01 && Math.abs(turn) < 0.002 && Math.abs(wantPolar - s.polar) < 0.002 && Math.abs(wantDistance - s.distance) < 0.01 && Math.abs(wantZoom - s.zoom) < 0.01;
    if (moving || !settled) invalidate();
  });

  return null;
}
