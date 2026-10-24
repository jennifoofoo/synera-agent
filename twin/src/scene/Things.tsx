import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { ThreeEvent } from "@react-three/fiber";
import type { Asset, BuildingState } from "../api/types";
import type { FloorModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";

const unitBox = new THREE.BoxGeometry(1, 1, 1);
unitBox.translate(0, 0.5, 0);
const temp = new THREE.Object3D();
const colour = new THREE.Color();

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
  /** 2D plan: only machines and equipment, in a quiet grey (a street map shows no furniture). */
  flat?: boolean;
}

/** All things of one floor as one instanced mesh (true size from the footprint) plus an inverted-hull outline. */
export function Things({ floor, y, state, limit, flat = false }: Props) {
  const select = useTwin((s) => s.select);
  const mesh = useRef<THREE.InstancedMesh>(null);
  const outline = useRef<THREE.InstancedMesh>(null);
  const removed = useMemo(() => new Set(state?.removed_assets ?? []), [state?.removed_assets]);
  const moved = state?.moved_assets ?? {};
  const assets = useMemo(
    () =>
      floor.assets
        .filter((asset) => !removed.has(asset.id) && (!flat || asset.category === "machine" || asset.category === "equipment"))
        .slice(0, limit),
    [floor, removed, limit, flat],
  );
  const count = assets.length;

  useEffect(() => {
    const instanced = mesh.current;
    const hull = outline.current;
    if (!instanced || !hull) return;
    assets.forEach((asset, index) => {
      const edit = moved[asset.id];
      const position = edit?.position ?? asset.position;
      const rotation = edit?.rotation_deg ?? asset.footprint?.rotation_deg ?? 0;
      const [w, h, d] = assetSize(asset);
      temp.position.set(position[0], 0, -position[1]);
      temp.rotation.set(0, THREE.MathUtils.degToRad(rotation), 0);
      temp.scale.set(w, h, d);
      temp.updateMatrix();
      instanced.setMatrixAt(index, temp.matrix);
      temp.scale.set(w + 0.06, h + 0.03, d + 0.06);
      temp.updateMatrix();
      hull.setMatrixAt(index, temp.matrix);
      instanced.setColorAt(index, colour.set(flat ? "#d3d0c9" : assetColour(asset)));
    });
    instanced.count = count;
    hull.count = count;
    instanced.instanceMatrix.needsUpdate = true;
    hull.instanceMatrix.needsUpdate = true;
    if (instanced.instanceColor) instanced.instanceColor.needsUpdate = true;
    instanced.computeBoundingSphere();
    hull.computeBoundingSphere();
  }, [assets, moved, count, flat]);

  const onClick = (event: ThreeEvent<MouseEvent>) => {
    if (event.instanceId === undefined) return;
    event.stopPropagation();
    const asset = assets[event.instanceId];
    if (!asset) return;
    select({ kind: "asset", id: asset.id, floor_id: floor.id, space_id: asset.space_id }, [event.nativeEvent.clientX, event.nativeEvent.clientY]);
  };

  if (!count) return null;
  return (
    <group position-y={y}>
      <instancedMesh ref={mesh} args={[unitBox, undefined, count]} onClick={onClick} frustumCulled={false}>
        <meshStandardMaterial roughness={0.8} metalness={0.05} />
      </instancedMesh>
      <instancedMesh ref={outline} args={[unitBox, undefined, count]} frustumCulled={false} raycast={() => null}>
        <meshBasicMaterial color={flat ? "#9a968d" : COLOURS.edge} side={THREE.BackSide} transparent opacity={0.9} />
      </instancedMesh>
    </group>
  );
}
