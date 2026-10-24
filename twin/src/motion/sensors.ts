import { headingFromOrientation, type HeadingReading } from "./heading";
import type { AccelSample, MotionStatus } from "./types";

/** Device sensors: feature detection, the iOS permission prompt and listeners. Never throws.
 *
 * iOS 13+: DeviceMotionEvent.requestPermission() and DeviceOrientationEvent.requestPermission() exist and must be
 * called from a user gesture (a tap). Every browser hides the sensors on plain http (except localhost):
 * the phone demo needs the https tunnel (scripts/tunnel.sh). */

type PermissionFn = () => Promise<"granted" | "denied" | "default">;
type WithPermission = { requestPermission?: PermissionFn };

let granted: boolean | null = null; // result of the last permission request in this page

function hasWindow(): boolean {
  return typeof window !== "undefined";
}

function motionCtor(): (WithPermission & object) | undefined {
  return hasWindow() ? (window as unknown as { DeviceMotionEvent?: WithPermission & object }).DeviceMotionEvent : undefined;
}

function orientationCtor(): (WithPermission & object) | undefined {
  return hasWindow()
    ? (window as unknown as { DeviceOrientationEvent?: WithPermission & object }).DeviceOrientationEvent
    : undefined;
}

/** True when the browser wants an explicit permission tap (iOS Safari 13+). */
export function needsPermissionPrompt(): boolean {
  return typeof motionCtor()?.requestPermission === "function";
}

/** What the sensors can do before start(): unsupported | needs-https | needs-permission | denied | ready. */
export function motionSupport(): MotionStatus {
  if (!hasWindow() || !motionCtor()) return "unsupported";
  if (window.isSecureContext === false) return "needs-https";
  if (granted === false) return "denied";
  if (needsPermissionPrompt() && granted !== true) return "needs-permission";
  return "ready";
}

/** Ask for motion and orientation access. Call it directly in the tap handler of the "Walk with me" switch
 * (iOS rejects the prompt outside a user gesture). Resolves to the new status; never rejects. */
export async function requestMotionPermission(): Promise<MotionStatus> {
  const before = motionSupport();
  if (before === "unsupported" || before === "needs-https") return before;
  const motion = motionCtor()?.requestPermission;
  if (typeof motion !== "function") {
    granted = true;
    return "ready";
  }
  const orientation = orientationCtor()?.requestPermission;
  try {
    // both prompts start inside the same gesture; awaiting the first would lose the gesture for the second
    const [motionResult, orientationResult] = await Promise.all([
      motion.call(motionCtor()),
      typeof orientation === "function" ? orientation.call(orientationCtor()).catch(() => "denied" as const) : Promise.resolve("granted" as const),
    ]);
    granted = motionResult === "granted";
    void orientationResult; // without the compass the walk still works, only the heading check is off
    return granted ? "ready" : "denied";
  } catch {
    // thrown when not called from a gesture, or blocked by the browser
    granted = false;
    return "denied";
  }
}

export interface SensorHandlers {
  onAccel: (sample: AccelSample) => void;
  onHeading: (reading: HeadingReading) => void;
}

/** Start listening. Returns a stop function. Does nothing (and returns a no-op) without a window. */
export function listenToSensors(handlers: SensorHandlers): () => void {
  if (!hasWindow()) return () => {};
  const onMotion = (event: DeviceMotionEvent) => {
    const a = event.accelerationIncludingGravity;
    if (!a || a.x === null || a.y === null || a.z === null) return;
    handlers.onAccel({ t: event.timeStamp || performance.now(), x: a.x, y: a.y, z: a.z });
  };
  const screenAngle = () => (typeof screen !== "undefined" && screen.orientation ? screen.orientation.angle : 0);
  const onOrientation = (event: DeviceOrientationEvent) => {
    const reading = headingFromOrientation({
      alpha: event.alpha,
      absolute: event.absolute || event.type === "deviceorientationabsolute",
      webkitCompassHeading: (event as DeviceOrientationEvent & { webkitCompassHeading?: number }).webkitCompassHeading,
      screenAngle: screenAngle(),
    });
    if (reading) handlers.onHeading(reading);
  };
  // Android Chrome sends north-referenced alpha only on deviceorientationabsolute
  const orientationEvent = "ondeviceorientationabsolute" in window ? "deviceorientationabsolute" : "deviceorientation";
  window.addEventListener("devicemotion", onMotion);
  window.addEventListener(orientationEvent, onOrientation as EventListener);
  return () => {
    window.removeEventListener("devicemotion", onMotion);
    window.removeEventListener(orientationEvent, onOrientation as EventListener);
  };
}

/** For tests only: forget the remembered permission answer. */
export function resetPermissionMemory(): void {
  granted = null;
}
