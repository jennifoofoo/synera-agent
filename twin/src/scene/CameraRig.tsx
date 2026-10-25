import { useCallback, useEffect, useRef } from "react";
import * as THREE from "three";
import { CameraControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import CameraControlsImpl from "camera-controls";
import type { BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { useCameraKeys } from "./cameraKeys";
import { useCameraMouse } from "./cameraMouse";
import { controlsRef, cutawayUniforms } from "./FloorMesh";

interface Props {
  model: BuildingModel;
  floorY: (floorId: string) => number;
  floorTop: (floorId: string) => number;
  topY: number;
}

const HOME_AZIMUTH = -Math.PI / 4;
const PLAN_TILT = 0.004;

/** camera-controls' fitToBox snaps the rotation to 90° steps; fitting the bounding sphere keeps the view angle. */
function fitBox(c: CameraControlsImpl, box: THREE.Box3, animate: boolean, pad = 1.08, minRadius = 3) {
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  sphere.radius = Math.max(minRadius, sphere.radius * pad);
  void c.fitToSphere(sphere, animate);
}
const HOME_POLAR = Math.PI / 3.6;

function pointInPolygon(x: number, y: number, polygon: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

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
  const rightInset = useTwin((s) => s.rightInset);
  const topInset = useTwin((s) => s.topInset);
  const route = useTwin((s) => s.state?.route ?? null);
  const directionsOpen = useTwin((s) => s.directions !== null);
  const viewMode = useTwin((s) => s.viewMode);
  const focusedFloorId = useTwin((s) => s.focusedFloorId);
  const invalidate = useThree((s) => s.invalidate);
  const flat = viewMode === "2d";
  const { bounds } = model;
  const size = bounds.size;
  const camera = useThree((s) => s.camera);
  const viewport = useThree((s) => s.size);
  // The campus site covers this canvas (hidden): it must not react to input then.
  const inUseNow = useCallback(() => !document.body.classList.contains("campus-site-open"), []);

  // The visible area is the window [bottom .. bottom + h] of a taller/wider virtual frame. The frustum must be built
  // for the aspect (and, orthographic, the extents) of that FULL frame, otherwise the crop scales x and y
  // differently and everything is stretched. react-three-fiber resets aspect/extents on resize, so this runs
  // again from an effect and from a per-frame guard.
  const insets = useRef({ bottom: 0, top: 0, right: 0 });
  insets.current = { bottom: bottomInset, top: topInset, right: rightInset };
  const applyFrame = () => {
    const w = viewport.width;
    const h = viewport.height;
    if (w < 1 || h < 1) return;
    const bottom = Math.min(insets.current.bottom, h * 0.6);
    const top = Math.min(insets.current.top, h * 0.4);
    const right = Math.min(insets.current.right, w * 0.6);
    const fullW = w + right;
    const fullH = h + bottom + top;
    const covered = bottom > 0 || right > 0 || top > 0;
    const cam = camera as THREE.PerspectiveCamera & THREE.OrthographicCamera;
    if (cam.isPerspectiveCamera) cam.aspect = covered ? fullW / fullH : w / h;
    else if (cam.isOrthographicCamera) {
      const ew = covered ? fullW : w;
      const eh = covered ? fullH : h;
      cam.left = -ew / 2;
      cam.right = ew / 2;
      cam.top = eh / 2;
      cam.bottom = -eh / 2;
    }
    if (covered) cam.setViewOffset(fullW, fullH, 0, bottom, w, h);
    else cam.clearViewOffset();
    cam.updateProjectionMatrix();
  };

  // UI covering the bottom (dock, sheet): render the top part of a taller virtual frame so the framed object
  // sits in the visible area above it.
  useEffect(() => {
    applyFrame();
    invalidate();
  }, [camera, viewport.width, viewport.height, bottomInset, rightInset, topInset, invalidate]);

  // Directions open: a new route is framed as a whole (its visible floors).
  const routeKey = route?.ok ? `${route.start}|${route.destination}|${route.length_m}` : null;
  useEffect(() => {
    const c = controls.current;
    if (!c || !routeKey || !directionsOpen || !route?.segments) return;
    const box = new THREE.Box3();
    for (const segment of route.segments) {
      if (flat && segment.floor_id !== focusedFloorId) continue;
      const y = floorY(segment.floor_id);
      for (const [x, z] of segment.points) box.expandByPoint(new THREE.Vector3(x, y, -z));
    }
    if (box.isEmpty()) return;
    box.expandByScalar(3);
    fitBox(c, box, !reducedMotion, 1.15);
    invalidate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeKey, directionsOpen, camera]);

  // Limits follow the building; the 2D plan is locked straight down, north up: pan and zoom only.
  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    c.minDistance = Math.max(2, size * 0.04);
    c.maxDistance = size * 3; // the building never shrinks below about a third of the view
    // Plan: px per metre that fits the largest floor. The plan never gets smaller than 35 percent of that (it used to
    // go down to 0.2 px/m: the floor was a few pixels in a blank grey plane).
    const largest = Math.max(1, ...model.floors.map((floor) => floor.bounds.size));
    const fit = Math.min(viewport.width, viewport.height) / largest;
    c.minZoom = fit * 0.35;
    c.maxZoom = Math.max(60, fit * 12);
    // Straight down but not exactly (a polar angle of 0 leaves the roll undefined and the plan may come up rotated).
    c.minPolarAngle = flat ? PLAN_TILT : 0.08;
    c.maxPolarAngle = flat ? PLAN_TILT : Math.PI / 2 - 0.12;
    // The plan may be rotated (right drag, two fingers) but never tilted; Home turns it back north up.
    c.minAzimuthAngle = -Infinity;
    c.maxAzimuthAngle = Infinity;
    const A = CameraControlsImpl.ACTION;
    // Left drag and middle drag pan (grab the map) in cameraMouse.ts; Ctrl or Alt + left, and right drag, rotate.
    c.mouseButtons.left = A.NONE;
    c.mouseButtons.middle = A.NONE;
    c.mouseButtons.right = A.ROTATE;
    c.mouseButtons.wheel = flat ? A.ZOOM : A.DOLLY;
    // One finger pans (cameraMouse.ts). Two fingers: 3D pinch-dolly, rotate and tilt; 2D pinch-zoom and move around
    // the midpoint in cameraMouse.ts (camera-controls turned a two-finger move into a rotation of the plan).
    c.touches.one = A.NONE;
    c.touches.two = flat ? A.NONE : A.TOUCH_DOLLY_ROTATE;
    if (flat) void c.rotateTo(c.azimuthAngle, PLAN_TILT, false);
    // Light damping: camera-controls smooths critically (no overshoot, no drift after release).
    c.smoothTime = 0.13;
    c.draggingSmoothTime = 0.04;
    c.dollyToCursor = true;
    c.infinityDolly = false;
    const margin = size * 0.25; // the target stays near the building: a drag can not carry it into empty space
    c.setBoundary(new THREE.Box3(new THREE.Vector3(bounds.minX - margin, -1, -bounds.maxY - margin), new THREE.Vector3(bounds.maxX + margin, topY + size, -bounds.minY + margin)));
    c.boundaryFriction = 0.2;
    invalidate();
    // `camera` is a dependency on purpose: drei recreates the controls when the default camera changes (2D <-> 3D).
  }, [bounds, size, topY, flat, invalidate, camera, model, viewport.width, viewport.height]);

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

  // 3D floor change: the camera glides up or down by the height difference (short, under 300 ms; reduced motion
  // jumps), so the switch reads as moving through the building. "All floors" and routes frame on their own.
  const lastFloor = useRef<string | null>(null);
  useEffect(() => {
    const previous = lastFloor.current;
    lastFloor.current = focusedFloorId;
    const c = controls.current;
    if (!c || flat || !previous || !focusedFloorId || previous === focusedFloorId || floorMode === "exploded") return;
    const dy = floorY(focusedFloorId) - floorY(previous);
    if (Math.abs(dy) < 0.01) return;
    const target = c.getTarget(new THREE.Vector3());
    const smooth = c.smoothTime;
    c.smoothTime = 0.06;
    void c.moveTo(target.x, target.y + dy, target.z, !reducedMotion).then(() => {
      c.smoothTime = smooth;
    });
    invalidate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedFloorId]);

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
        void c.rotateTo(0, PLAN_TILT, animate);
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
    // The viewport size is a dependency on purpose: a request made while the canvas was hidden or being resized
    // (campus overlay, phone rotation) is framed again once the real size is known.
  }, [request.nonce, floorMode, camera, viewport.width, viewport.height]);

  // Test hooks (read only use): the store, the controls and a frame counter, for the Playwright measurements.
  useEffect(() => {
    const w = window as unknown as Record<string, unknown>;
    w.__twinStore = useTwin;
    w.__twinCamera = camera;
  }, [camera]);

  useEffect(() => {
    controlsRef.current = controls.current;
    return () => {
      controlsRef.current = null;
    };
  });

  // Keyboard (table in controlsTable.ts): held keys move the camera per frame (cameraKeys.ts); here the host's keys.
  const onKey = useCallback(
    (event: KeyboardEvent) => {
      const store = useTwin.getState();
      const key = event.key;
      if (key === "t" || key === "T") {
        store.setViewMode(flat ? "3d" : "2d");
        return true;
      }
      const floors = model.floors;
      let floor = null as (typeof floors)[number] | null;
      if (/^[1-9]$/.test(key)) floor = floors.find((f) => f.level === Number(key)) ?? null;
      else if (key === "g" || key === "G") floor = floors.find((f) => f.level === 0) ?? null;
      else return false;
      if (floor && floor.id !== store.focusedFloorId) {
        store.focusFloor(floor.id);
        if (store.floorMode === "exploded") store.requestCamera({ kind: "floor", floorId: floor.id });
      }
      return true;
    },
    [flat, model],
  );
  const onHome = useCallback(() => useTwin.getState().requestCamera({ kind: "home" }), []);
  useCameraKeys({ controls, flat, active: inUseNow, onHome, onKey });


  // Double click on a room or the floor in 3D flies to that room (2D keeps the floor mesh's zoom-in handler).
  const scene = useThree((s) => s.scene);
  const gl = useThree((s) => s.gl);
  const raycaster = useThree((s) => s.raycaster);
  const onDoubleClick = useCallback(
    (event: MouseEvent) => {
      if (flat) return;
      const rect = gl.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
      camera.updateMatrixWorld();
      raycaster.setFromCamera(ndc, camera);
      const targets: THREE.Object3D[] = [];
      scene.traverse((object) => {
        if (object.userData?.floorId && !object.userData.ghost && (object as THREE.Mesh).isMesh) {
          let visible = true;
          for (let o: THREE.Object3D | null = object; o; o = o.parent) visible = visible && o.visible;
          if (visible) targets.push(object);
        }
      });
      const hit = raycaster.intersectObjects(targets, false)[0];
      if (!hit) return;
      const floorId = hit.object.userData.floorId as string;
      const floor = model.floorById.get(floorId);
      if (!floor) return;
      const x = hit.point.x;
      const y = -hit.point.z;
      const space = floor.spaces.find((candidate) => pointInPolygon(x, y, candidate.polygon));
      if (space) useTwin.getState().flyTo(space.id);
      else useTwin.getState().requestCamera({ kind: "point", floorId, point: [x, y], radius: 8 });
    },
    [flat, gl, camera, raycaster, scene, model],
  );
  useCameraMouse({ controls, onDoubleClick, active: inUseNow });

  // Cutaway: outer walls facing the camera are lowered. In 2D, note when the view was panned away from the floor.
  const direction = new THREE.Vector2();
  const target = new THREE.Vector3();
  useFrame(() => {
    const w = window as unknown as { __twinFrames?: number };
    w.__twinFrames = (w.__twinFrames ?? 0) + 1;
    {
      const pc = camera as THREE.PerspectiveCamera & THREE.OrthographicCamera;
      const { bottom, top, right } = insets.current;
      const covered = bottom > 0 || right > 0 || top > 0;
      const expectW = viewport.width + Math.min(right, viewport.width * 0.6);
      const stale = pc.isPerspectiveCamera
        ? Math.abs(pc.aspect - (covered ? expectW / (viewport.height + Math.min(bottom, viewport.height * 0.6) + Math.min(top, viewport.height * 0.4)) : viewport.width / viewport.height)) > 1e-4
        : Math.abs(pc.right - pc.left - (covered ? expectW : viewport.width)) > 0.5;
      if (stale || covered !== !!pc.view?.enabled) applyFrame();
    }
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
