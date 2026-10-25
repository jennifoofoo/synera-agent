// Wheel classification for the map: is a wheel event a trackpad pinch, a two-finger trackpad swipe, a mouse notch,
// or an Option/Alt orbit? Pure (no DOM), so it is unit tested in wheelInput.test.ts with recorded-like sequences.
//
//  - ctrlKey: a trackpad pinch (Chrome and Firefox send pinch as ctrl + wheel). Zoom to the cursor.
//  - altKey: orbit. Horizontal rotates, vertical tilts (3D). Works for a trackpad swipe and a mouse wheel alike.
//  - otherwise the device decides: a trackpad swipe pans, a mouse notch zooms.
//
// Device rules, first match wins:
//  1. deltaMode 1 or 2 (lines, pages): mouse.
//  2. Inside a running gesture (the previous event came less than GESTURE_GAP_MS ago): the device of that gesture.
//     A swipe never turns into a zoom halfway, momentum included.
//  3. Any sideways delta: trackpad.
//  4. Legacy wheelDeltaY (Chrome, Safari): a trackpad reports exactly -3 x deltaY; a mouse whole multiples of 120.
//  5. Fractional deltaY: trackpad.
//  6. A large whole step on Y only (>= 50 px): mouse. A small one: trackpad.

export type WheelAction = "pinch" | "orbit" | "pan" | "zoom";
export type WheelDevice = "mouse" | "trackpad";

export interface WheelSample {
  deltaX: number;
  deltaY: number;
  deltaMode: number;
  ctrlKey: boolean;
  altKey: boolean;
  timeStamp: number;
  /** Legacy, non-standard (Chrome and Safari): 0 or undefined when missing. */
  wheelDeltaY?: number;
}

export const GESTURE_GAP_MS = 150;
const MOUSE_STEP_PX = 50;

/** The device of one event on its own (no history). */
export function wheelDevice(event: WheelSample): WheelDevice {
  if (event.deltaMode !== 0) return "mouse";
  if (event.deltaX !== 0) return "trackpad";
  const legacy = event.wheelDeltaY ?? 0;
  if (legacy !== 0 && event.deltaY !== 0) {
    if (Math.abs(legacy + 3 * event.deltaY) < 1) return "trackpad";
    if (Math.abs(legacy) % 120 === 0) return "mouse";
  }
  if (!Number.isInteger(event.deltaY)) return "trackpad";
  return Math.abs(event.deltaY) >= MOUSE_STEP_PX ? "mouse" : "trackpad";
}

/** A classifier with memory of the running gesture (one per canvas). */
export function createWheelClassifier() {
  let lastTime = -Infinity;
  let lastDevice: WheelDevice | null = null;
  return (event: WheelSample): WheelAction => {
    const running = event.timeStamp - lastTime < GESTURE_GAP_MS && event.timeStamp >= lastTime;
    lastTime = event.timeStamp;
    const device: WheelDevice = event.deltaMode !== 0 ? "mouse" : running && lastDevice ? lastDevice : wheelDevice(event);
    lastDevice = device;
    if (event.ctrlKey) return "pinch";
    if (event.altKey) return "orbit";
    return device === "trackpad" ? "pan" : "zoom";
  };
}

/** Radians per scrolled pixel for an Option/Alt orbit (a 300 px swipe turns about 70 degrees). */
export const ORBIT_RAD_PER_PX = 0.004;

/** Azimuth and polar change for an orbit. 2D has no tilt, so there both axes rotate. */
export function orbitDelta(deltaX: number, deltaY: number, flat: boolean): [number, number] {
  if (flat) return [-(deltaX + deltaY) * ORBIT_RAD_PER_PX, 0];
  return [-deltaX * ORBIT_RAD_PER_PX, deltaY * ORBIT_RAD_PER_PX];
}

/** Safari twist (gesturechange rotation, degrees, cumulative): rotation starts after a small dead zone so a pinch
 * does not turn the map by accident. Returns the azimuth change in radians for this event. */
export function createTwist(deadZoneDeg = 8) {
  let last = 0;
  let engaged = false;
  return {
    reset() {
      last = 0;
      engaged = false;
    },
    step(rotationDeg: number): number {
      if (!engaged) {
        if (Math.abs(rotationDeg) < deadZoneDeg) return 0;
        engaged = true;
        last = rotationDeg;
        return 0;
      }
      const delta = rotationDeg - last;
      last = rotationDeg;
      return (delta * Math.PI) / 180;
    },
  };
}
