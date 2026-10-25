// Zoom tiers of the 2D map, like a street map: what is shown depends only on the scale (metres per screen
// pixel), so the same zoom always shows the same things, on the phone and on the laptop alike.
//
// The rule: "show everything, quietly".
// 1. Shapes by on-screen size, not by category: every thing's footprint is drawn once its larger side covers
//    MIN_SHAPE_PX on screen, at every tier. Far away the machines and racks form the pattern of the building,
//    chairs vanish on their own because they are too small. (scene/Things.tsx; cheap: filtered per scale bucket.)
// 2. Shapes are always quiet: one grey just darker than the floor, no edge; never competing with route, pins, labels.
// 3. Text and symbols by tier (spec: docs/specs/semantic-zoom.md, "overview first, zoom and filter, then details"):
//   area: the whole floor is small on screen: areas instead of single names (adjacent rooms of one kind merged:
//         "Production", "Offices", "Social", scene/areas.ts) and the points of interest (entrances, lifts, stairs,
//         toilets). Only on floors large enough to have such a view; small floors skip it.
//   far:  zone names (the largest rooms) and points of interest
//   mid:  every room name that fits inside its room, and the amenity symbols (coffee, printer, first aid /
//         defibrillator / eyewash in safety green, fire extinguishers in safety red, below the room names)
//   near: also the names of machines (things become tappable), a second line under the room name ("Kitchen ·
//         24 m²") and the clear width of wide doors ("1.4 m")
//   Tapping a room (details on demand) lists its equipment on the room card (ui/Card.tsx).
//   Elements entering a tier fade in (150-200 ms, none with prefers-reduced-motion; poiIcons.css).
// 4. The task highlights, it does not hide: with a route (or while guiding) the shapes get fainter, and the things
//    the directions name as landmarks get darker and carry their name at every tier (scene/landmarks.ts).
// 3D keeps its own look (every thing in true size and colour).

import { useState } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { frameSize } from "./markerLayout";
import { controlsRef } from "./FloorMesh";

export type MapTier = "area" | "far" | "mid" | "near";

/** Scale buckets are half octaves. A bucket's layout is computed for its coarsest scale (its upper bound), so
 * nothing overlaps anywhere inside the bucket and the set only changes when a bucket boundary is crossed. */
const BUCKETS_PER_OCTAVE = 2;
/** Tier boundaries in metres per pixel: below NEAR a 2 m machine is at least ~22 px wide. */
const NEAR_MAX = 0.09;
const MID_MAX = 0.3;
/** A thing's footprint is drawn in 2D once its larger side is at least this many screen pixels. */
export const MIN_SHAPE_PX = 3.5;
/** Overview: the floor's larger side covers at most this many screen pixels (a phone shows a whole factory like
 * this at its home view; a laptop after zooming out a little). Pixels, not a share of the screen, so the same scale
 * gives the same tier on every device. */
const AREA_MAX_PX = 480;
/** Hysteresis: a bucket is only left once the scale is this far (in half octaves) past its edge, so a slight zoom
 * back and forth at a boundary never flickers. */
const HYSTERESIS = 0.2;
const HELD_FACTOR = Math.pow(2, HYSTERESIS / BUCKETS_PER_OCTAVE);

/** The tier of a scale; `extentM` (the floor's larger side in metres) enables the outermost "area" tier. */
export function tierOf(metresPerPixel: number, extentM = 0): MapTier {
  if (metresPerPixel <= NEAR_MAX) return "near";
  if (extentM > 0 && extentM / metresPerPixel <= AREA_MAX_PX) return "area";
  return metresPerPixel <= MID_MAX ? "mid" : "far";
}

const centre = new THREE.Vector3();

/** Metres per screen pixel at the focus. In 3D from the zoom alone (the orbit distance, when there are controls), so
 * tilting, rotating or panning never changes the tier (label-rules.md: measured at the floor's centre, they did). */
export function metresPerPixelOf(camera: THREE.Camera, canvasWidth: number, canvasHeight: number, focus: THREE.Vector3): number {
  const [width, height] = frameSize(camera, canvasWidth, canvasHeight);
  if ((camera as THREE.OrthographicCamera).isOrthographicCamera) {
    const ortho = camera as THREE.OrthographicCamera;
    return (ortho.right - ortho.left) / ortho.zoom / Math.max(1, width);
  }
  const perspective = camera as THREE.PerspectiveCamera;
  const distance = controlsRef.current?.distance ?? camera.position.distanceTo(focus);
  return (2 * distance * Math.tan(THREE.MathUtils.degToRad(perspective.fov / 2))) / Math.max(1, height);
}

/** The current scale bucket: `scale` is the bucket's coarsest metres-per-pixel (use it for collision layout),
 * `tier` the map tier of that scale (`extentM`: see tierOf). Re-renders only when the bucket changes, and a bucket
 * is only left a little past its edge (HYSTERESIS). */
export function useMapZoom(focusX: number, focusY: number, focusZ: number, extentM = 0): { scale: number; tier: MapTier } {
  const [scale, setScale] = useState(1);
  useFrame(({ camera, size }) => {
    centre.set(focusX, focusY, focusZ);
    const mpp = metresPerPixelOf(camera, size.width, size.height, centre);
    const position = Math.log2(Math.max(1e-3, mpp)) * BUCKETS_PER_OCTAVE; // in half octaves
    const current = Math.round(Math.log2(scale) * BUCKETS_PER_OCTAVE); // the bucket covers (current - 1, current]
    if (position <= current + HYSTERESIS && position > current - 1 - HYSTERESIS) return;
    const bucket = Math.pow(2, Math.ceil(position - 1e-6) / BUCKETS_PER_OCTAVE);
    if (bucket !== scale) setScale(bucket);
  });
  // The layout scale is the coarsest the bucket can show while it is held (its edge plus the hysteresis), so labels
  // laid out for it never overlap anywhere inside it.
  return { scale: scale * HELD_FACTOR, tier: tierOf(scale, extentM) };
}
