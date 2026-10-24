import { useEffect, useRef } from "react";
import * as THREE from "three";
import { CameraControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import CameraControlsImpl from "camera-controls";
import type { BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { controlsRef, cutawayUniforms } from "./FloorMesh";

interface Props {
  model: BuildingModel;
  floorY: (floorId: string) => number;
  floorTop: (floorId: string) => number;
  topY: number;
}

const HOME_AZIMUTH = -Math.PI / 4;

/** camera-controls' fitToBox snaps the rotation to 90° steps; fitting the bounding sphere keeps the view angle. */
function fitBox(c: CameraControlsImpl, box: THREE.Box3, animate: boolean, pad = 1.08, minRadius = 3) {
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  sphere.radius = Math.max(minRadius, sphere.radius * pad);
  void c.fitToSphere(sphere, animate);
}
const HOME_POLAR = Math.PI / 3.6;

/** Smooth camera with limits: never below the floor, never away from the building, a sensible distance, and
 * fly-to for rooms, things, floors and points. Reduced motion: the camera jumps. */
export function CameraRig({ model, floorY, floorTop, topY }: Props) {
  const controls = useRef<CameraControlsImpl>(null);
  const request = useTwin((s) => s.camera);
  const reducedMotion = useTwin((s) => s.reducedMotion);
  const cutaway = useTwin((s) => s.cutaway);
  const floorMode = useTwin((s) => s.floorMode);
  const profile = useTwin((s) => s.profile);
  const bottomInset = useTwin((s) => s.bottomInset);
  const viewMode = useTwin((s) => s.viewMode);
  const focusedFloorId = useTwin((s) => s.focusedFloorId);
  const invalidate = useThree((s) => s.invalidate);
  const flat = viewMode === "2d";
  const { bounds } = model;
  const size = bounds.size;
  const camera = useThree((s) => s.camera);
  const viewport = useThree((s) => s.size);

  // UI covering the bottom (dock, sheet): render the top part of a taller virtual frame so the framed object
  // sits in the visible area above it.
  useEffect(() => {
    const w = viewport.width;
    const h = viewport.height;
    const inset = Math.min(bottomInset, h * 0.6);
    if (inset > 0) camera.setViewOffset(w, h + inset, 0, inset, w, h);
    else camera.clearViewOffset();
    camera.updateProjectionMatrix();
  }, [camera, viewport.width, viewport.height, bottomInset]);

  // Limits follow the building; the 2D plan is locked straight down, north up: pan and zoom only.
  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    c.minDistance = Math.max(2, size * 0.04);
    c.maxDistance = size * 4;
    c.minZoom = 0.2;
    c.maxZoom = 60;
    c.minPolarAngle = flat ? 0 : 0.08;
    c.maxPolarAngle = flat ? 0 : Math.PI / 2 - 0.12;
    c.minAzimuthAngle = flat ? 0 : -Infinity;
    c.maxAzimuthAngle = flat ? 0 : Infinity;
    const A = CameraControlsImpl.ACTION;
    c.mouseButtons.left = flat ? A.TRUCK : A.ROTATE;
    c.mouseButtons.right = A.TRUCK;
    c.mouseButtons.wheel = flat ? A.ZOOM : A.DOLLY;
    c.touches.one = flat ? A.TOUCH_TRUCK : A.TOUCH_ROTATE;
    c.touches.two = flat ? A.TOUCH_ZOOM_TRUCK : A.TOUCH_DOLLY_TRUCK;
    if (flat) void c.rotateTo(0, 0, false);
    c.smoothTime = 0.32;
    c.draggingSmoothTime = 0.08;
    c.dollyToCursor = true;
    c.infinityDolly = false;
    const margin = size * 0.6;
    c.setBoundary(new THREE.Box3(new THREE.Vector3(bounds.minX - margin, -1, -bounds.maxY - margin), new THREE.Vector3(bounds.maxX + margin, topY + size, -bounds.minY + margin)));
    c.boundaryFriction = 0.2;
    invalidate();
  }, [bounds, size, topY, flat, invalidate]);

  // Entering 2D or changing the floor in 2D frames the focused floor.
  useEffect(() => {
    const c = controls.current;
    if (!c || !flat || !focusedFloorId) return;
    const floor = model.floorById.get(focusedFloorId);
    if (!floor) return;
    const y = floorY(floor.id);
    const box = new THREE.Box3(new THREE.Vector3(floor.bounds.minX, y, -floor.bounds.maxY), new THREE.Vector3(floor.bounds.maxX, y + 1, -floor.bounds.minY));
    fitBox(c, box, !reducedMotion, 0.9);
    invalidate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flat, focusedFloorId, camera]);

  // Requests from the store. Under frameloop="demand" a camera transition needs a first frame to start, so
  // every request ends with invalidate() (the transition then keeps requesting frames through the controls).
  useEffect(() => {
    const c = controls.current;
    if (!c || !request.nonce) return;
    const animate = !reducedMotion;
    const box = new THREE.Box3();
    const kick = () => setTimeout(invalidate, 0);
    kick();
    if (request.kind === "home") {
      if (flat) {
        const floor = model.floorById.get(focusedFloorId ?? "") ?? model.floors[0];
        const y = floorY(floor.id);
        box.set(new THREE.Vector3(floor.bounds.minX, y, -floor.bounds.maxY), new THREE.Vector3(floor.bounds.maxX, y + 1, -floor.bounds.minY));
        fitBox(c, box, animate, 0.9);
        return;
      }
      box.set(new THREE.Vector3(bounds.minX, 0, -bounds.maxY), new THREE.Vector3(bounds.maxX, topY, -bounds.minY));
      void c.rotateTo(HOME_AZIMUTH, profile === "worker" ? Math.PI / 5 : HOME_POLAR, animate);
      fitBox(c, box, animate, 0.95);
      return;
    }
    if (request.kind === "floor" && request.floorId) {
      const floor = model.floorById.get(request.floorId);
      if (!floor) return;
      const y = floorY(floor.id);
      box.set(new THREE.Vector3(floor.bounds.minX, y, -floor.bounds.maxY), new THREE.Vector3(floor.bounds.maxX, y + floor.height_m, -floor.bounds.minY));
      fitBox(c, box, animate, 0.95);
      return;
    }
    if (request.kind === "point" && request.point && request.floorId) {
      const y = floorY(request.floorId);
      const r = request.radius ?? 6;
      box.set(new THREE.Vector3(request.point[0] - r, y, -request.point[1] - r), new THREE.Vector3(request.point[0] + r, y + 3, -request.point[1] + r));
      fitBox(c, box, animate, 1.1);
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
      // On a phone never fly closer than a room plus its neighbours, and look down enough to see into it.
      const worker = profile === "worker";
      if (worker && !flat && c.polarAngle > Math.PI * 0.3) void c.rotateTo(c.azimuthAngle, Math.PI * 0.28, animate);
      fitBox(c, box, animate, 1.6, worker ? Math.max(12, size * 0.1) : 3);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request.nonce, floorMode, camera]);

  useEffect(() => {
    controlsRef.current = controls.current;
    return () => {
      controlsRef.current = null;
    };
  });

  // Cutaway: outer walls facing the camera are lowered. In 2D, note when the view was panned away from the floor.
  const direction = new THREE.Vector2();
  const target = new THREE.Vector3();
  useFrame(() => {
    const c = controls.current;
    if (c && flat && focusedFloorId) {
      const floor = model.floorById.get(focusedFloorId);
      if (floor) {
        c.getTarget(target);
        const dx = Math.abs(target.x - floor.bounds.cx);
        const dz = Math.abs(-target.z - floor.bounds.cy);
        const away = dx > floor.bounds.size * 0.35 || dz > floor.bounds.size * 0.35;
        if (away !== useTwin.getState().offCentre) useTwin.setState({ offCentre: away });
      }
    } else if (useTwin.getState().offCentre) useTwin.setState({ offCentre: false });
    direction.set(camera.position.x - bounds.cx, camera.position.z + bounds.cy).normalize();
    cutawayUniforms.uCamDir.value.copy(direction);
    cutawayUniforms.uCut.value = cutaway && !flat ? 1 : 0;
    cutawayUniforms.uFlat.value = flat ? 1 : 0;
  });

  return (
    <CameraControls key={flat ? "2d" : "3d"} ref={controls} makeDefault />
  );
}
