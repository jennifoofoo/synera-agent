import { useEffect, useRef, type RefObject } from "react";
import * as THREE from "three";
import { useThree } from "@react-three/fiber";
import CameraControlsImpl from "camera-controls";
import { useTwin, type ViewHandover } from "../store";
import { classifyTwoFinger, distanceToOrthoZoom, FLAT_ENOUGH_POLAR, type FingerPair, HANDOVER_POLAR, type TwoFingerGesture, tiltForSwipe } from "./twoFinger";
import { createOrbitSwitch, createTwist, createWheelClassifier, orbitDelta } from "./wheelInput";

// Input model (like a map):
//  - left button or one finger: grab the map and pan (the point under the pointer stays under the pointer, no damping)
//  - right button, or Ctrl/Alt + left: rotate (3D: also tilt). Two fingers: pinch zoom + rotate + tilt in 3D;
//    on the 2D plan pinch zoom around the midpoint and move with it, no rotation
//  - middle button: pan. Mouse wheel and pinch: zoom to the pointer. Two-finger trackpad swipe: pan.
//  - Option/Alt + wheel or swipe: horizontal rotates, vertical tilts (3D). Safari two-finger twist: rotate.
//    Which wheel event is which: wheelInput.ts.
//  - 2D <-> 3D like Google Maps (docs/specs/swipe-tilt.md): two fingers pushed up together on the plan (twoFinger.ts
//    decides, a pinch never tilts) or Option/Alt + swipe up switch to 3D at the same spot and scale and keep tilting.
//    In 3D, two fingers down (or Option/Alt + swipe down, then a 300 ms pause) to nearly straight down go back to 2D.
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

/** Two fingers on the 2D plan: zoom by the finger spread around their midpoint, and move with the midpoint. */
interface Pinch {
  snap: THREE.OrthographicCamera;
  plane: THREE.Plane;
  p0: THREE.Vector3;
  target0: THREE.Vector3;
  zoom0: number;
  spread0: number;
  /** Finger positions at the start, and what the two fingers do (decided once per touch, see twoFinger.ts). */
  fingers0: FingerPair;
  gesture: TwoFingerGesture;
}

/** Fingers that switched the plan to 3D: they keep tilting the new 3D view until they lift. Lives in a ref, because
 * the switch makes a new camera and this hook's listeners are set up again in the middle of the touch. */
interface TiltSession {
  ids: [number, number];
  pos: Map<number, [number, number]>;
  y0: number;
}

/** Two fingers in 3D: at the release, a swipe down that left the view nearly straight down goes back to the plan. */
interface TiltBack {
  ids: [number, number];
  fingers0: FingerPair;
}

const OPTION_BACK_PAUSE_MS = 300;

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
  const tiltSession = useRef<TiltSession | null>(null);

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
    let back: TiltBack | null = null;
    let backTimer: ReturnType<typeof setTimeout> | undefined;
    const orbitSwitch = createOrbitSwitch();
    const usable = () => !(active && !active());
    el.style.cursor = "grab";

    /** The current view for the other camera (2D <-> 3D): target, px per metre in the image centre, heading. */
    const handoverFrom = (c: CameraControlsImpl): Omit<ViewHandover, "mode"> => {
      const t = c.getTarget(new THREE.Vector3());
      const cam = c.camera as THREE.PerspectiveCamera & THREE.OrthographicCamera;
      const flat = !!cam.isOrthographicCamera;
      const frameHeight = cam.view?.enabled ? cam.view.fullHeight : el.getBoundingClientRect().height;
      return {
        target: [t.x, t.y, t.z],
        scale: flat ? cam.zoom : distanceToOrthoZoom(c.distance, frameHeight, cam.fov),
        azimuth: c.azimuthAngle,
        polar: flat ? HANDOVER_POLAR : 0,
      };
    };
    const pairOf = (ids: readonly [number, number], pos: Map<number, [number, number]>): FingerPair | null => {
      const a = pos.get(ids[0]);
      const b = pos.get(ids[1]);
      return a && b ? [a, b] : null;
    };

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

    const classify = createWheelClassifier();
    const isFlat = (c: CameraControlsImpl) => !!(c.camera as THREE.OrthographicCamera).isOrthographicCamera;
    const onWheel = (event: WheelEvent) => {
      if ((event as unknown as Record<string, unknown>)[RIG_FLAG]) return; // our own, let it reach the controls
      event.preventDefault(); // never scroll or zoom the page over the canvas
      event.stopPropagation();
      const c = controls.current;
      if (!c || !usable()) return;
      const action = classify({
        deltaX: event.deltaX,
        deltaY: event.deltaY,
        deltaMode: event.deltaMode,
        ctrlKey: event.ctrlKey,
        altKey: event.altKey,
        timeStamp: event.timeStamp,
        wheelDeltaY: (event as WheelEvent & { wheelDeltaY?: number }).wheelDeltaY,
      });
      if (action === "pan") return scrollPan(c, event.deltaX, event.deltaY);
      if (action === "orbit") {
        const scale = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 400 : 1;
        const dx = event.deltaX * scale;
        const dy = event.deltaY * scale;
        const flat = isFlat(c);
        clearTimeout(backTimer);
        if (flat) {
          if (useTwin.getState().viewMode !== "2d") return; // switched already, the 3D camera is on its way
          const step = orbitSwitch.step(dx, dy, event.timeStamp);
          if (step === "switch") useTwin.getState().tiltTo3d(handoverFrom(c));
          if (step !== "rotate") return;
        }
        const [azimuth, polar] = orbitDelta(dx, dy, flat);
        void c.rotate(azimuth, polar, false);
        invalidate();
        // 3D swiped down to nearly straight down: back to the plan once the swipe pauses.
        if (!flat && dy < 0 && c.polarAngle < FLAT_ENOUGH_POLAR) {
          backTimer = setTimeout(() => {
            const now = controls.current;
            if (now && !isFlat(now) && now.polarAngle < FLAT_ENOUGH_POLAR && usable()) useTwin.getState().tiltTo2d(handoverFrom(now));
          }, OPTION_BACK_PAUSE_MS);
        }
        return;
      }
      zoomBy(wheelUnits(event), event.clientX, event.clientY);
    };

    // Safari (Mac) reports a trackpad pinch as gesture events and would zoom the whole page.
    // A two-finger twist on the trackpad (gesturechange rotation) turns the map, like Apple Maps.
    let lastScale = 1;
    const twist = createTwist();
    const onGestureStart = (event: Event) => {
      event.preventDefault();
      lastScale = 1;
      twist.reset();
    };
    const onGestureChange = (event: Event) => {
      event.preventDefault();
      const gesture = event as Event & { scale: number; rotation?: number; clientX?: number; clientY?: number };
      const factor = gesture.scale / lastScale;
      lastScale = gesture.scale;
      if (touches > 0 || !(factor > 0) || !usable()) return; // a touch pinch is handled by the controls
      zoomBy(-Math.log(factor) / UNIT, gesture.clientX ?? lastX, gesture.clientY ?? lastY);
      const turn = twist.step(gesture.rotation ?? 0);
      const c = controls.current;
      if (turn && c) {
        void c.rotate(turn, 0, false);
        invalidate();
      }
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
      const [a, b] = [...fingers.values()];
      pinch = { snap, plane, p0, target0, zoom0: snap.zoom, spread0: spread, fingers0: [[...a], [...b]], gesture: "undecided" };
    };

    /** Two fingers pushed up together on the plan: undo the little pinch so far and switch to 3D at the start view;
     * the fingers then keep tilting (tiltSession) until they lift. */
    const tiltUp = (c: CameraControlsImpl, p: Pinch) => {
      void c.zoomTo(p.zoom0, false);
      void c.moveTo(p.target0.x, p.target0.y, p.target0.z, false);
      const ids = [...fingers.keys()] as [number, number];
      const pos = new Map<number, [number, number]>([...fingers.entries()].map(([id, xy]) => [id, [xy[0], xy[1]]]));
      tiltSession.current = { ids, pos, y0: midpoint()[1] };
      pinch = null;
      useTwin.getState().tiltTo3d(handoverFrom(c));
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
        back = null;
        if (touches === 2 && fingers.size === 2 && controls.current && !isFlat(controls.current) && usable()) {
          const [a, b] = [...fingers.values()];
          back = { ids: [...fingers.keys()] as [number, number], fingers0: [[...a], [...b]] };
        }
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
      const session = tiltSession.current;
      if (session?.pos.has(event.pointerId)) {
        // The fingers that switched to 3D keep tilting it (the new controls never saw them go down).
        session.pos.set(event.pointerId, [event.clientX, event.clientY]);
        const pair = pairOf(session.ids, session.pos);
        const c = controls.current;
        if (pair && c && !isFlat(c)) {
          void c.rotatePolarTo(tiltForSwipe(session.y0 - (pair[0][1] + pair[1][1]) / 2, c.maxPolarAngle), false);
          invalidate();
        }
        return;
      }
      if (fingers.has(event.pointerId)) fingers.set(event.pointerId, [event.clientX, event.clientY]);
      if (pinch && fingers.has(event.pointerId) && fingers.size === 2) {
        const c = controls.current;
        if (!c || !c.enabled) return void (pinch = null);
        if (pinch.gesture === "undecided") {
          const [a, b] = [...fingers.values()];
          pinch.gesture = classifyTwoFinger(pinch.fingers0, [a, b]);
          if (pinch.gesture === "tilt-up" && usable()) return tiltUp(c, pinch);
        }
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
      if (tiltSession.current?.pos.has(event.pointerId)) tiltSession.current = null; // a finger lifted: tilting ends
      if (back?.ids.includes(event.pointerId)) {
        // Released after two fingers in 3D: a swipe down (not a pinch) that left the view nearly straight down.
        const last = pairOf(back.ids, fingers);
        const swipe = last ? classifyTwoFinger(back.fingers0, last) : "undecided";
        back = null;
        if (swipe === "tilt-down" && c && !isFlat(c) && c.polarAngle < FLAT_ENOUGH_POLAR && usable()) useTwin.getState().tiltTo2d(handoverFrom(c));
      }
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
      clearTimeout(backTimer);
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
