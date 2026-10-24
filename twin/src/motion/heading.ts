import type { Point } from "./types";

/** Compass heading helpers. All angles in degrees, clockwise from north, in [0, 360).
 *
 * Model frame: +y is north in the data, unless the building is rotated. `northOffsetDeg` is the compass bearing
 * of the model's +y axis (0 = +y points north, 90 = +y points east). */

export function normalizeDeg(deg: number): number {
  return ((deg % 360) + 360) % 360;
}

/** Smallest absolute difference between two bearings, 0 to 180. */
export function angleDiff(a: number, b: number): number {
  const d = Math.abs(normalizeDeg(a) - normalizeDeg(b));
  return d > 180 ? 360 - d : d;
}

/** Bearing of the model direction a -> b in model degrees (0 = +y, 90 = +x), or null for a zero-length step. */
export function modelBearing(a: Point, b: Point): number | null {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  if (Math.hypot(dx, dy) < 1e-6) return null;
  return normalizeDeg((Math.atan2(dx, dy) * 180) / Math.PI);
}

/** Model bearing -> compass bearing. */
export function modelToCompass(modelDeg: number, northOffsetDeg = 0): number {
  return normalizeDeg(modelDeg + northOffsetDeg);
}

/** The orientation fields we read (DeviceOrientationEvent plus iOS's webkitCompassHeading). */
export interface OrientationReading {
  alpha: number | null;
  absolute?: boolean;
  webkitCompassHeading?: number | null;
  /** screen.orientation.angle (0, 90, 180, 270), so a phone held sideways still points the right way */
  screenAngle?: number;
}

export interface HeadingReading {
  deg: number;
  /** true when the heading is relative to north (iOS compass, Android deviceorientationabsolute) */
  absolute: boolean;
}

/** Compass heading from one orientation event, or null if the event carries none. */
export function headingFromOrientation(reading: OrientationReading): HeadingReading | null {
  const screen = reading.screenAngle ?? 0;
  const compass = reading.webkitCompassHeading;
  if (typeof compass === "number" && Number.isFinite(compass) && compass >= 0) {
    // iOS: already clockwise from magnetic north, for the device in portrait
    return { deg: normalizeDeg(compass + screen), absolute: true };
  }
  if (typeof reading.alpha === "number" && Number.isFinite(reading.alpha)) {
    // W3C alpha turns counter-clockwise; it is only relative to north when the event is absolute
    return { deg: normalizeDeg(360 - reading.alpha + screen), absolute: reading.absolute === true };
  }
  return null;
}

/** Circular mean over the last `size` headings (a plain mean breaks at 359 -> 0). */
export class HeadingSmoother {
  private readonly size: number;
  private values: number[] = [];

  constructor(size = 8) {
    this.size = Math.max(1, size);
  }

  push(deg: number): number | null {
    if (!Number.isFinite(deg)) return this.value();
    this.values = [...this.values.slice(-(this.size - 1)), deg];
    return this.value();
  }

  value(): number | null {
    return circularMean(this.values);
  }

  reset(): void {
    this.values = [];
  }
}

export function circularMean(degs: number[]): number | null {
  if (!degs.length) return null;
  let s = 0;
  let c = 0;
  for (const d of degs) {
    s += Math.sin((d * Math.PI) / 180);
    c += Math.cos((d * Math.PI) / 180);
  }
  if (Math.hypot(s, c) < 1e-9) return null; // headings cancel out, no direction
  return normalizeDeg((Math.atan2(s, c) * 180) / Math.PI);
}
