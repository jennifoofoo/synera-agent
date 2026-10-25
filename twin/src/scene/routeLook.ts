// The look of the route line in one place (RouteLine.tsx draws it, 2D and 3D alike): one solid Synera-blue line on a
// thin darker casing, both opaque. No halo, no glow, no ghost of an earlier route: overlapping translucent Line2
// layers were what made the route read as several bands (their round caps double-blend at every joint).

import type { Point } from "../api/types";
import { COLOURS } from "../model/palette";

/** Route line width on screen (px) and its darker casing on each side (px). */
export const ROUTE_LINE_PX = 6;
export const ROUTE_CASING_PX = 1.5;
/** The part of the route outside the current guide leg: the same blue mixed toward white (opaque, never alpha). */
const PALE_MIX = 0.6;

export interface RouteLayer {
  name: "route-casing" | "route-line";
  colour: string;
  widthPx: number;
  renderOrder: number;
}

function mix(hex: string, toward: string, amount: number): string {
  const a = Number.parseInt(hex.slice(1), 16);
  const b = Number.parseInt(toward.slice(1), 16);
  const channel = (shift: number) => Math.round(((a >> shift) & 255) * (1 - amount) + ((b >> shift) & 255) * amount);
  return `#${((channel(16) << 16) | (channel(8) << 8) | channel(0)).toString(16).padStart(6, "0")}`;
}

/** The route's layers, bottom to top: exactly one casing and one line, both opaque. `pale`: the line is the
 * background for a guide leg drawn on top (same layers, paler colours). */
export function routeLayers(pale = false): RouteLayer[] {
  const casing = pale ? mix(COLOURS.mapBlueDark, "#ffffff", PALE_MIX) : COLOURS.mapBlueDark;
  const line = pale ? mix(COLOURS.signal, "#ffffff", PALE_MIX) : COLOURS.signal;
  return [
    { name: "route-casing", colour: casing, widthPx: ROUTE_LINE_PX + 2 * ROUTE_CASING_PX, renderOrder: 20 },
    { name: "route-line", colour: line, widthPx: ROUTE_LINE_PX, renderOrder: 21 },
  ];
}

/** Drop repeated points and points that lie on the straight line between their neighbours (within `tolerance` m):
 * the server sends door approaches as extra collinear points, and every extra vertex is one more joint to draw. */
export function simplifyPolyline(points: Point[], tolerance = 0.02): Point[] {
  const unique: Point[] = [];
  for (const point of points) {
    const last = unique[unique.length - 1];
    if (!last || Math.hypot(point[0] - last[0], point[1] - last[1]) > tolerance) unique.push(point);
  }
  if (unique.length < 3) return unique;
  const result: Point[] = [unique[0]];
  for (let i = 1; i < unique.length - 1; i++) {
    const a = result[result.length - 1];
    const b = unique[i];
    const c = unique[i + 1];
    const length = Math.hypot(c[0] - a[0], c[1] - a[1]);
    const offLine = length < 1e-9 ? 0 : Math.abs((c[0] - a[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (c[1] - a[1])) / length;
    // keep b if it bends the line, or if it lies outside the a..c span (a turn back)
    const t = length < 1e-9 ? 0 : ((b[0] - a[0]) * (c[0] - a[0]) + (b[1] - a[1]) * (c[1] - a[1])) / (length * length);
    if (offLine > tolerance || t < 0 || t > 1) result.push(b);
  }
  result.push(unique[unique.length - 1]);
  return result;
}
