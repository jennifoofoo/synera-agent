// Zoom tiers of the 2D map, like a street map: what is shown depends only on the scale (metres per screen
// pixel), so the same zoom always shows the same things.
//   far:  zone names (the largest rooms) and points of interest (lifts, stairs, toilets, entrances)
//   mid:  every room name that fits inside its room
//   near: also the machines and equipment

import { useState } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";

export type MapTier = "far" | "mid" | "near";

/** Scale buckets are half octaves. A bucket's layout is computed for its coarsest scale (its upper bound), so
 * nothing overlaps anywhere inside the bucket and the set only changes when a bucket boundary is crossed. */
const BUCKETS_PER_OCTAVE = 2;
/** Tier boundaries in metres per pixel: below NEAR a 2 m machine is at least ~22 px wide. */
const NEAR_MAX = 0.09;
const MID_MAX = 0.3;

export function tierOf(metresPerPixel: number): MapTier {
  return metresPerPixel <= NEAR_MAX ? "near" : metresPerPixel <= MID_MAX ? "mid" : "far";
}

const centre = new THREE.Vector3();

function metresPerPixelOf(camera: THREE.Camera, width: number, height: number, focus: THREE.Vector3): number {
  if ((camera as THREE.OrthographicCamera).isOrthographicCamera) {
    const ortho = camera as THREE.OrthographicCamera;
    return (ortho.right - ortho.left) / ortho.zoom / Math.max(1, width);
  }
  const perspective = camera as THREE.PerspectiveCamera;
  const distance = camera.position.distanceTo(focus);
  return (2 * distance * Math.tan(THREE.MathUtils.degToRad(perspective.fov / 2))) / Math.max(1, height);
}

/** The current scale bucket: `scale` is the bucket's coarsest metres-per-pixel (use it for collision layout),
 * `tier` the map tier of that scale. Re-renders only when the bucket changes. */
export function useMapZoom(focusX: number, focusY: number, focusZ: number): { scale: number; tier: MapTier } {
  const [scale, setScale] = useState(1);
  useFrame(({ camera, size }) => {
    centre.set(focusX, focusY, focusZ);
    const mpp = metresPerPixelOf(camera, size.width, size.height, centre);
    const bucket = Math.pow(2, Math.ceil(Math.log2(Math.max(1e-3, mpp)) * BUCKETS_PER_OCTAVE - 1e-6) / BUCKETS_PER_OCTAVE);
    if (bucket !== scale) setScale(bucket);
  });
  return { scale, tier: tierOf(scale) };
}
