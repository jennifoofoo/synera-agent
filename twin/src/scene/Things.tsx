import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { ThreeEvent } from "@react-three/fiber";
import type { Asset, BuildingState } from "../api/types";
import type { FloorModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";
import { useLandmarks } from "./landmarks";
import { MIN_SHAPE_PX, useMapZoom } from "./mapZoom";

const unitBox = new THREE.BoxGeometry(1, 1, 1);
unitBox.translate(0, 0.5, 0);
const temp = new THREE.Object3D();
const colour = new THREE.Color();

/** 2D plan shapes: one quiet grey just darker than the floor; fainter while a route is shown, landmarks stronger. */
const PLAN_THING = "#c3c0b9";
const PLAN_THING_FAINT = "#cac8c2";
const PLAN_LANDMARK = "#8f8a80";
/** 2D: things are thin slabs, so they never cover the route, pins or labels drawn above the floor. */
const PLAN_HEIGHT = 0.06;

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

/** All things of one floor as one instanced mesh (true size from the footprint) plus an inverted-hull outline (3D). */
export function Things({ floor, y, state, limit, flat = false }: Props) {
  const select = useTwin((s) => s.select);
  const mesh = useRef<THREE.InstancedMesh>(null);
  const outline = useRef<THREE.InstancedMesh>(null);
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
  const capacity = all.length;
  const count = assets.length;

  useEffect(() => {
    const instanced = mesh.current;
    const hull = outline.current;
    if (!instanced || !hull) return;
    assets.forEach((asset, index) => {
      const edit = moved[asset.id];
      const position = edit?.position ?? asset.position;
      const rotation = edit?.rotation_deg ?? asset.footprint?.rotation_deg ?? 0;
      const [w, fullHeight, d] = assetSize(asset);
      const h = flat ? PLAN_HEIGHT : fullHeight;
      temp.position.set(position[0], 0, -position[1]);
      temp.rotation.set(0, THREE.MathUtils.degToRad(rotation), 0);
      temp.scale.set(w, h, d);
      temp.updateMatrix();
      instanced.setMatrixAt(index, temp.matrix);
      temp.scale.set(w + 0.06, h + 0.03, d + 0.06);
      temp.updateMatrix();
      hull.setMatrixAt(index, temp.matrix);
      const planColour = landmarks.has(asset.id) ? PLAN_LANDMARK : routeShown ? PLAN_THING_FAINT : PLAN_THING;
      instanced.setColorAt(index, colour.set(flat ? planColour : assetColour(asset)));
    });
    instanced.count = count;
    hull.count = flat ? 0 : count; // 2D: no edge, the fill alone
    instanced.instanceMatrix.needsUpdate = true;
    hull.instanceMatrix.needsUpdate = true;
    if (instanced.instanceColor) instanced.instanceColor.needsUpdate = true;
    instanced.computeBoundingSphere();
    hull.computeBoundingSphere();
  }, [assets, moved, count, flat, landmarks, routeShown]);

  const onClick = (event: ThreeEvent<MouseEvent>) => {
    // 2D: a tap on a shape only selects the thing when zoomed in; farther out it goes to the room below.
    // Furniture never takes the tap in 2D (a tap on a desk means its room); machines and equipment do from near on.
    if (event.instanceId === undefined || (flat && tier !== "near")) return;
    const asset = assets[event.instanceId];
    if (!asset || (flat && asset.category !== "machine" && asset.category !== "equipment")) return;
    event.stopPropagation();
    select({ kind: "asset", id: asset.id, floor_id: floor.id, space_id: asset.space_id }, [event.nativeEvent.clientX, event.nativeEvent.clientY]);
  };

  if (!capacity) return null;
  return (
    <group position-y={y}>
      {/* key: the material type changes between 2D (unlit, exact plan colour) and 3D (lit) */}
      <instancedMesh key={flat ? "plan" : "solid"} ref={mesh} args={[unitBox, undefined, capacity]} onClick={onClick} frustumCulled={false}>
        {flat ? <meshBasicMaterial /> : <meshStandardMaterial roughness={0.8} metalness={0.05} />}
      </instancedMesh>
      <instancedMesh ref={outline} args={[unitBox, undefined, capacity]} frustumCulled={false} raycast={() => null}>
        <meshBasicMaterial color={COLOURS.edge} side={THREE.BackSide} transparent opacity={0.9} />
      </instancedMesh>
    </group>
  );
}
