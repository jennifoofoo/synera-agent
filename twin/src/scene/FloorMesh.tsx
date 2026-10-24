import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import type { FloorModel, BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";
import { buildFloorGeometry, withCutaway } from "./geometry";

interface Props {
  floor: FloorModel;
  model: BuildingModel;
  y: number;
  ghost: boolean;
  visible: boolean;
}

/** Shared uniforms for the dollhouse cutaway: direction from the building centre to the camera, and on/off. */
export const cutawayUniforms = { uCamDir: { value: new THREE.Vector2(0, 1) }, uCut: { value: 1 }, uFlat: { value: 0 } };

export function FloorMesh({ floor, model, y, ghost, visible }: Props) {
  const select = useTwin((s) => s.select);
  const built = useMemo(() => {
    const started = performance.now();
    const geometry = buildFloorGeometry(floor);
    buildTimes.set(floor.id, performance.now() - started);
    return geometry;
  }, [floor]);
  useEffect(() => () => {
    built.solid.disposeBoundsTree?.();
    built.solid.dispose();
    built.edges.dispose();
  }, [built]);

  const materials = useMemo(() => {
    const solid = withCutaway(
      new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.92, metalness: 0.0, flatShading: false }),
      cutawayUniforms,
    );
    const edges = withCutaway(new THREE.LineBasicMaterial({ color: COLOURS.edge, transparent: true, opacity: 0.85 }), cutawayUniforms);
    const ghostSolid = new THREE.MeshBasicMaterial({
      color: COLOURS.ghost,
      transparent: true,
      opacity: 0.1,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const ghostEdges = new THREE.LineBasicMaterial({ color: COLOURS.edgeGhost, transparent: true, opacity: 0.35, depthWrite: false });
    return { solid, edges, ghostSolid, ghostEdges };
  }, []);
  useEffect(() => () => Object.values(materials).forEach((m) => m.dispose()), [materials]);

  const group = useRef<THREE.Group>(null);
  useFrame(() => {
    if (group.current) group.current.position.y = y; // no React re-render for the exploded animation
  });

  const onClick = (event: ThreeEvent<MouseEvent>) => {
    if (ghost || !event.face) return;
    event.stopPropagation();
    const index = built.spaceIndexOf(event.face.a);
    const space = floor.spaces[index];
    if (!space) return;
    const native = event.nativeEvent;
    const screen: [number, number] = [native.clientX, native.clientY];
    const point: [number, number] = [Math.round(event.point.x * 100) / 100, Math.round(-event.point.z * 100) / 100];
    if (native.shiftKey) {
      select({ kind: "point", id: `${space.id}@${point.join(",")}`, floor_id: floor.id, space_id: space.id, point }, screen);
      return;
    }
    const connector = model.connectorBySpace.get(space.id);
    if (connector) {
      select({ kind: "connector", id: connector.id, floor_id: floor.id, space_id: space.id, point }, screen);
      return;
    }
    select({ kind: "space", id: space.id, floor_id: floor.id, point }, screen);
  };

  return (
    <group ref={group} position-y={y} visible={visible} name={`floor:${floor.id}`}>
      <mesh
        geometry={built.solid}
        material={ghost ? materials.ghostSolid : materials.solid}
        onClick={ghost ? undefined : onClick}
        renderOrder={ghost ? 10 : 0}
        layers-mask={ghost ? 2 : 1}
        userData={{ floorId: floor.id, ghost }}
        frustumCulled
      />
      <lineSegments geometry={built.edges} material={ghost ? materials.ghostEdges : materials.edges} renderOrder={ghost ? 11 : 1} layers-mask={ghost ? 2 : 1} />
    </group>
  );
}

export const buildTimes = new Map<string, number>();
