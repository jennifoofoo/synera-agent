// The tap pin (where the floor was just tapped) and the draggable "You are here" dot.
// Both sit on the floor plane in world space, so the circles stay exact whatever the camera does.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Html } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import type { Point } from "../api/types";
import { samePoint } from "../model/format";
import type { BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";
import { controlsRef } from "./FloorMesh";
import { Disc, Ring } from "./Markers";
import { markHereHintSeen } from "../ui/HereChip";
import { useWalkMotion } from "../walkWithMe";
import "./HerePin.css";
import { HERE_CORE_PX, HERE_HALO_PX, HERE_RIM_PX, ScreenSized } from "./markerLayout";

function inPolygon(point: Point, polygon: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > point[1] !== yj > point[1] && point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

interface PinProps {
  model: BuildingModel;
  floorY: (floorId: string) => number;
  visibleFloors: Set<string>;
  flat: boolean;
}

/** Pin with a ring and a hairline crosshair at the tapped point. Esc removes it (the card's x does too). */
export function TapPin({ floorY, visibleFloors, flat }: PinProps) {
  const selection = useTwin((s) => s.selection);
  const position = useTwin((s) => s.state?.position ?? null);
  const select = useTwin((s) => s.select);
  const active = !!selection?.point && selection.kind !== "asset" && selection.kind !== "opening";

  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.key !== "Escape" || target?.closest("input, textarea, select, [contenteditable]")) return;
      if (useTwin.getState().directions) return; // Esc belongs to the From/To panel then
      select(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, select]);

  const reach = flat ? 4.5 : 3;
  const cross = useMemo(() => {
    const gap = flat ? 1.1 : 0.8;
    const verts = [-reach, 0, 0, -gap, 0, 0, gap, 0, 0, reach, 0, 0, 0, 0, -reach, 0, 0, -gap, 0, 0, gap, 0, 0, reach];
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
    return geometry;
  }, [reach, flat]);
  useEffect(() => () => cross.dispose(), [cross]);

  if (!selection || !active || !selection.point || !visibleFloors.has(selection.floor_id)) return null;
  // The dot already stands here (just pressed "I'm here"): never two markers on one spot.
  if (position && position.floor_id === selection.floor_id && samePoint(position.point, selection.point)) return null;
  const radius = flat ? 1.1 : 0.8;
  return (
    <group position={[selection.point[0], floorY(selection.floor_id) + 0.07, -selection.point[1]]} name="tap-pin">
      <Ring radius={radius} colour={COLOURS.selection} width={flat ? 0.16 : 0.12} through order={30} />
      <lineSegments geometry={cross} renderOrder={19}>
        <lineBasicMaterial color={COLOURS.selection} transparent opacity={0.8} depthTest={false} />
      </lineSegments>
      <Disc radius={flat ? 0.28 : 0.2} colour={COLOURS.selection} opacity={1} through y={0.02} order={31} />
      {!flat && (
        <>
          <mesh position-y={0.55}>
            <cylinderGeometry args={[0.025, 0.025, 1.1, 8]} />
            <meshBasicMaterial color={COLOURS.selection} />
          </mesh>
          <mesh position-y={1.15}>
            <sphereGeometry args={[0.2, 16, 16]} />
            <meshBasicMaterial color={COLOURS.selection} />
          </mesh>
        </>
      )}
    </group>
  );
}

interface DotProps {
  model: BuildingModel;
  floorY: (floorId: string) => number;
  visibleFloors: Set<string>;
  flat: boolean;
  reducedMotion: boolean;
  colour: string;
}

interface Drag {
  point: Point;
  space_id: string;
}

/** The "You are here" dot. Pointer down on it, move over the floor, release: the new spot is set like "I'm here".
 * The one-time "drag to correct" hint lives in the HereChip bar, off the map. */
export function HereDot({ model, floorY, visibleFloors, flat, colour, reducedMotion }: DotProps) {
  const known = useTwin((s) => s.state?.position ?? null);
  // Walk with me: the dot shows the step estimate instead (local only, never written to state.position).
  const estimate = useWalkMotion((s) => s.estimate);
  const uncertaintyM = useWalkMotion((s) => s.uncertaintyM);
  const position = useMemo(
    () => (estimate ? { space_id: "", floor_id: estimate.floorId, point: estimate.point as Point } : known),
    [estimate, known],
  );
  const camera = useThree((s) => s.camera);
  const gl = useThree((s) => s.gl);
  const invalidate = useThree((s) => s.invalidate);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [dragging, setDragging] = useState(false);
  const live = useRef({ position, floorY, flat, model });
  live.current = { position, floorY, flat, model };
  const visibleFloorsRef = useRef(visibleFloors);
  visibleFloorsRef.current = visibleFloors;
  const shownFloor = position && visibleFloors.has(position.floor_id) ? position.floor_id : null;
  // A new position from the server wins over a leftover drag preview.
  useEffect(() => setDrag(null), [known]);

  // A jump of the dot (Next/Back in the step guide, "I'm here") glides for 250 ms instead of teleporting; reduced
  // motion, a drag, a floor change and the small steps of the Walk with me estimate are drawn at once.
  const groupRef = useRef<THREE.Group>(null);
  const tween = useRef<{ from: Point; to: Point; t0: number } | null>(null);
  const shown = useRef<{ point: Point; floor: string } | null>(null);
  const target: Point | null = position ? (drag?.point ?? position.point ?? model.spaceById.get(position.space_id)?.anchor ?? null) : null;
  const targetFloor = position?.floor_id ?? null;
  useLayoutEffect(() => {
    const before = shown.current;
    shown.current = target && targetFloor ? { point: target, floor: targetFloor } : null;
    const g = groupRef.current;
    if (!target || !before || !g || before.floor !== targetFloor || drag || reducedMotion) {
      tween.current = null;
      return;
    }
    if (Math.hypot(target[0] - before.point[0], target[1] - before.point[1]) < 1) {
      tween.current = null;
      return;
    }
    const from: Point = tween.current ? [g.position.x, -g.position.z] : before.point;
    tween.current = { from, to: target, t0: performance.now() };
    g.position.x = from[0];
    g.position.z = -from[1];
    invalidate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target?.[0], target?.[1], targetFloor]);
  useFrame(() => {
    const t = tween.current;
    const g = groupRef.current;
    if (!t || !g) return;
    const k = Math.min(1, (performance.now() - t.t0) / 250);
    const e = 1 - (1 - k) ** 3;
    g.position.x = t.from[0] + (t.to[0] - t.from[0]) * e;
    g.position.z = -(t.from[1] + (t.to[1] - t.from[1]) * e);
    if (k >= 1) tween.current = null;
    else invalidate();
  });

  // Walking the steps: a confirmed step (Next/Back) that lands outside the visible part of the map pans the camera
  // to the dot (same zoom). A floor change frames the new floor on its own (CameraRig), so it is left alone here.
  const walking = useTwin((s) => s.walkStep !== null);
  const lastKnown = useRef(known);
  useEffect(() => {
    const before = lastKnown.current;
    lastKnown.current = known;
    const c = controlsRef.current;
    if (!walking || !c || !known?.point || !before || before.floor_id !== known.floor_id) return;
    const rect = gl.domElement.getBoundingClientRect();
    const v = new THREE.Vector3(known.point[0], floorY(known.floor_id), -known.point[1]).project(camera);
    const x = ((v.x + 1) / 2) * rect.width;
    const y = ((1 - v.y) / 2) * rect.height;
    const { topInset, bottomInset, rightInset } = useTwin.getState();
    const pad = 32;
    if (x > pad && x < rect.width - rightInset - pad && y > topInset + pad && y < rect.height - bottomInset - pad) return;
    const t = c.getTarget(new THREE.Vector3());
    void c.moveTo(known.point[0], t.y, -known.point[1], !reducedMotion);
    invalidate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [known]);

  useEffect(() => {
    const element = gl.domElement;
    const ray = new THREE.Raycaster();
    const hit = new THREE.Vector3();

    const dotScreen = (): [number, number] | null => {
      const { position: here, floorY: y, model: m } = live.current;
      if (!here) return null;
      const point = here.point ?? m.spaceById.get(here.space_id)?.anchor;
      if (!point) return null;
      const rect = element.getBoundingClientRect();
      const v = new THREE.Vector3(point[0], y(here.floor_id) + 0.1, -point[1]).project(camera);
      return [rect.left + ((v.x + 1) / 2) * rect.width, rect.top + ((1 - v.y) / 2) * rect.height];
    };

    const floorPoint = (clientX: number, clientY: number, floorId: string): Point | null => {
      const rect = element.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1), camera);
      const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -live.current.floorY(floorId));
      return ray.ray.intersectPlane(plane, hit) ? [hit.x, -hit.z] : null;
    };

    const onDown = (event: PointerEvent) => {
      if (!event.isPrimary || (event.pointerType === "mouse" && event.button !== 0)) return;
      const here = live.current.position;
      const screen = dotScreen();
      if (!here || !screen || !visibleFloorsRef.current.has(here.floor_id)) return;
      const reach = event.pointerType === "mouse" ? 26 : 40;
      if (Math.hypot(event.clientX - screen[0], event.clientY - screen[1]) > reach) return;
      // Ours: keep the camera and the floor tap out of it, then follow the pointer on the floor plane.
      event.stopImmediatePropagation();
      event.preventDefault();
      const store = useTwin.getState();
      store.select(null);
      store.setDragLock(true);
      if (controlsRef.current) controlsRef.current.enabled = false;
      try {
        element.setPointerCapture(event.pointerId);
      } catch {
        /* the window listeners below still follow the pointer */
      }
      markHereHintSeen();
      setDragging(true);
      const start: [number, number] = [event.clientX, event.clientY];
      let last: Drag | null = null;
      let moved = false;

      const onMove = (move: PointerEvent) => {
        if (move.pointerId !== event.pointerId) return;
        if (Math.hypot(move.clientX - start[0], move.clientY - start[1]) > 4) moved = true;
        const point = floorPoint(move.clientX, move.clientY, here.floor_id);
        if (!point) return;
        const rounded: Point = [Math.round(point[0] * 100) / 100, Math.round(point[1] * 100) / 100];
        const space = live.current.model.floorById.get(here.floor_id)?.spaces.find((s) => s.type !== "outdoor" && inPolygon(rounded, s.polygon));
        if (!space) return; // outside every room: keep the last valid point
        last = { point: rounded, space_id: space.id };
        setDrag(last);
        invalidate();
      };
      const finish = (end: PointerEvent, cancelled: boolean) => {
        if (end.pointerId !== event.pointerId) return;
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onCancel);
        try {
          element.releasePointerCapture(event.pointerId);
        } catch {
          /* already released */
        }
        if (controlsRef.current) controlsRef.current.enabled = true;
        useTwin.getState().setDragLock(false);
        setDragging(false);
        if (moved) {
          // The click that follows a drag must not select the floor underneath.
          const swallow = (click: Event) => click.stopImmediatePropagation();
          element.addEventListener("click", swallow, true);
          setTimeout(() => element.removeEventListener("click", swallow, true), 60);
        }
        if (cancelled || !last) {
          setDrag(null);
          invalidate();
          return;
        }
        const sent = last;
        // Same path as the "I'm here" button: set on screen at once, no agent call.
        useTwin.getState().setHere({ space_id: sent.space_id, point: sent.point, floor_id: here.floor_id });
        setDrag(null);
        invalidate();
      };
      const onUp = (up: PointerEvent) => finish(up, false);
      const onCancel = (cancel: PointerEvent) => finish(cancel, true);
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onCancel);
    };

    element.addEventListener("pointerdown", onDown, true);
    return () => element.removeEventListener("pointerdown", onDown, true);
  }, [camera, gl, invalidate]);

  if (!position || !shownFloor) return null;
  const point = target ?? [0, 0];
  return (
    <group ref={groupRef} position={[point[0], floorY(position.floor_id), -point[1]]} name={estimate ? "walk-estimate" : "here-dot"}>
      {estimate && !drag && (
        <>
          {/* soft uncertainty ring in metres: it grows with the distance walked since the last confirmation */}
          <Disc radius={uncertaintyM} colour={colour} opacity={0.08} through y={0.04} />
          <Ring radius={uncertaintyM} colour={colour} width={flat ? 0.12 : 0.08} opacity={0.35} through />
          <Html position={[0, 0, 0]} center zIndexRange={[5, 0]} style={{ pointerEvents: "none" }}>
            <span className="walk-estimated">estimated</span>
          </Html>
        </>
      )}
      {/* the map-app blue dot: constant size on screen, white rim, a calm accuracy halo, no text */}
      <ScreenSized>
        <Disc radius={HERE_HALO_PX} colour={colour} opacity={0.16} through />
        <Disc radius={HERE_RIM_PX} colour="#ffffff" opacity={1} through y={0.08} order={30} />
        <Disc radius={HERE_CORE_PX} colour={colour} opacity={1} through y={0.1} order={31} />
      </ScreenSized>
    </group>
  );
}
