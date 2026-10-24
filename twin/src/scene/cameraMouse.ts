import { useEffect, type RefObject } from "react";
import * as THREE from "three";
import { useThree } from "@react-three/fiber";
import CameraControlsImpl from "camera-controls";

// Input model (like a map):
//  - left button or one finger: grab the map and pan (the point under the pointer stays under the pointer, no damping)
//  - right button, or Ctrl/Alt + left: rotate (3D: also tilt). Two fingers: pinch zoom + rotate + tilt in 3D;
//    on the 2D plan pinch zoom around the midpoint and move with it, no rotation
//  - middle button: pan. Wheel and pinch: zoom to the pointer. Two-finger trackpad scroll: pan.
// camera-controls does rotate, touch and the animated moves; panning, the wheel and gestures are done here.

const IS_MAC = typeof navigator !== "undefined" && /Mac/.test(navigator.platform);
const UNIT = Math.log(1 / 0.95);

const NOTCH_CLAMP_PX = 90; // a mouse notch (100 px in Chrome) counts as 90 px at most
const PX_TO_UNITS = 0.035; // 90 px = 3.15 units = a 15 percent step (camera-controls zooms by 0.95^units)
const PINCH_TO_UNITS = 0.3; // Chrome and Firefox report a trackpad pinch as ctrl + wheel with small deltas
const PINCH_CLAMP = 8;
const TAP_PX = 6; // a press that moved further than this is a drag: it never ends in a click
const PAN_START_PX = 3;

const RIG_FLAG = "__rigWheel";

export function wheelUnits(event: Pick<WheelEvent, "deltaY" | "deltaMode" | "ctrlKey">): number {
  if (event.ctrlKey) return Math.max(-PINCH_CLAMP, Math.min(PINCH_CLAMP, event.deltaY * PINCH_TO_UNITS));
  const px = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaMode === 2 ? event.deltaY * 400 : event.deltaY;
  return Math.max(-NOTCH_CLAMP_PX, Math.min(NOTCH_CLAMP_PX, px)) * PX_TO_UNITS;
}

/** A mouse wheel notch (zoom) or a trackpad scroll (pan)? Line-mode steps and whole 120 steps (Chrome and Firefox
 * with a mouse) are notches. A trackpad sends a stream of small steps, often sideways or fractional, so an event
 * that follows another within 80 ms, or comes sideways or fractional, is a scroll. An isolated whole step is a
 * notch (Safari reports a mouse notch and a trackpad step alike, so the first step of a scroll zooms a hair). */
let lastWheel = 0;
export function isTrackpadScroll(event: WheelEvent): boolean {
  const now = performance.now();
  const streaming = now - lastWheel < 80;
  lastWheel = now;
  if (event.deltaMode !== 0) return false;
  const legacy = (event as WheelEvent & { wheelDeltaY?: number }).wheelDeltaY ?? 0;
  if (Math.abs(event.deltaY) >= 50 && Math.abs(legacy) % 120 === 0 && event.deltaX === 0) return false;
  return event.deltaX !== 0 || !Number.isInteger(event.deltaY) || streaming;
}

/** Two fingers on the 2D plan: zoom by the finger spread around their midpoint, and move with the midpoint. */
interface Pinch {
  snap: THREE.OrthographicCamera;
  plane: THREE.Plane;
  p0: THREE.Vector3;
  target0: THREE.Vector3;
  zoom0: number;
  spread0: number;
}

interface Options {
  controls: RefObject<CameraControlsImpl>;
  /** Called on a double click with the pointer position. */
  onDoubleClick?: (event: MouseEvent) => void;
  /** False while this canvas is not the one in use (e.g. hidden behind the campus view). */
  active?: () => boolean;
}

interface Pan {
  pointerId: number;
  start: [number, number];
  snap: THREE.Camera;
  p0: THREE.Vector3;
  target0: THREE.Vector3;
  plane: THREE.Plane;
  moved: boolean;
}

/** Mouse, touch and trackpad input on top of camera-controls (see the model at the top of this file). */
export function useCameraMouse({ controls, onDoubleClick, active }: Options) {
  const gl = useThree((s) => s.gl);
  const camera = useThree((s) => s.camera);
  const invalidate = useThree((s) => s.invalidate);

  useEffect(() => {
    const el = gl.domElement;
    const host = el.parentElement ?? el;
    const ray = new THREE.Raycaster();
    const hit = new THREE.Vector3();
    const v = new THREE.Vector3();
    const ndc = new THREE.Vector2();
    let lastX = 0;
    let lastY = 0;
    let touches = 0;
    let pan: Pan | null = null;
    let pinch: Pinch | null = null;
    const fingers = new Map<number, [number, number]>();
    const scratch = new THREE.OrthographicCamera();
    let restoreLeft: CameraControlsImpl["mouseButtons"]["left"] | null = null;
    let down: [number, number] = [0, 0];
    const usable = () => !(active && !active());
    el.style.cursor = "grab";

    const ground = (cam: THREE.Camera, clientX: number, clientY: number, plane: THREE.Plane, out: THREE.Vector3): boolean => {
      const rect = el.getBoundingClientRect();
      ray.setFromCamera(ndc.set(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1), cam);
      return ray.ray.intersectPlane(plane, out) !== null;
    };

    const zoomBy = (units: number, x: number, y: number) => {
      if (!units) return;
      const event = new WheelEvent("wheel", { deltaY: units * (IS_MAC ? 1 : 3), deltaMode: 1, clientX: x, clientY: y, bubbles: true, cancelable: true });
      Object.defineProperty(event, RIG_FLAG, { value: true });
      el.dispatchEvent(event);
    };

    /** Trackpad scroll: move the view by the scrolled pixels (content follows the fingers). */
    const scrollPan = (c: CameraControlsImpl, dx: number, dy: number) => {
      const cam = c.camera;
      const rect = el.getBoundingClientRect();
      const perPixel = (cam as THREE.OrthographicCamera).isOrthographicCamera
        ? 1 / Math.max(1e-6, cam.zoom)
        : (2 * c.distance * Math.tan(THREE.MathUtils.degToRad((cam as THREE.PerspectiveCamera).fov) / 2)) / rect.height;
      const tilt = Math.max(0.3, Math.cos(c.polarAngle)); // a vertical pixel covers more ground when the view is tilted
      void c.truck(dx * perPixel, 0, false);
      void c.forward((-dy * perPixel) / tilt, false);
      invalidate();
    };

    const onWheel = (event: WheelEvent) => {
      if ((event as unknown as Record<string, unknown>)[RIG_FLAG]) return; // our own, let it reach the controls
      event.preventDefault(); // never scroll or zoom the page over the canvas
      event.stopPropagation();
      const c = controls.current;
      if (!c || !usable()) return;
      if (!event.ctrlKey && !event.altKey && isTrackpadScroll(event)) {
        scrollPan(c, event.deltaX, event.deltaY);
        return;
      }
      zoomBy(wheelUnits(event), event.clientX, event.clientY);
    };

    // Safari (Mac) reports a trackpad pinch as gesture events and would zoom the whole page.
    let lastScale = 1;
    const onGestureStart = (event: Event) => {
      event.preventDefault();
      lastScale = 1;
    };
    const onGestureChange = (event: Event) => {
      event.preventDefault();
      const gesture = event as Event & { scale: number; clientX?: number; clientY?: number };
      const factor = gesture.scale / lastScale;
      lastScale = gesture.scale;
      if (touches > 0 || !(factor > 0) || !usable()) return; // a touch pinch is handled by the controls
      zoomBy(-Math.log(factor) / UNIT, gesture.clientX ?? lastX, gesture.clientY ?? lastY);
    };
    const onGestureEnd = (event: Event) => event.preventDefault();

    const stopPan = () => {
      pan = null;
      el.style.cursor = "grab";
    };

    const midpoint = (): [number, number, number] => {
      const [a, b] = [...fingers.values()];
      return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, Math.hypot(a[0] - b[0], a[1] - b[1])];
    };
    const startPinch = (c: CameraControlsImpl) => {
      pinch = null;
      if (!(c.camera as THREE.OrthographicCamera).isOrthographicCamera || fingers.size !== 2 || !c.enabled) return;
      const [x, y, spread] = midpoint();
      const target0 = c.getTarget(new THREE.Vector3());
      const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -target0.y);
      const snap = (c.camera as THREE.OrthographicCamera).clone();
      snap.updateMatrixWorld(true);
      const p0 = new THREE.Vector3();
      if (spread < 8 || !ground(snap, x, y, plane, p0)) return;
      pinch = { snap, plane, p0, target0, zoom0: snap.zoom, spread0: spread };
    };

    const onPointerDown = (event: PointerEvent) => {
      lastX = event.clientX;
      lastY = event.clientY;
      down = [event.clientX, event.clientY];
      if (event.pointerType === "touch") {
        touches++;
        fingers.set(event.pointerId, [event.clientX, event.clientY]);
        if (touches > 1) stopPan(); // two fingers: pinch on the 2D plan (below), the controls in 3D
        if (touches === 2 && controls.current && usable()) startPinch(controls.current);
      }
      const c = controls.current;
      if (!c || !usable() || !event.isPrimary) return;
      const mouse = event.pointerType === "mouse";
      if (mouse && event.button === 0 && (event.ctrlKey || event.altKey)) {
        restoreLeft = c.mouseButtons.left;
        c.mouseButtons.left = CameraControlsImpl.ACTION.ROTATE; // Ctrl or Alt + left drag rotates
        return;
      }
      const wantsPan = (mouse && (event.button === 0 || event.button === 1)) || (!mouse && touches === 1);
      if (!wantsPan || !c.enabled) return;
      startPan(c, event.pointerId, event.clientX, event.clientY);
    };

    const startPan = (c: CameraControlsImpl, pointerId: number, clientX: number, clientY: number) => {
      c.getTarget(v);
      const target0 = v.clone();
      const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -target0.y);
      const snap = c.camera.clone();
      snap.updateMatrixWorld(true);
      const p0 = new THREE.Vector3();
      if (!ground(snap, clientX, clientY, plane, p0)) return;
      pan = { pointerId, start: [clientX, clientY], snap, p0, target0, plane, moved: false };
    };

    const onPointerMove = (event: PointerEvent) => {
      lastX = event.clientX;
      lastY = event.clientY;
      if (fingers.has(event.pointerId)) fingers.set(event.pointerId, [event.clientX, event.clientY]);
      if (pinch && fingers.has(event.pointerId) && fingers.size === 2) {
        const c = controls.current;
        if (!c || !c.enabled) return void (pinch = null);
        // Exact: the ground point under the midpoint at the start stays under the midpoint at the new zoom.
        const [x, y, spread] = midpoint();
        const zoom = THREE.MathUtils.clamp((pinch.zoom0 * spread) / pinch.spread0, c.minZoom, c.maxZoom);
        scratch.copy(pinch.snap);
        scratch.zoom = zoom;
        scratch.updateProjectionMatrix();
        scratch.updateMatrixWorld(true);
        if (!ground(scratch, x, y, pinch.plane, hit)) return;
        void c.zoomTo(zoom, false);
        void c.moveTo(pinch.target0.x + (pinch.p0.x - hit.x), pinch.target0.y, pinch.target0.z + (pinch.p0.z - hit.z), false);
        invalidate();
        return;
      }
      if (!pan || event.pointerId !== pan.pointerId) return;
      const c = controls.current;
      // Another handler took the press (the draggable "you are here" dot disables the controls): back off.
      if (!c || !c.enabled || touches > 1) return stopPan();
      if (!pan.moved && Math.hypot(event.clientX - pan.start[0], event.clientY - pan.start[1]) < PAN_START_PX) return;
      pan.moved = true;
      el.style.cursor = "grabbing";
      // The pointer's ground point seen from the camera as it was at the press: the camera shifts by the difference.
      if (!ground(pan.snap, event.clientX, event.clientY, pan.plane, hit)) return;
      if (hit.distanceTo(pan.snap.position) > c.distance * 12) return;
      void c.moveTo(pan.target0.x + (pan.p0.x - hit.x), pan.target0.y, pan.target0.z + (pan.p0.z - hit.z), false);
      invalidate();
    };

    const onPointerEnd = (event: PointerEvent) => {
      if (event.pointerType === "touch") touches = Math.max(0, touches - 1);
      if (pan && event.pointerId === pan.pointerId) stopPan();
      const c = controls.current;
      if (fingers.delete(event.pointerId) && pinch) {
        pinch = null;
        // One finger left after a pinch: it goes on moving the map from where it is.
        const rest = [...fingers.entries()][0];
        if (c && rest && touches === 1 && usable()) startPan(c, rest[0], rest[1][0], rest[1][1]);
      }
      if (c && restoreLeft !== null && event.pointerType === "mouse") {
        c.mouseButtons.left = restoreLeft;
        restoreLeft = null;
      }
    };

    // A press that moved is a drag, never a click: the room under the pointer must not be selected on release.
    const onClick = (event: MouseEvent) => {
      if (Math.hypot(event.clientX - down[0], event.clientY - down[1]) > TAP_PX) {
        event.stopPropagation();
        event.preventDefault();
      }
    };
    const onMouseDown = (event: MouseEvent) => {
      if (event.button === 1) event.preventDefault(); // no middle-click autoscroll
    };
    const onDouble = (event: MouseEvent) => {
      if (usable()) onDoubleClick?.(event);
    };

    host.addEventListener("wheel", onWheel, { passive: false, capture: true });
    host.addEventListener("gesturestart", onGestureStart, { passive: false });
    host.addEventListener("gesturechange", onGestureChange, { passive: false });
    host.addEventListener("gestureend", onGestureEnd, { passive: false });
    host.addEventListener("pointerdown", onPointerDown, true);
    window.addEventListener("pointermove", onPointerMove, true);
    window.addEventListener("pointerup", onPointerEnd, true);
    window.addEventListener("pointercancel", onPointerEnd, true);
    host.addEventListener("click", onClick, true);
    host.addEventListener("mousedown", onMouseDown, true);
    host.addEventListener("dblclick", onDouble);
    return () => {
      el.style.cursor = "";
      host.removeEventListener("wheel", onWheel, true);
      host.removeEventListener("gesturestart", onGestureStart);
      host.removeEventListener("gesturechange", onGestureChange);
      host.removeEventListener("gestureend", onGestureEnd);
      host.removeEventListener("pointerdown", onPointerDown, true);
      window.removeEventListener("pointermove", onPointerMove, true);
      window.removeEventListener("pointerup", onPointerEnd, true);
      window.removeEventListener("pointercancel", onPointerEnd, true);
      host.removeEventListener("click", onClick, true);
      host.removeEventListener("mousedown", onMouseDown, true);
      host.removeEventListener("dblclick", onDouble);
    };
  }, [gl, camera, controls, onDoubleClick, active, invalidate]);
}
