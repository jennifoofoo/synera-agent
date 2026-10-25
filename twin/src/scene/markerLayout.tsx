// Screen-space sizes (px) of the markers, and how far a room label moves up when a marker sits in its room.
// Markers are drawn at a constant size on screen; the labels use these numbers so they never sit on a marker.

import { useRef, type ReactNode } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";

/** "You are here": white rim, blue core, soft accuracy halo (radius in px). No text: the dot is the marker. */
export const HERE_RIM_PX = 9;
export const HERE_CORE_PX = 6.5;
export const HERE_HALO_PX = 22;
/** Gap between a marker and the drag hint below it. */
export const BADGE_GAP_PX = 4;
/** Route start when no "You are here" dot stands there: a paper dot with a blue ring (radius in px). */
export const START_DOT_PX = 6;
/** Route destination: a slim pin standing on its tip (px): head radius, head centre above the tip, total height. */
export const PIN_HEAD_PX = 6.5;
export const PIN_HEAD_Y_PX = 14;
export const PIN_HEIGHT_PX = PIN_HEAD_Y_PX + PIN_HEAD_PX + 1.5; // with the paper casing

/** Tap pin (the tapped spot): ring radius, ring width and centre dot radius (px), and the reach of its small
 * crosshair (about 1.5x the ring radius). In 3D a stalk with a head stands on it (metres, TAP_STALK_M high). */
export const TAP_RING_PX = 11;
export const TAP_RING_W_PX = 2;
export const TAP_DOT_PX = 3.5;
export const TAP_CROSS_PX = 16.5;
export const TAP_STALK_M = 1.35; // top of the 3D pin's head above the floor

/** How far above its marker a room label's bottom edge sits (px). */
export const LABEL_LIFT = {
  here: HERE_RIM_PX + BADGE_GAP_PX + 6, // above the dot's white rim, with room for the frame the HTML label lags behind a gliding camera
  end: PIN_HEIGHT_PX + 3, // just above the destination pin's head
  start: START_DOT_PX + 12, // just above the start dot
  tap: TAP_CROSS_PX + BADGE_GAP_PX, // 2D: above the tap pin's crosshair, so no line runs through the name
  tapHead: BADGE_GAP_PX + 2, // 3D: just above the head of the tap pin's stalk (anchored at TAP_STALK_M)
};

const at = new THREE.Vector3();

/** Width and height (px) of the frame the camera's frustum spans: when CameraRig renders only the visible window of
 * a taller or wider virtual frame (setViewOffset, a sheet covers part of the canvas) that is the full frame, else the
 * canvas. Metres per pixel must divide by this, or markers grow by the covered share (1.4x under a phone sheet). */
export function frameSize(camera: THREE.Camera, width: number, height: number): [number, number] {
  const view = (camera as THREE.PerspectiveCamera | THREE.OrthographicCamera).view;
  return view?.enabled ? [view.fullWidth, view.fullHeight] : [width, height];
}

/** A slow breathing scale on the floor plane (markers that want attention); still under reduced motion. */
export function Pulse({ children, reducedMotion, speed = 1.6, amount = 0.12 }: { children: ReactNode; reducedMotion: boolean; speed?: number; amount?: number }) {
  const group = useRef<THREE.Group>(null);
  useFrame(({ clock, invalidate }) => {
    if (!group.current || reducedMotion) return;
    invalidate();
    const s = 1 + amount * (0.5 + 0.5 * Math.sin(clock.elapsedTime * speed * Math.PI));
    group.current.scale.set(s, 1, s);
  });
  return <group ref={group}>{children}</group>;
}

/** A ring that grows and fades a few times when it appears, then stays hidden: attention on arrival, calm after.
 * Asks for frames only while it runs (no per-frame invalidate afterwards); nothing under reduced motion. */
export function ArrivalPulse({ radius, colour, reducedMotion, beats = 3, period = 1.1 }: { radius: number; colour: string; reducedMotion: boolean; beats?: number; period?: number }) {
  const group = useRef<THREE.Group>(null);
  const material = useRef<THREE.MeshBasicMaterial>(null);
  const start = useRef<number | null>(null);
  const done = useRef(reducedMotion);
  useFrame(({ clock, invalidate }) => {
    const g = group.current;
    if (!g || !material.current || done.current) return;
    if (start.current === null) start.current = clock.elapsedTime;
    const t = (clock.elapsedTime - start.current) / period;
    if (t >= beats) {
      done.current = true;
      g.visible = false;
      invalidate(); // one last frame without the ring
      return;
    }
    const phase = t % 1;
    const s = 0.4 + 0.9 * phase;
    g.scale.set(s, 1, s);
    material.current.opacity = 0.55 * (1 - phase);
    invalidate();
  });
  if (reducedMotion) return null;
  return (
    <group ref={group}>
      <mesh rotation-x={-Math.PI / 2} position-y={0.07} renderOrder={15}>
        <ringGeometry args={[Math.max(0.05, radius - 0.14), radius, 48]} />
        <meshBasicMaterial ref={material} color={colour} transparent opacity={0} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

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
      metresPerPixel = (ortho.top - ortho.bottom) / ortho.zoom / Math.max(1, frameSize(camera, size.width, size.height)[1]);
    } else {
      const perspective = camera as THREE.PerspectiveCamera;
      g.getWorldPosition(at);
      metresPerPixel = (2 * camera.position.distanceTo(at) * Math.tan(THREE.MathUtils.degToRad(perspective.fov / 2))) / Math.max(1, frameSize(camera, size.width, size.height)[1]);
    }
    if (Math.abs(g.scale.x - metresPerPixel) > 1e-6) g.scale.set(metresPerPixel, uniform ? metresPerPixel : 1, metresPerPixel);
  });
  return <group ref={group}>{children}</group>;
}
