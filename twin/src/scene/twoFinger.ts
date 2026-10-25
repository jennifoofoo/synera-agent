// Two-finger touch gestures on the map and the 2D <-> 3D view handover (docs/specs/swipe-tilt.md).
// Pure (no DOM, no three.js), unit tested in twoFinger.test.ts.
//
// Classifying two fingers: a pinch must never tilt, so every rule errs towards "pinch".
//  1. The finger spread changed by 12 percent or more, or the fingers turned by 15 degrees or more: pinch.
//  2. The midpoint moved less than 24 px: undecided (the caller keeps pinching as before).
//  3. Both fingers moved up by at least 10 px each and the midpoint moved mostly vertically (|dy| > 2 |dx|): tilt-up.
//     The same downwards: tilt-down.
//  4. Anything else: pan (two fingers moving together, sideways or diagonally).

export type Point = readonly [number, number];
export type FingerPair = readonly [Point, Point];
export type TwoFingerGesture = "pinch" | "tilt-up" | "tilt-down" | "pan" | "undecided";

export const SPREAD_CHANGE_MAX = 0.12;
export const TURN_MAX_RAD = (15 * Math.PI) / 180;
export const FINGER_MIN_PX = 10;
export const MIDPOINT_DECIDE_PX = 24;

/** Polar angle (radians from straight down) the 3D view starts at after a swipe up from the plan. */
export const HANDOVER_POLAR = 0.1;
/** Radians of tilt per pixel the fingers move up after the switch (until they lift). */
export const TILT_RAD_PER_PX = 0.006;
/** Below this polar angle (about 17 degrees) a 3D view counts as nearly straight down: a swipe down that ends here goes
 * back to the plan. Fingers rarely land exactly on the top, so this is not tighter. */
export const FLAT_ENOUGH_POLAR = 0.3;

const spread = ([a, b]: FingerPair) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const angle = ([a, b]: FingerPair) => Math.atan2(b[1] - a[1], b[0] - a[0]);

export function classifyTwoFinger(start: FingerPair, now: FingerPair): TwoFingerGesture {
  const s0 = spread(start);
  if (!(s0 > 1)) return "pinch"; // fingers on top of each other: no reliable direction
  if (Math.abs(spread(now) - s0) / s0 >= SPREAD_CHANGE_MAX) return "pinch";
  const turn = Math.abs(Math.atan2(Math.sin(angle(now) - angle(start)), Math.cos(angle(now) - angle(start))));
  if (turn >= TURN_MAX_RAD) return "pinch";
  const dyA = now[0][1] - start[0][1];
  const dyB = now[1][1] - start[1][1];
  const mx = (now[0][0] + now[1][0] - start[0][0] - start[1][0]) / 2;
  const my = (dyA + dyB) / 2;
  if (Math.hypot(mx, my) < MIDPOINT_DECIDE_PX) return "undecided";
  const vertical = Math.abs(my) > 2 * Math.abs(mx);
  if (vertical && dyA <= -FINGER_MIN_PX && dyB <= -FINGER_MIN_PX) return "tilt-up";
  if (vertical && dyA >= FINGER_MIN_PX && dyB >= FINGER_MIN_PX) return "tilt-down";
  return "pan";
}

/** Distance of a perspective camera that shows the same metres per pixel in the image centre as an orthographic
 * camera at `zoom` (px per metre). `frameHeightPx` is the full frame height the projection is built for, `fovDeg`
 * the perspective camera's vertical field of view (always the real camera's, Scene.tsx may change it). */
export function orthoZoomToDistance(zoom: number, frameHeightPx: number, fovDeg: number): number {
  return frameHeightPx / (2 * zoom * Math.tan((fovDeg * Math.PI) / 360));
}

/** Inverse of orthoZoomToDistance. */
export function distanceToOrthoZoom(distance: number, frameHeightPx: number, fovDeg: number): number {
  return frameHeightPx / (2 * distance * Math.tan((fovDeg * Math.PI) / 360));
}

/** Option/Alt + mouse drag (button held), the mouse twin of the two-finger swipe:
 *  - on the plan, a drag mostly up (|dy| > 2 |dx|) by OPTION_DRAG_SWITCH_PX switches to 3D and keeps tilting;
 *  - in 3D, a drag mostly down by as much that leaves the view nearly straight down goes back at the release;
 *  - a drag that goes sideways first (OPTION_DRAG_SIDEWAYS_PX) rotates as before and never switches.
 * `dx`, `dy`: the pointer's move since the press (screen px, y down). */
export const OPTION_DRAG_SWITCH_PX = 40;
export const OPTION_DRAG_SIDEWAYS_PX = 12;
export type OptionDrag = "tilt-up" | "tilt-down" | "rotate" | "undecided";

export function classifyOptionDrag(dx: number, dy: number): OptionDrag {
  const vertical = Math.abs(dy) > 2 * Math.abs(dx);
  if (vertical && -dy >= OPTION_DRAG_SWITCH_PX) return "tilt-up";
  if (vertical && dy >= OPTION_DRAG_SWITCH_PX) return "tilt-down";
  if (!vertical && Math.abs(dx) >= OPTION_DRAG_SIDEWAYS_PX) return "rotate";
  return "undecided";
}

/** Polar angle while the fingers keep moving up after the switch to 3D (`upPx` > 0 is up), within the 3D limits. */
export function tiltForSwipe(upPx: number, maxTilt: number): number {
  return Math.min(maxTilt, Math.max(HANDOVER_POLAR, HANDOVER_POLAR + upPx * TILT_RAD_PER_PX));
}
