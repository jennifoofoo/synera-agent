import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { useThree } from "@react-three/fiber";
import { AccumulativeShadows, Environment, Lightformer, RandomizedLight } from "@react-three/drei";
import { boundsOf, type BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { SLAB_THICKNESS } from "./geometry";

/** The plinth: a thin slab under the ground floor, this much larger than the building on each side (m). */
export const PLINTH_MARGIN_M = 1.5;
export const PLINTH_THICKNESS_M = 0.35;
/** Wait this long after the scene changed before baking the soft shadow (the focused floor rises for 600 ms). */
const BAKE_DELAY_MS = 750;
/** The shadow catcher sits this far above the floor slab (no z-fighting, below furniture tops and the route). */
const SHADOW_LIFT_M = 0.02;

/** Top of the plinth: the underside of the lowest floor slab, so the building stands on it. */
export function plinthTop(model: BuildingModel): number {
  return Math.min(...model.floors.map((floor) => floor.elevation_m)) - SLAB_THICKNESS;
}

type Pt = readonly [number, number];

/** Convex hull (monotone chain), counter-clockwise. */
function hullOf(points: Pt[]): Pt[] {
  const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (sorted.length < 3) return sorted;
  const cross = (o: Pt, a: Pt, b: Pt) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: Pt[] = [];
  for (const p of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: Pt[] = [];
  for (const p of [...sorted].reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  return [...lower.slice(0, -1), ...upper.slice(0, -1)];
}

/** The plinth's rectangle in plan coordinates: the smallest rectangle around the indoor spaces of all floors (turned
 * with the building when it is not axis-aligned), plus the margin. Outdoor areas (yards, site) are left out. */
function plinthRect(model: BuildingModel) {
  const spaces = model.building.spaces;
  const indoor = spaces.filter((space) => space.type !== "outdoor");
  const points: Pt[] = (indoor.length ? indoor : spaces).flatMap((space) => space.polygon as Pt[]);
  const hull = hullOf(points);
  const fit = (angle: number) => {
    const c = Math.cos(angle);
    const s = Math.sin(angle);
    let u0 = Infinity, u1 = -Infinity, v0 = Infinity, v1 = -Infinity;
    for (const [x, y] of hull) {
      const u = x * c + y * s;
      const v = -x * s + y * c;
      u0 = Math.min(u0, u); u1 = Math.max(u1, u); v0 = Math.min(v0, v); v1 = Math.max(v1, v);
    }
    const um = (u0 + u1) / 2;
    const vm = (v0 + v1) / 2;
    return { angle, w: u1 - u0, d: v1 - v0, cx: um * c - vm * s, cy: um * s + vm * c };
  };
  // Axis-aligned unless a turned rectangle is clearly smaller (a rectangular building keeps a square-on base).
  let best = fit(0);
  for (let i = 0; i < hull.length; i++) {
    const [ax, ay] = hull[i];
    const [bx, by] = hull[(i + 1) % hull.length];
    const candidate = fit(Math.atan2(by - ay, bx - ax));
    if (candidate.w * candidate.d < best.w * best.d * 0.97) best = candidate;
  }
  return { ...best, w: best.w + 2 * PLINTH_MARGIN_M, d: best.d + 2 * PLINTH_MARGIN_M, size: Math.max(best.w, best.d, 1) };
}

/** Spread of the plinth's shadow on the backdrop (m): how far the blur reaches past its edge. */
const PLINTH_SHADOW_M = 1.6;

/** The plinth follows the ground floor's footprint (indoor spaces, every shape, not a bounding rectangle), this
 * much wider on each side (m). */
const FOOTPRINT_MARGIN_M = 0.9;

interface Footprint {
  /** Alpha mask of the footprint plus margin (white inside), and its blurred copy for the shadow. */
  mask: THREE.CanvasTexture;
  shadow: THREE.CanvasTexture;
  /** Size and centre of the textures' plane in plan metres. */
  w: number;
  d: number;
  cx: number;
  cy: number;
}

/** The ground floor's footprint drawn on a 2D canvas: every indoor polygon filled and stroked with a round line
 * twice the margin wide, which is exactly the union of the rooms grown by the margin. Drawn once, no render pass. */
function footprintTextures(model: BuildingModel): Footprint | null {
  const ground = model.floors.find((floor) => floor.spaces.some((space) => space.type !== "outdoor"));
  const polygons = (ground?.spaces ?? []).filter((space) => space.type !== "outdoor").map((space) => space.polygon as Pt[]);
  if (!polygons.length) return null;
  const b = boundsOf(polygons.flat() as [number, number][]);
  const pad = FOOTPRINT_MARGIN_M + PLINTH_SHADOW_M * 1.5;
  const w = b.maxX - b.minX + 2 * pad;
  const d = b.maxY - b.minY + 2 * pad;
  const ppm = Math.min(24, 2048 / Math.max(w, d)); // canvas pixels per metre
  const draw = (blur: number) => {
    const canvas = document.createElement("canvas");
    canvas.width = Math.ceil(w * ppm);
    canvas.height = Math.ceil(d * ppm);
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    const far = blur ? canvas.width + 100 : 0;
    if (blur) {
      ctx.shadowColor = "#fff";
      ctx.shadowBlur = blur * ppm;
      ctx.shadowOffsetX = far; // draw the shape off canvas, keep only its blurred shadow
    }
    ctx.fillStyle = "#fff";
    ctx.strokeStyle = "#fff";
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.lineWidth = 2 * FOOTPRINT_MARGIN_M * ppm;
    ctx.beginPath();
    for (const polygon of polygons) {
      polygon.forEach(([x, y], i) => {
        const px = (x - b.minX + pad) * ppm - far;
        const py = (b.maxY + pad - y) * ppm; // canvas rows run south; the texture's top is plan north
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.closePath();
    }
    ctx.fill("nonzero");
    ctx.stroke();
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.NoColorSpace;
    return texture;
  };
  return { mask: draw(0), shadow: draw(PLINTH_SHADOW_M * 0.9), w, d, cx: (b.minX + b.maxX) / 2, cy: (b.minY + b.maxY) / 2 };
}

/** The base the model stands on, like an architectural model on a table (3D only): the ground floor's own outline
 * with a small margin (not a rectangle around every floor, which left a large empty slab beside an L-shaped or
 * offset building), with its own soft shadow on the backdrop. */
export function Plinth({ model }: { model: BuildingModel }) {
  const footprint = useMemo(() => footprintTextures(model), [model]);
  useEffect(
    () => () => {
      footprint?.mask.dispose();
      footprint?.shadow.dispose();
    },
    [footprint],
  );
  if (!footprint) return null;
  const { w, d, cx, cy, mask, shadow } = footprint;
  const top = plinthTop(model);
  return (
    <group position={[cx, top, -cy]}>
      <mesh position-y={-0.004} rotation-x={-Math.PI / 2} raycast={() => null} receiveShadow>
        <planeGeometry args={[w, d]} />
        <meshStandardMaterial color={COLOURS.plinth} roughness={0.9} metalness={0} alphaMap={mask} alphaTest={0.5} />
      </mesh>
      <mesh position-y={-PLINTH_THICKNESS_M - 0.02} rotation-x={-Math.PI / 2} raycast={() => null} renderOrder={-1}>
        <planeGeometry args={[w, d]} />
        <meshBasicMaterial color={COLOURS.shadowTint} alphaMap={shadow} transparent opacity={0.28} depthWrite={false} fog={false} />
      </mesh>
    </group>
  );
}

const softwareCache = new WeakMap<object, boolean>();

/** Whether WebGL runs on a software rasterizer (SwiftShader, llvmpipe: headless browsers, VMs, blocklisted GPUs).
 * There a frame costs seconds, so the studio keeps to the cheap lights and skips the baked shadows. */
export function useSoftwareGl(): boolean {
  const gl = useThree((s) => s.gl);
  let software = softwareCache.get(gl);
  if (software === undefined) {
    const context = gl.getContext();
    const info = context.getExtension("WEBGL_debug_renderer_info");
    const renderer = info ? String(context.getParameter(info.UNMASKED_RENDERER_WEBGL)) : "";
    software = /swiftshader|llvmpipe|software/i.test(renderer);
    softwareCache.set(gl, software);
  }
  return software;
}

/** Studio light for the planner (3D): a large softbox above the front, a rim light behind, a weak fill, baked once
 * into an environment map. White surfaces stay white; the shape comes from the gradients, not from dark faces. */
export function StudioLight() {
  return (
    <Environment resolution={256} frames={1} environmentIntensity={1.45}>
      {/* an even grey dome: every face gets some light, so no wall turns dark */}
      <color attach="background" args={[COLOURS.studioDome]} />
      <Lightformer form="rect" intensity={1.6} color={COLOURS.studioKey} scale={[16, 10, 1]} position={[-3, 8, 7]} target={[0, 0, 0]} />
      <Lightformer form="rect" intensity={0.45} color={COLOURS.studioKey} scale={[40, 40, 1]} position={[0, 12, 0]} rotation-x={Math.PI / 2} />
      <Lightformer form="rect" intensity={1.0} color={COLOURS.studioRim} scale={[18, 4, 1]} position={[-5, 4, -9]} target={[0, 0, 0]} />
      <Lightformer form="rect" intensity={0.6} color={COLOURS.studioFill} scale={[12, 6, 1]} position={[9, 2, 1]} target={[0, 0, 0]} />
    </Environment>
  );
}

interface ShadowProps {
  model: BuildingModel;
  /** Height of the floor the shadow lies on (the focused floor's slab top). */
  y: number;
  /** Changes whenever what casts the shadow changes (floor, floor mode, route floors, things): re-bakes. */
  bakeKey: string;
}

/** Real soft shadows (planner, 3D): a shadow-catcher plane just above the focused floor, accumulated once per change
 * from 8 randomised lights over 60 frames, then free (no per-frame cost). Walls and machines throw soft shadows into
 * the rooms like a clay model under a softbox. The phone profile does not mount this. */
export const StudioShadows = memo(function StudioShadows({ model, y, bakeKey }: ShadowProps) {
  const { w, d, cx, cy, size, angle } = useMemo(() => plinthRect(model), [model]);
  // Mount the accumulation only once the scene has settled, so nothing mounts or moves while it bakes.
  const [settledKey, setSettledKey] = useState<string | null>(null);
  useEffect(() => {
    setSettledKey(null);
    const timer = setTimeout(() => setSettledKey(bakeKey), BAKE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [bakeKey]);
  if (!settledKey) return null;
  return (
    <AccumulativeShadows
      key={settledKey}
      temporal
      frames={60}
      alphaTest={0.85}
      opacity={0.8}
      // the plane is square; stretch it to the plinth once mounted (the component is memoised, no re-render)
      ref={(api) => api?.getMesh().scale.set(w, d, 1)}
      position={[cx, y + SHADOW_LIFT_M, -cy]}
      rotation-y={angle}
      color={COLOURS.shadowTint}
      colorBlend={1.4}
      resolution={1024}
    >
      <BuildingLight size={size} centre={[cx, y, -cy]} />
    </AccumulativeShadows>
  );
});

/** RandomizedLight aims its lights at the world origin; point them at the building centre instead. */
function BuildingLight({ size, centre }: { size: number; centre: [number, number, number] }) {
  const wrap = useRef<THREE.Group>(null);
  const [x, y, z] = centre;
  useLayoutEffect(() => {
    wrap.current?.traverse((child) => {
      if (!(child instanceof THREE.DirectionalLight)) return;
      child.target.position.set(x, y, z);
      child.target.updateMatrixWorld();
    });
  }, [x, y, z]);
  return (
    <group ref={wrap}>
      <RandomizedLight
        amount={8}
        radius={size * 0.3}
        ambient={0.3}
        // bright enough that unshadowed floor stays fully clear (lights low on the dome hit it at a slant)
        intensity={Math.PI * 1.35}
        // from behind on the left and high up: shadows fall toward the camera, where they are seen
        position={[-size * 0.45, size * 1.0, -size * 0.15]}
        size={size * 0.75 + PLINTH_MARGIN_M + 2}
        far={size * 4}
        mapSize={1024}
        bias={0.002}
      />
    </group>
  );
}
