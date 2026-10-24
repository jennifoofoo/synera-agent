// The tap pin (where the floor was just tapped) and the draggable "You are here" dot.
// Both sit on the floor plane in world space, so the circles stay exact whatever the camera does.

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import type { Point } from "../api/types";
import { samePoint } from "../model/format";
import type { BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";
import { controlsRef } from "./FloorMesh";
import { Disc, Pulse, Ring } from "./Markers";
import "./HerePin.css";

const HINT_KEY = "twin.here.dragHint";
const hintSeen = (): boolean => {
  try {
    return localStorage.getItem(HINT_KEY) === "1";
  } catch {
    return false;
  }
};
const markHintSeen = () => {
  try {
    localStorage.setItem(HINT_KEY, "1");
  } catch {
    /* private mode: the hint just shows again next time */
  }
};

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
      <Ring radius={radius} colour={COLOURS.selection} width={flat ? 0.16 : 0.12} through />
      <lineSegments geometry={cross} renderOrder={19}>
        <lineBasicMaterial color={COLOURS.selection} transparent opacity={0.8} depthTest={false} />
      </lineSegments>
      <Disc radius={flat ? 0.28 : 0.2} colour={COLOURS.selection} opacity={1} through y={0.02} />
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

/** The "You are here" dot. Pointer down on it, move over the floor, release: the new spot is sent like "I'm here". */
export function HereDot({ model, floorY, visibleFloors, flat, reducedMotion, colour }: DotProps) {
  const position = useTwin((s) => s.state?.position ?? null);
  const camera = useThree((s) => s.camera);
  const gl = useThree((s) => s.gl);
  const invalidate = useThree((s) => s.invalidate);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [dragging, setDragging] = useState(false);
  const [hint, setHint] = useState(false);
  const live = useRef({ position, floorY, flat, model });
  live.current = { position, floorY, flat, model };
  const visibleFloorsRef = useRef(visibleFloors);
  visibleFloorsRef.current = visibleFloors;
  const shownFloor = position && visibleFloors.has(position.floor_id) ? position.floor_id : null;

  // First time the dot shows: a short hint that it can be dragged.
  useEffect(() => {
    if (!shownFloor || hintSeen()) return;
    setHint(true);
    const timer = setTimeout(() => {
      setHint(false);
      markHintSeen();
    }, 7000);
    return () => clearTimeout(timer);
  }, [shownFloor]);

  // A new position from the server wins over a leftover drag preview.
  useEffect(() => setDrag(null), [position]);

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
      markHintSeen();
      setHint(false);
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
        // Same path as the "I'm here" button: context.here travels with one short message.
        void useTwin
          .getState()
          .ask("I moved here.", false, { here: { space_id: sent.space_id, point: sent.point, floor_id: here.floor_id } })
          .finally(() => {
            setDrag(null);
            invalidate();
          });
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
  const point = drag?.point ?? position.point ?? model.spaceById.get(position.space_id)?.anchor ?? [0, 0];
  return (
    <group position={[point[0], floorY(position.floor_id), -point[1]]} name="here-dot">
      <Pulse reducedMotion={reducedMotion || dragging} speed={0.8} amount={0.25}>
        <Disc radius={flat ? 3 : 1.4} colour={colour} opacity={flat ? 0.18 : 0.2} through />
      </Pulse>
      {!flat && <Ring radius={1.4} colour={colour} width={0.14} opacity={0.7} through />}
      <Disc radius={flat ? 0.75 : 0.9} colour="#ffffff" opacity={1} through y={0.08} />
      <Disc radius={flat ? 0.55 : 0.6} colour={colour} opacity={1} through y={0.1} />
      {!flat && (
        <mesh position-y={0.35}>
          <sphereGeometry args={[0.32, 16, 16]} />
          <meshBasicMaterial color={colour} />
        </mesh>
      )}
      <group position-y={2.2}>
        <Html center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
          <div className="here-dot-labels">
            <div className="chip chip-here">You are here</div>
            {hint && !dragging && <div className="here-drag-hint">Drag to correct your position</div>}
          </div>
        </Html>
      </group>
    </group>
  );
}
