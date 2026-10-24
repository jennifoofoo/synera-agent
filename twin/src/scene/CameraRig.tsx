import { useEffect, useRef } from "react";
import * as THREE from "three";
import { CameraControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import type CameraControlsImpl from "camera-controls";
import type { BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { cutawayUniforms } from "./FloorMesh";

interface Props {
  model: BuildingModel;
  floorY: (floorId: string) => number;
  floorTop: (floorId: string) => number;
  topY: number;
}

const HOME_AZIMUTH = -Math.PI / 4;
const HOME_POLAR = Math.PI / 3.6;

/** Smooth camera with limits: never below the floor, never away from the building, a sensible distance, and
 * fly-to for rooms, things, floors and points. Reduced motion: the camera jumps. */
export function CameraRig({ model, floorY, floorTop, topY }: Props) {
  const controls = useRef<CameraControlsImpl>(null);
  const request = useTwin((s) => s.camera);
  const reducedMotion = useTwin((s) => s.reducedMotion);
  const cutaway = useTwin((s) => s.cutaway);
  const floorMode = useTwin((s) => s.floorMode);
  const { bounds } = model;
  const size = bounds.size;
  const camera = useThree((s) => s.camera);

  // Limits follow the building.
  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    c.minDistance = Math.max(2, size * 0.04);
    c.maxDistance = size * 4;
    c.minPolarAngle = 0.08;
    c.maxPolarAngle = Math.PI / 2 - 0.12;
    c.smoothTime = 0.32;
    c.draggingSmoothTime = 0.08;
    c.dollyToCursor = true;
    c.infinityDolly = false;
    const margin = size * 0.6;
    c.setBoundary(new THREE.Box3(new THREE.Vector3(bounds.minX - margin, -1, -bounds.maxY - margin), new THREE.Vector3(bounds.maxX + margin, topY + size, -bounds.minY + margin)));
    c.boundaryFriction = 0.2;
  }, [bounds, size, topY]);

  // Requests from the store.
  useEffect(() => {
    const c = controls.current;
    if (!c || !request.nonce) return;
    const animate = !reducedMotion;
    const box = new THREE.Box3();
    if (request.kind === "home") {
      box.set(new THREE.Vector3(bounds.minX, 0, -bounds.maxY), new THREE.Vector3(bounds.maxX, topY, -bounds.minY));
      c.rotateTo(HOME_AZIMUTH, HOME_POLAR, animate);
      c.fitToBox(box, animate, { paddingTop: size * 0.05, paddingBottom: size * 0.05, paddingLeft: size * 0.05, paddingRight: size * 0.05 });
      return;
    }
    if (request.kind === "floor" && request.floorId) {
      const floor = model.floorById.get(request.floorId);
      if (!floor) return;
      const y = floorY(floor.id);
      box.set(new THREE.Vector3(floor.bounds.minX, y, -floor.bounds.maxY), new THREE.Vector3(floor.bounds.maxX, y + floor.height_m, -floor.bounds.minY));
      c.fitToBox(box, animate, { paddingTop: 2, paddingBottom: 2, paddingLeft: 2, paddingRight: 2 });
      return;
    }
    if (request.kind === "point" && request.point && request.floorId) {
      const y = floorY(request.floorId);
      const r = request.radius ?? 6;
      box.set(new THREE.Vector3(request.point[0] - r, y, -request.point[1] - r), new THREE.Vector3(request.point[0] + r, y + 3, -request.point[1] + r));
      c.fitToBox(box, animate, { paddingTop: 1, paddingBottom: 1, paddingLeft: 1, paddingRight: 1 });
      return;
    }
    if (request.kind === "object" && request.ids?.length) {
      box.makeEmpty();
      for (const id of request.ids) {
        const space = model.spaceById.get(id);
        if (space) {
          const y = floorY(space.floor_id);
          for (const [x, z] of space.polygon) box.expandByPoint(new THREE.Vector3(x, y, -z));
          box.expandByPoint(new THREE.Vector3(space.anchor[0], floorTop(space.floor_id) * 0.4 + y * 0.6, -space.anchor[1]));
          continue;
        }
        const asset = model.assetById.get(id);
        if (asset) {
          const y = floorY(asset.floor_id);
          box.expandByPoint(new THREE.Vector3(asset.position[0] - 4, y, -asset.position[1] - 4));
          box.expandByPoint(new THREE.Vector3(asset.position[0] + 4, y + 3, -asset.position[1] + 4));
          continue;
        }
        const opening = model.openingById.get(id);
        if (opening) {
          const y = floorY(opening.floor_id);
          box.expandByPoint(new THREE.Vector3(opening.position[0] - 4, y, -opening.position[1] - 4));
          box.expandByPoint(new THREE.Vector3(opening.position[0] + 4, y + 3, -opening.position[1] + 4));
          continue;
        }
        const connector = model.connectorById.get(id);
        if (connector) {
          for (const spaceId of connector.space_ids) {
            const stop = model.spaceById.get(spaceId);
            if (!stop) continue;
            const y = floorY(stop.floor_id);
            for (const [x, z] of stop.polygon) box.expandByPoint(new THREE.Vector3(x, y, -z));
            box.expandByPoint(new THREE.Vector3(stop.anchor[0], y + 3, -stop.anchor[1]));
          }
        }
      }
      if (box.isEmpty()) return;
      const extent = new THREE.Vector3();
      box.getSize(extent);
      const pad = Math.max(2, Math.max(extent.x, extent.z) * 0.6);
      c.fitToBox(box, animate, { paddingTop: pad, paddingBottom: pad, paddingLeft: pad, paddingRight: pad });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request.nonce, floorMode]);

  // Cutaway: outer walls facing the camera are lowered.
  const direction = new THREE.Vector2();
  useFrame(() => {
    direction.set(camera.position.x - bounds.cx, camera.position.z + bounds.cy).normalize();
    cutawayUniforms.uCamDir.value.copy(direction);
    cutawayUniforms.uCut.value = cutaway ? 1 : 0;
  });

  return (
    <CameraControls
      ref={controls}
      makeDefault
      mouseButtons={{ left: 1, middle: 8, right: 2, wheel: 8 }}
      touches={{ one: 32, two: 1024, three: 64 }}
    />
  );
}
