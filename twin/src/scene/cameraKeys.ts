import { useEffect, useRef, type RefObject } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import type CameraControlsImpl from "camera-controls";
import { useKeyHelp } from "./controlsTable";

// Held-key camera motion (table: controlsTable.ts). Keys are tracked as "held" and applied once per frame with the
// frame's delta time, so motion is smooth, does not depend on key repeat and stops on keyup, blur and tab switch.

type Action = "forward" | "back" | "left" | "right" | "rotateLeft" | "rotateRight" | "zoomIn" | "zoomOut";

const BY_CODE: Record<string, Action> = {
  KeyW: "forward",
  ArrowUp: "forward",
  KeyS: "back",
  ArrowDown: "back",
  KeyA: "left",
  ArrowLeft: "left",
  KeyD: "right",
  ArrowRight: "right",
  KeyQ: "rotateLeft",
  KeyE: "rotateRight",
  KeyR: "zoomIn",
  NumpadAdd: "zoomIn",
  KeyF: "zoomOut",
  NumpadSubtract: "zoomOut",
};

const PAN_PER_SECOND = 0.5; // of the view height per second
const ROTATE_PER_SECOND = 1.3; // rad
const ZOOM_PER_SECOND = 1.0; // e-folds per second
const FAST = 3;

/** True when the key belongs to a field, list, chat or autocomplete: the camera never takes those. */
export function isTypingTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  if (!element || !element.tagName) return false;
  if (element.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(element.tagName)) return true;
  return !!element.closest?.(".planner-sheet, .directions, .omnibox, .autocomplete, [cmdk-root], [role='listbox'], [role='combobox'], [role='dialog']");
}

function actionFor(event: KeyboardEvent): Action | null {
  const byCode = BY_CODE[event.code];
  if (byCode) return byCode;
  if (event.key === "+" || event.key === "=") return "zoomIn"; // layouts differ: "+" is not on the same key everywhere
  if (event.key === "-" || event.key === "_") return "zoomOut";
  return null;
}

interface Options {
  controls: RefObject<CameraControlsImpl>;
  flat: boolean;
  /** False while this canvas is not the one in use (hidden behind the campus view). */
  active?: () => boolean;
  /** Home, 0. */
  onHome: () => void;
  /** One-shot keys of the host (floors, 2D/3D). Return true when handled. */
  onKey?: (event: KeyboardEvent) => boolean;
}

export function useCameraKeys({ controls, flat, active, onHome, onKey }: Options) {
  const invalidate = useThree((s) => s.invalidate);
  const size = useThree((s) => s.size);
  const held = useRef(new Map<string, Action>());
  const shift = useRef(false);
  const latest = useRef({ flat, onHome, onKey, active, size });
  latest.current = { flat, onHome, onKey, active, size };

  useEffect(() => {
    const clear = () => {
      held.current.clear();
      shift.current = false;
    };
    const onDown = (event: KeyboardEvent) => {
      shift.current = event.shiftKey;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      const { active: isActive, onHome: home, onKey: extra } = latest.current;
      if (isActive && !isActive()) return;
      if (useKeyHelp.getState().open) return; // KeyHelp closes itself on any key and swallows it
      const action = actionFor(event);
      if (action) {
        event.preventDefault();
        held.current.set(event.code, action);
        invalidate();
        return;
      }
      if (event.key === "Home" || event.key === "0") {
        event.preventDefault();
        home();
      } else if (event.key === "?" || event.key === "h" || event.key === "H") {
        event.preventDefault();
        useKeyHelp.getState().setOpen(true);
      } else if (extra?.(event)) {
        event.preventDefault();
      }
    };
    const onUp = (event: KeyboardEvent) => {
      shift.current = event.shiftKey;
      held.current.delete(event.code);
    };
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    window.addEventListener("blur", clear);
    document.addEventListener("visibilitychange", clear);
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
      window.removeEventListener("blur", clear);
      document.removeEventListener("visibilitychange", clear);
    };
  }, [invalidate]);

  const direction = useRef(new THREE.Vector2());
  // Before camera-controls' own update (priority -1), so a step shows in the same frame.
  useFrame((_, delta) => {
    const actions = held.current;
    if (!actions.size) return;
    const c = controls.current;
    if (!c) return;
    const dt = Math.min(delta, 0.1);
    const fast = shift.current ? FAST : 1;
    const has = (action: Action) => [...actions.values()].includes(action);
    const cam = c.camera as THREE.PerspectiveCamera & THREE.OrthographicCamera;
    const ortho = !!cam.isOrthographicCamera;
    // World units that cross the view per second: the view height at the target (perspective) or at this zoom (plan).
    const view = ortho ? latest.current.size.height / cam.zoom : 2 * c.distance * Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2);
    const step = view * PAN_PER_SECOND * dt * fast;
    direction.current.set((has("right") ? 1 : 0) - (has("left") ? 1 : 0), (has("forward") ? 1 : 0) - (has("back") ? 1 : 0));
    if (direction.current.x) void c.truck(direction.current.x * step, 0, false);
    if (direction.current.y) void c.forward(direction.current.y * step, false);
    const turn = (has("rotateRight") ? 1 : 0) - (has("rotateLeft") ? 1 : 0);
    if (turn) void c.rotate(-turn * ROTATE_PER_SECOND * dt * fast, 0, false);
    const zoom = (has("zoomIn") ? 1 : 0) - (has("zoomOut") ? 1 : 0);
    if (zoom) {
      const factor = Math.exp(zoom * ZOOM_PER_SECOND * dt * fast);
      if (ortho) void c.zoomTo(cam.zoom * factor, false);
      else void c.dollyTo(c.distance / factor, false);
    }
    invalidate(); // frameloop="demand": keep drawing while a key is held
  }, -2);
}
