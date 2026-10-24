// Screen-space sizes (px) of the markers, and how far a room label moves up when a marker sits in its room.
// Markers are drawn at a constant size on screen; the labels use these numbers so they never sit on a marker.

import { useRef, type ReactNode } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";

/** "You are here": white rim, blue core, pulse disc (radius in px). */
export const HERE_RIM_PX = 9;
export const HERE_CORE_PX = 6.5;
export const HERE_PULSE_PX = 28;
/** Gap between the dot and its "You are here" badge (badge bottom = rim + gap above the dot centre). */
export const BADGE_GAP_PX = 4;
export const BADGE_LIFT_PX = HERE_RIM_PX + BADGE_GAP_PX;
/** Route ends and the guide's next target: a small ring. */
export const END_RING_PX = 8;
export const START_DOT_PX = 5;

/** How far above its marker a room label's bottom edge sits (px). */
export const LABEL_LIFT = {
  here: BADGE_LIFT_PX + 19 + 4, // above the badge (19 px tall) with a small gap
  guide: END_RING_PX + BADGE_GAP_PX + 19 + 4, // above the "Next: ..." chip
  end: 20, // just above a route end ring
};

const at = new THREE.Vector3();

/** Children are authored in px on the floor plane (x/z); the group scales them so they keep that size on screen.
 * The y axis stays in metres, so the small lifts above the floor stay the same. */
export function ScreenSized({ children }: { children: ReactNode }) {
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
    if (Math.abs(g.scale.x - metresPerPixel) > 1e-6) g.scale.set(metresPerPixel, 1, metresPerPixel);
  });
  return <group ref={group}>{children}</group>;
}
