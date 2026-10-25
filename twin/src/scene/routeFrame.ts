// Framing a drawn route (or a planned round): the camera shows the whole route on the shown floor, start dot to
// end pin, inside the FREE part of the map: below the top bar, above the dock and sheet, beside the floor rail and
// the chat column, with some padding. Pure math here (vitest: routeFrame.test.ts), CameraRig applies the result.

import * as THREE from "three";
import type { RouteSegment } from "../api/types";

/** A screen rectangle in px (CSS, relative to the same origin). */
export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** The padding (px) around the framed route inside the free area. */
export const FRAME_PAD_PX = 24;
/** A short route is not blown up: the framed area spans at least this many metres each way. */
export const MIN_SPAN_M = 10;
/** The free area never shrinks below this (px); a sheet covering nearly everything falls back to the whole canvas. */
const MIN_FREE_PX = 100;
/** The destination pin and the room labels stand above their point on the route (px). */
export const END_MARKER_PX = 44;
/** 3D: a route is framed from at most this angle from straight down (rad), so walls hide little of it. */
export const ROUTE_POLAR_MAX = 0.8;

/** Padding (px) for a canvas of this size: 24 px on a phone, more air on a laptop map. */
export function framePad(width: number, height: number): number {
  return Math.max(FRAME_PAD_PX, Math.round(0.07 * Math.min(width, height)));
}

/** Room above the framed route for the pin and labels that stand on its points (unless the area gets too small). */
export function withEndMarkers(free: Rect, extra = END_MARKER_PX): Rect {
  return free.bottom - (free.top + extra) >= MIN_FREE_PX ? { ...free, top: free.top + extra } : free;
}

/** The part of `canvas` no UI element in `covers` lies on. Each cover cuts the free area from the side that loses
 * the least of it (a full-width top bar cuts the top, a narrow rail on the right cuts the right, ...); covers outside
 * the canvas or empty (hidden) are ignored. Then `pad` px of air. Falls back to the padded canvas if too small. */
export function freeRect(canvas: Rect, covers: Rect[], pad = FRAME_PAD_PX): Rect {
  const free = { ...canvas };
  for (const cover of covers) {
    const left = Math.max(cover.left, free.left);
    const right = Math.min(cover.right, free.right);
    const top = Math.max(cover.top, free.top);
    const bottom = Math.min(cover.bottom, free.bottom);
    if (right - left < 1 || bottom - top < 1) continue; // not over the free area
    const width = free.right - free.left;
    const height = free.bottom - free.top;
    // the area left after each possible cut
    const options: [keyof Rect, number, number][] = [
      ["top", bottom, (free.bottom - bottom) * width],
      ["bottom", top, (top - free.top) * width],
      ["left", right, (free.right - right) * height],
      ["right", left, (left - free.left) * height],
    ];
    options.sort((a, b) => b[2] - a[2]);
    const [side, edge] = options[0];
    free[side] = edge;
  }
  const padded = { left: free.left + pad, top: free.top + pad, right: free.right - pad, bottom: free.bottom - pad };
  if (padded.right - padded.left < MIN_FREE_PX || padded.bottom - padded.top < MIN_FREE_PX) {
    return { left: canvas.left + pad, top: canvas.top + pad, right: canvas.right - pad, bottom: canvas.bottom - pad };
  }
  return padded;
}

/** The route's points on `floorId` (all floors when null) in scene space, plus the corners of a square of
 * `minSpan` m around their centre (so a 5 m route is not framed at room-filling zoom). Empty if nothing is there. */
export function routeFramePoints(
  segments: RouteSegment[],
  floorId: string | null,
  floorY: (id: string) => number,
  lift = 0,
  minSpan = MIN_SPAN_M,
): THREE.Vector3[] {
  const points: THREE.Vector3[] = [];
  for (const segment of segments) {
    if (floorId && segment.floor_id !== floorId) continue;
    const y = floorY(segment.floor_id) + lift;
    for (const [x, z] of segment.points) points.push(new THREE.Vector3(x, y, -z));
  }
  if (!points.length) return points;
  const box = new THREE.Box3().setFromPoints(points);
  const centre = box.getCenter(new THREE.Vector3());
  const half = minSpan / 2;
  for (const dx of [-half, half]) for (const dz of [-half, half]) points.push(new THREE.Vector3(centre.x + dx, centre.y, centre.z + dz));
  return points;
}

export interface FrameResult {
  position: THREE.Vector3;
  target: THREE.Vector3;
  /** Orthographic only: the zoom (px per metre). */
  zoom?: number;
}

/** The camera that shows all `points` inside `free` (px within a canvas of `size`), seen from `azimuth` / `polar`
 * (kept as they are). Projects with a copy of the real camera (its view offset and frustum included): the largest
 * zoom (orthographic) or the smallest distance (perspective) at which the points fit, then the target is moved so
 * their projection sits in the middle of the free area. */
export function fitPointsInRect(
  camera: THREE.Camera,
  points: THREE.Vector3[],
  free: Rect,
  size: { width: number; height: number },
  azimuth: number,
  polar: number,
): FrameResult | null {
  if (!points.length || size.width < 1 || size.height < 1) return null;
  const ortho = (camera as THREE.OrthographicCamera).isOrthographicCamera === true;
  const probe = (camera as THREE.PerspectiveCamera | THREE.OrthographicCamera).clone();
  const lo = new THREE.Vector2(-1 + (2 * free.left) / size.width, 1 - (2 * free.bottom) / size.height);
  const hi = new THREE.Vector2(-1 + (2 * free.right) / size.width, 1 - (2 * free.top) / size.height);
  const direction = new THREE.Vector3().setFromSpherical(new THREE.Spherical(1, polar, azimuth));
  const box = new THREE.Box3().setFromPoints(points);
  const target = box.getCenter(new THREE.Vector3());
  const radius = Math.max(1, box.getBoundingSphere(new THREE.Sphere()).radius);
  const orthoDistance = Math.max(50, radius * 4);
  const point = new THREE.Vector3();
  const place = (scale: number) => {
    if (ortho) {
      (probe as THREE.OrthographicCamera).zoom = scale;
      probe.position.copy(target).addScaledVector(direction, orthoDistance);
    } else {
      probe.position.copy(target).addScaledVector(direction, scale);
    }
    probe.up.set(0, 1, 0);
    probe.lookAt(target);
    probe.updateMatrixWorld(true);
    probe.updateProjectionMatrix();
  };
  const extent = (scale: number) => {
    place(scale);
    const min = new THREE.Vector2(Infinity, Infinity);
    const max = new THREE.Vector2(-Infinity, -Infinity);
    for (const p of points) {
      point.copy(p).project(probe);
      min.set(Math.min(min.x, point.x), Math.min(min.y, point.y));
      max.set(Math.max(max.x, point.x), Math.max(max.y, point.y));
    }
    return { min, max };
  };
  const fits = (scale: number) => {
    const { min, max } = extent(scale);
    return max.x - min.x <= hi.x - lo.x && max.y - min.y <= hi.y - lo.y;
  };
  let scale = ortho ? 1 : radius * 3;
  for (let pass = 0; pass < 3; pass++) {
    if (ortho) {
      // largest zoom that fits (log search)
      let small = 1e-3;
      let large = 1e4;
      for (let i = 0; i < 40; i++) {
        const mid = Math.sqrt(small * large);
        if (fits(mid)) small = mid;
        else large = mid;
      }
      scale = small;
    } else {
      // smallest distance that fits
      let near = Math.max(0.5, radius * 0.3);
      let far = radius * 60;
      for (let i = 0; i < 32; i++) {
        const mid = (near + far) / 2;
        if (fits(mid)) far = mid;
        else near = mid;
      }
      scale = far;
    }
    const { min, max } = extent(scale);
    const depth = target.clone().project(probe).z;
    const from = new THREE.Vector3((min.x + max.x) / 2, (min.y + max.y) / 2, depth).unproject(probe);
    const to = new THREE.Vector3((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, depth).unproject(probe);
    target.add(from.sub(to));
  }
  place(scale);
  return { position: probe.position.clone(), target, zoom: ortho ? scale : undefined };
}
