// Small display formatters shared by the card and the scene.

import type { Point } from "../api/types";

/** A point in model metres as "12.3, 5.7 m" (one decimal, never "-0.0"). */
export function formatPoint(point: Point): string {
  const one = (value: number) => {
    const text = (Math.round(value * 10) / 10).toFixed(1);
    return text === "-0.0" ? "0.0" : text;
  };
  return `${one(point[0])}, ${one(point[1])} m`;
}

/** True when two points are the same spot (within a centimetre). */
export function samePoint(a: Point | null | undefined, b: Point | null | undefined): boolean {
  return !!a && !!b && Math.abs(a[0] - b[0]) < 0.011 && Math.abs(a[1] - b[1]) < 0.011;
}
