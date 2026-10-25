import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import type { ThreeEvent } from "@react-three/fiber";
import type { Asset, BuildingState } from "../api/types";
import type { FloorModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";
import { useLandmarks } from "./landmarks";
import { MIN_SHAPE_PX, useMapZoom } from "./mapZoom";

// Two kinds of things, like an architectural model: furniture is a flat footprint on the floor (it gives scale and
// reads as "a desk here", nothing more), machines and the landmarks of the directions are bodies (rounded, a darker
// top, a soft shadow) because they are what people steer by. Equipment (printers, extinguishers) is a footprint too:
// its icon on the map is the recognisable part.

/** Bodies: a rounded box standing on the floor, vertex colour darkens the top face a step (instance colour on top). */
const bodyBox = new RoundedBoxGeometry(1, 1, 1, 3, 0.06);
bodyBox.translate(0, 0.5, 0);
{
  const normals = bodyBox.getAttribute("normal");
  const colours = new Float32Array(normals.count * 3);
  for (let i = 0; i < normals.count; i++) {
    const f = normals.getY(i) > 0.9 ? 0.9 : 1;
    colours[i * 3] = f;
    colours[i * 3 + 1] = f;
    colours[i * 3 + 2] = f;
  }
  bodyBox.setAttribute("color", new THREE.BufferAttribute(colours, 3));
}
/** Footprints: a flat rounded slab (also the 2D plan shape of every thing). */
const footprintBox = new RoundedBoxGeometry(1, 1, 1, 2, 0.12);
footprintBox.translate(0, 0.5, 0);
/** A soft shadow blob under every body: a plane with a radial alpha texture. */
const shadowPlane = new THREE.PlaneGeometry(1, 1);
shadowPlane.rotateX(-Math.PI / 2);
function shadowTexture(): THREE.Texture | null {
  if (typeof document === "undefined") return null;
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const context = canvas.getContext("2d");
  if (!context) return null;
  const gradient = context.createRadialGradient(size / 2, size / 2, size * 0.18, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, "rgba(0,0,0,1)");
  gradient.addColorStop(1, "rgba(0,0,0,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.NoColorSpace;
  return texture;
}
const shadowMap = shadowTexture();

const temp = new THREE.Object3D();
const colour = new THREE.Color();

/** 2D plan shapes: one quiet grey just darker than the floor; fainter while a route is shown, landmarks stronger. */
const PLAN_THING = COLOURS.planThing;
const PLAN_THING_FAINT = COLOURS.planThingFaint;
const PLAN_LANDMARK = COLOURS.planLandmark;
/** 2D: things are thin slabs, so they never cover the route, pins or labels drawn above the floor. */
const PLAN_HEIGHT = 0.06;
/** 3D: furniture footprints are this high (m), bodies keep their category height. */
const FOOTPRINT_HEIGHT = 0.08;
const SHADOW_PAD_M = 0.45;
const SHADOW_OPACITY = 0.1;

export function assetSize(asset: Asset): [number, number, number] {
  const category = asset.category ?? "furniture";
  const height = category === "machine" ? 1.9 : category === "equipment" ? 1.3 : category === "fixture" ? 0.9 : 0.75;
  const width = asset.footprint?.width_m ?? (category === "machine" ? 2 : 0.8);
  const depth = asset.footprint?.depth_m ?? (category === "machine" ? 1.5 : 0.8);
  return [Math.max(0.25, width), height, Math.max(0.25, depth)];
}

export function assetColour(asset: Asset): string {
  return asset.category === "machine" ? COLOURS.machine : COLOURS.thing;
}

interface Props {
  floor: FloorModel;
  y: number;
  state: BuildingState | null;
  limit: number;
  /** 2D plan: "show everything, quietly" (see mapZoom.ts): every footprint big enough on screen, flat and grey. */
  flat?: boolean;
}

/** All things of one floor: machines and landmarks as rounded bodies with a soft shadow, everything else as a flat
 * footprint; one instanced mesh per kind (true size from the footprint). */
export function Things({ floor, y, state, limit, flat = false }: Props) {
  const select = useTwin((s) => s.select);
  const bodies = useRef<THREE.InstancedMesh>(null);
  const shadows = useRef<THREE.InstancedMesh>(null);
  const footprints = useRef<THREE.InstancedMesh>(null);
  const removed = useMemo(() => new Set(state?.removed_assets ?? []), [state?.removed_assets]);
  const moved = state?.moved_assets ?? {};
  const all = useMemo(() => floor.assets.filter((asset) => !removed.has(asset.id)).slice(0, limit), [floor, removed, limit]);
  const { scale, tier } = useMapZoom(floor.bounds.cx, y, -floor.bounds.cy);
  const landmarks = useLandmarks();
  // While a route is shown or walked the task is the route: shapes step back, its landmarks step forward.
  const routeShown = useTwin((s) => !!s.state?.route?.ok || !!s.state?.guide?.active);
  // 2D: a shape is drawn once its larger side covers MIN_SHAPE_PX on screen (per scale bucket, so cheap); far away
  // the machines form the pattern of the building and chairs vanish on their own. Landmarks always.
  const assets = useMemo(
    () =>
      flat
        ? all.filter((asset) => {
            if (landmarks.has(asset.id)) return true;
            const [w, , d] = assetSize(asset);
            return Math.max(w, d) / scale >= MIN_SHAPE_PX;
          })
        : all,
    [all, flat, scale, landmarks],
  );
  // 3D: bodies are machines and the landmarks of the directions; the rest lies flat. 2D: everything is a flat slab.
  const split = useMemo(() => {
    const body: Asset[] = [];
    const slab: Asset[] = [];
    for (const asset of assets) (!flat && (asset.category === "machine" || landmarks.has(asset.id)) ? body : slab).push(asset);
    return { body, slab };
  }, [assets, flat, landmarks]);
  const capacity = all.length;

  useEffect(() => {
    const body = bodies.current;
    const shadow = shadows.current;
    const slab = footprints.current;
    if (!slab) return;
    const place = (asset: Asset, h: number, pad = 0, lift = 0) => {
      const edit = moved[asset.id];
      const position = edit?.position ?? asset.position;
      const rotation = edit?.rotation_deg ?? asset.footprint?.rotation_deg ?? 0;
      const [w, , d] = assetSize(asset);
      temp.position.set(position[0], lift, -position[1]);
      temp.rotation.set(0, THREE.MathUtils.degToRad(rotation), 0);
      temp.scale.set(w + pad, h, d + pad);
      temp.updateMatrix();
    };
    const planColour = (asset: Asset) => (landmarks.has(asset.id) ? PLAN_LANDMARK : routeShown ? PLAN_THING_FAINT : PLAN_THING);
    split.slab.forEach((asset, index) => {
      place(asset, flat ? PLAN_HEIGHT : FOOTPRINT_HEIGHT);
      slab.setMatrixAt(index, temp.matrix);
      slab.setColorAt(index, colour.set(flat ? planColour(asset) : COLOURS.footprint));
    });
    slab.count = split.slab.length;
    slab.instanceMatrix.needsUpdate = true;
    if (slab.instanceColor) slab.instanceColor.needsUpdate = true;
    slab.computeBoundingSphere();
    if (body && shadow) {
      split.body.forEach((asset, index) => {
        const [, fullHeight] = assetSize(asset);
        place(asset, fullHeight);
        body.setMatrixAt(index, temp.matrix);
        body.setColorAt(index, colour.set(assetColour(asset)));
        place(asset, 1, SHADOW_PAD_M, 0.012);
        shadow.setMatrixAt(index, temp.matrix);
      });
      body.count = split.body.length;
      shadow.count = split.body.length;
      body.instanceMatrix.needsUpdate = true;
      shadow.instanceMatrix.needsUpdate = true;
      if (body.instanceColor) body.instanceColor.needsUpdate = true;
      body.computeBoundingSphere();
      shadow.computeBoundingSphere();
    }
  }, [split, moved, flat, landmarks, routeShown]);

  const onClick = (list: Asset[]) => (event: ThreeEvent<MouseEvent>) => {
    // 2D: a tap on a shape only selects the thing when zoomed in; farther out it goes to the room below.
    // Furniture never takes the tap in 2D (a tap on a desk means its room); machines and equipment do from near on.
    if (event.instanceId === undefined || (flat && tier !== "near")) return;
    const asset = list[event.instanceId];
    if (!asset || (flat && asset.category !== "machine" && asset.category !== "equipment")) return;
    event.stopPropagation();
    select({ kind: "asset", id: asset.id, floor_id: floor.id, space_id: asset.space_id }, [event.nativeEvent.clientX, event.nativeEvent.clientY]);
  };

  if (!capacity) return null;
  return (
    <group position-y={y}>
      {/* key: the material type changes between 2D (unlit, exact plan colour) and 3D (lit) */}
      <instancedMesh key={flat ? "plan" : "solid"} ref={footprints} args={[footprintBox, undefined, capacity]} onClick={onClick(split.slab)} frustumCulled={false}>
        {flat ? <meshBasicMaterial /> : <meshStandardMaterial roughness={0.95} metalness={0} />}
      </instancedMesh>
      {!flat && (
        <>
          <instancedMesh ref={shadows} args={[shadowPlane, undefined, capacity]} frustumCulled={false} raycast={() => null} renderOrder={1}>
            <meshBasicMaterial color={COLOURS.shadow} transparent opacity={SHADOW_OPACITY} depthWrite={false} alphaMap={shadowMap ?? undefined} />
          </instancedMesh>
          <instancedMesh ref={bodies} args={[bodyBox, undefined, capacity]} onClick={onClick(split.body)} frustumCulled={false}>
            <meshStandardMaterial roughness={0.7} metalness={0.05} vertexColors />
          </instancedMesh>
        </>
      )}
    </group>
  );
}
