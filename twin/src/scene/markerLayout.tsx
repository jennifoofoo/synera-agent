// Screen-space sizes (px) of the markers, and how far a room label moves up when a marker sits in its room.
// Markers are drawn at a constant size on screen; the labels use these numbers so they never sit on a marker.

import { useRef, type ReactNode } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import type { Guide, Point, Space } from "../api/types";

/** "You are here": white rim, blue core, pulse disc (radius in px). */
export const HERE_RIM_PX = 9;
export const HERE_CORE_PX = 6.5;
export const HERE_PULSE_PX = 28;
/** Gap between the dot and its "You are here" badge (badge bottom = rim + gap above the dot centre). */
export const BADGE_GAP_PX = 4;
export const BADGE_LIFT_PX = HERE_RIM_PX + BADGE_GAP_PX;
/** The guide's next target: a small paper dot with a blue ring (radius in px). */
export const END_RING_PX = 6;
/** Route start when no "You are here" dot stands there: a paper dot with a blue ring (radius in px). */
export const START_DOT_PX = 5;
/** Route destination: a slim pin standing on its tip (px): head radius, head centre above the tip, total height. */
export const PIN_HEAD_PX = 6.5;
export const PIN_HEAD_Y_PX = 14;
export const PIN_HEIGHT_PX = PIN_HEAD_Y_PX + PIN_HEAD_PX + 1.5; // with the paper casing

/** How far above its marker a room label's bottom edge sits (px). */
export const LABEL_LIFT = {
  here: BADGE_LIFT_PX + 19 + 4, // above the badge (19 px tall) with a small gap
  guide: END_RING_PX + BADGE_GAP_PX + 19 + 4, // above the "Next: ..." chip
  end: PIN_HEIGHT_PX + 3, // just above the destination pin's head
  start: START_DOT_PX + 12, // just above the start dot
};

/** Where the guide's next target is marked: the end of the current leg on its floor (on the route line), else
 * the room anchor. Markers.tsx draws it there, Labels.tsx lifts the room name above it. */
export function guideNextPoint(guide: Guide, target: Space): Point {
  const onFloor = guide.leg.segments.filter((segment) => segment.floor_id === target.floor_id && segment.points.length);
  const last = onFloor[onFloor.length - 1];
  return last ? last.points[last.points.length - 1] : target.anchor;
}

const at = new THREE.Vector3();

/** Children are authored in px on the floor plane (x/z); the group scales them so they keep that size on screen.
 * The y axis stays in metres, so the small lifts above the floor stay the same. With `uniform` the y axis is in px
 * too (for markers authored on a camera-facing plane, such as the destination pin). */
export function ScreenSized({ children, uniform = false }: { children: ReactNode; uniform?: boolean }) {
  const group = useRef<THREE.Group>(null);
  useFrame(({ camera, size }) => {
    const g = group.current;
    if (!g) return;
    let metresPerPixel: number;
    if ((camera as THREE.OrthographicCamera).isOrthographicCamera) {
      const ortho = camera as THREE.OrthographicCamera;
      metresPerPixel = (ortho.top - ortho.bottom) / ortho.zoom / Math.max(1, size.height);
    } else {
      const perspective = camera as THREE.PerspectiveCamera;
      g.getWorldPosition(at);
      metresPerPixel = (2 * camera.position.distanceTo(at) * Math.tan(THREE.MathUtils.degToRad(perspective.fov / 2))) / Math.max(1, size.height);
    }
    if (Math.abs(g.scale.x - metresPerPixel) > 1e-6) g.scale.set(metresPerPixel, uniform ? metresPerPixel : 1, metresPerPixel);
  });
  return <group ref={group}>{children}</group>;
}
