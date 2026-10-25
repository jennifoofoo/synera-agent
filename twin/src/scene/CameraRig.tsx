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
import { orthoZoomToDistance } from "./twoFinger";

interface Props {
  model: BuildingModel;
  floorY: (floorId: string) => number;
  floorTop: (floorId: string) => number;
  topY: number;
}

const HOME_AZIMUTH = -Math.PI / 4;
const PLAN_TILT = 0.004;
/** The flattest 3D view: about 57 degrees from straight down. Flatter, walls hide each other and far labels pile
 * up; this holds for every input (drag, Option + swipe, keys, the tilt buttons). */
export const MAX_TILT = 1.0;

/** camera-controls' fitToBox snaps the rotation to 90° steps; fitting the bounding sphere keeps the view angle. */
function fitBox(c: CameraControlsImpl, box: THREE.Box3, animate: boolean, pad = 1.08, minRadius = 3) {
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  sphere.radius = Math.max(minRadius, sphere.radius * pad);
  void c.fitToSphere(sphere, animate);
}
/** 2D plan: fit the floor's rectangle into the visible map (orthographic zoom = px per metre) minus the chrome, so a
 * long narrow building fits top to bottom too (fitToSphere fitted the diagonal and cut it). */
function fitPlan(c: CameraControlsImpl, camera: THREE.Camera, box: THREE.Box3, view: { width: number; height: number }, animate: boolean) {
  if (!(camera as THREE.OrthographicCamera).isOrthographicCamera || view.width < 1 || view.height < 1) {
    fitBox(c, box, animate, 0.9);
    return;
  }
  const size = box.getSize(new THREE.Vector3());
  const centre = box.getCenter(new THREE.Vector3());
  const availW = Math.max(60, view.width - 96); // the floor rail on the right
  const availH = Math.max(60, view.height - 120); // buttons on top, a little air below
  const zoom = Math.min(availW / Math.max(1, size.x), availH / Math.max(1, size.z));
  void c.moveTo(centre.x, centre.y, centre.z, animate);
  void c.zoomTo(zoom, animate);
}
const HOME_POLAR = Math.PI / 3.6;
/** Screen space (px) the laptop chrome covers around the 3D home view: name chip, voice bar, floor rail. */
const HOME_CHROME = { top: 80, bottom: 104, left: 24, right: 72 };

/** Home in 3D, tight: the building's own points (its footprint corners, else the box's corners; not the bounding
 * sphere, which leaves a flat building small in a wide window) fill the screen minus the chrome, seen from
 * `azimuth` / `polar`. Projects with a copy of the real camera (its view offset included) and searches the distance,
 * then centres the projection in the free area. */
function fitHome(
  c: CameraControlsImpl,
  camera: THREE.Camera,
  box: THREE.Box3,
  azimuth: number,
  polar: number,
  view: { width: number; height: number },
  animate: boolean,
  points?: THREE.Vector3[],
  planner = false,
) {
  if (!(camera as THREE.PerspectiveCamera).isPerspectiveCamera || view.width < 1 || view.height < 1) {
    void c.rotateTo(azimuth, polar, animate);
    fitBox(c, box, animate, 0.95);
    return;
  }
  const probe = (camera as THREE.PerspectiveCamera).clone();
  // Phone chrome only on the phone profile: on the laptop a narrow map (next to the chat column) still has the
  // floor rail on the right and the buttons on top.
  const chrome = view.width < 700 && !planner ? { top: 72, bottom: 120, left: 12, right: 12 } : HOME_CHROME;
  const lo = new THREE.Vector2(-1 + (2 * chrome.left) / view.width, -1 + (2 * chrome.bottom) / view.height);
  const hi = new THREE.Vector2(1 - (2 * chrome.right) / view.width, 1 - (2 * chrome.top) / view.height);
  const direction = new THREE.Vector3().setFromSpherical(new THREE.Spherical(1, polar, azimuth));
  const corners: THREE.Vector3[] = points?.length ? points : [];
  if (!corners.length) {
    for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) corners.push(new THREE.Vector3(x, y, z));
  }
  const target = box.getCenter(new THREE.Vector3());
  const point = new THREE.Vector3();
  const place = (distance: number) => {
    probe.position.copy(target).addScaledVector(direction, distance);
    probe.up.set(0, 1, 0);
    probe.lookAt(target);
    probe.updateMatrixWorld(true);
  };
  const extent = (distance: number) => {
    place(distance);
    const min = new THREE.Vector2(Infinity, Infinity);
    const max = new THREE.Vector2(-Infinity, -Infinity);
    for (const corner of corners) {
      point.copy(corner).project(probe);
      min.set(Math.min(min.x, point.x), Math.min(min.y, point.y));
      max.set(Math.max(max.x, point.x), Math.max(max.y, point.y));
    }
    return { min, max };
  };
  const radius = box.getBoundingSphere(new THREE.Sphere()).radius;
  let distance = radius * 3;
  for (let pass = 0; pass < 3; pass++) {
    // the smallest distance at which the box fits the free area (its width and height; centring follows)
    let near = Math.max(1, radius * 0.6);
    let far = radius * 12;
    for (let i = 0; i < 28; i++) {
      const mid = (near + far) / 2;
      const { min, max } = extent(mid);
      if (max.x - min.x <= hi.x - lo.x && max.y - min.y <= hi.y - lo.y) far = mid;
      else near = mid;
    }
    distance = far;
    // move the target so the box's projection sits in the middle of the free area
    const { min, max } = extent(distance);
    const depth = target.clone().project(probe).z;
    const from = new THREE.Vector3((min.x + max.x) / 2, (min.y + max.y) / 2, depth).unproject(probe);
    const to = new THREE.Vector3((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, depth).unproject(probe);
    target.add(from.sub(to));
  }
  distance *= 1.04; // a hair of air around the building
  place(distance);
  void c.setLookAt(probe.position.x, probe.position.y, probe.position.z, target.x, target.y, target.z, animate);
}

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
    if (!c || !routeKey || !directionsOpen || !route?.segments || useTwin.getState().viewHandover) return;
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
    c.minZoom = fit * 0.6;
    c.maxZoom = Math.max(60, fit * 12);
    // Straight down but not exactly (a polar angle of 0 leaves the roll undefined and the plan may come up rotated).
    c.minPolarAngle = flat ? PLAN_TILT : 0.08;
    c.maxPolarAngle = flat ? PLAN_TILT : MAX_TILT;
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
    c.smoothTime = profile === "worker" ? 0.13 : 0.18; // fly-tos glide a touch longer on the laptop
    c.draggingSmoothTime = 0.04;
    c.dollyToCursor = true;
    c.infinityDolly = false;
    const margin = Math.max(2, size * 0.08); // the target stays inside the building (plus a little): a drag or pinch can not carry it off screen
    // The box must contain every target the rig itself sets (home framing puts it at the plinth, below y = 0): a
    // target outside the box in y makes camera-controls' _encloseToBoundary divide by zero on the next pan (offset
    // horizontal, clamp vertical: dot = 0) and the camera becomes NaN, the map goes blank.
    const lowY = Math.min(-1, ...model.floors.map((floor) => floorY(floor.id))) - Math.max(5, size * 0.25);
    c.setBoundary(new THREE.Box3(new THREE.Vector3(bounds.minX - margin, lowY, -bounds.maxY - margin), new THREE.Vector3(bounds.maxX + margin, topY + size, -bounds.minY + margin)));
    c.boundaryFriction = 0.2;
    invalidate();
    // `camera` is a dependency on purpose: drei recreates the controls when the default camera changes (2D <-> 3D).
  }, [bounds, size, topY, flat, invalidate, camera, model, viewport.width, viewport.height, profile]);

  // Entering 2D or changing the floor in 2D frames the focused floor, north up (the plan is axis-aligned; the
  // label layout in Labels.tsx assumes it too). Q/E and a right drag may still turn it, Home turns it back.
  useEffect(() => {
    const c = controls.current;
    // A gesture switch keeps the view instead (viewHandover, applied below).
    if (!c || !flat || !focusedFloorId || useTwin.getState().viewHandover) return;
    const floor = model.floorById.get(focusedFloorId);
    if (!floor) return;
    const y = floorY(floor.id);
    const box = new THREE.Box3(new THREE.Vector3(floor.bounds.minX, y, -floor.bounds.maxY), new THREE.Vector3(floor.bounds.maxX, y + 1, -floor.bounds.minY));
    void c.rotateTo(0, PLAN_TILT, !reducedMotion);
    fitPlan(c, camera, box, viewport, !reducedMotion);
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
    // The new camera after a gesture switch keeps the view: the last request is not framed again.
    if (!c || !request.nonce || useTwin.getState().viewHandover) return;
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
        fitPlan(c, camera, box, viewport, animate);
        return;
      }
      const polar = profile === "worker" ? Math.PI / 5 : HOME_POLAR;
      if (floorMode === "exploded") {
        box.set(new THREE.Vector3(bounds.minX, 0, -bounds.maxY), new THREE.Vector3(bounds.maxX, topY, -bounds.minY));
        void c.rotateTo(HOME_AZIMUTH, polar, animate);
        fitBox(c, box, animate, 0.95);
        return;
      }
      // One floor at a time: frame what is drawn, the focused floor and the outlines below it (floors above are
      // hidden, an upper floor that reaches past the ground floor must not shrink the view).
      const focused = model.floorById.get(focusedFloorId ?? "") ?? model.floors[0];
      const points: THREE.Vector3[] = [];
      const wallTop = floorY(focused.id) + 1.2; // the cut walls
      for (const floor of model.floors) {
        if (floor.level > focused.level) continue;
        const y = floorY(floor.id);
        for (const space of floor.spaces) {
          for (const [x, z] of space.polygon) {
            points.push(new THREE.Vector3(x, y, -z));
            if (floor.id === focused.id) points.push(new THREE.Vector3(x, wallTop, -z));
          }
        }
      }
      for (const point of points) box.expandByPoint(point);
      if (box.isEmpty()) box.set(new THREE.Vector3(bounds.minX, 0, -bounds.maxY), new THREE.Vector3(bounds.maxX, topY, -bounds.minY));
      fitHome(c, camera, box, HOME_AZIMUTH, polar, viewport, animate, points, profile === "planner");
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

  // A gesture switched 2D <-> 3D (store.tiltTo3d / tiltTo2d): the new controls take over the old view without
  // animation, same target, same scale in the image centre, same heading. Runs after the effects above, which skip
  // their framing while a handover is pending. The button and key T set no handover and behave as before.
  useEffect(() => {
    const c = controls.current;
    const handover = useTwin.getState().viewHandover;
    if (!c || !handover) return;
    if (handover.mode !== viewMode) {
      useTwin.setState({ viewHandover: null });
      return;
    }
    const cam = c.camera as THREE.PerspectiveCamera & THREE.OrthographicCamera;
    if (cam !== camera || !!cam.isOrthographicCamera !== flat) {
      // The new default camera is not there yet. Never leave a handover behind: it would block the framing above.
      const stale = setTimeout(() => {
        if (useTwin.getState().viewHandover === handover) useTwin.setState({ viewHandover: null });
      }, 1000);
      return () => clearTimeout(stale);
    }
    useTwin.setState({ viewHandover: null });
    const [x, y, z] = handover.target;
    void c.moveTo(x, y, z, false);
    if (flat) {
      void c.rotateTo(handover.azimuth, PLAN_TILT, false);
      void c.zoomTo(handover.scale, false);
    } else {
      const frameHeight = cam.view?.enabled ? cam.view.fullHeight : viewport.height;
      void c.rotateTo(handover.azimuth, Math.max(handover.polar, c.minPolarAngle), false);
      void c.dollyTo(orthoZoomToDistance(handover.scale, frameHeight, cam.fov), false);
    }
    invalidate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flat, camera]);

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
  // Last line of defence: a NaN in the camera blanks the map until reload. Keep the last finite view and restore it.
  const goodTarget = useRef<THREE.Vector3 | null>(null);
  const goodPosition = useRef<THREE.Vector3 | null>(null);
  useFrame(() => {
    const w = window as unknown as { __twinFrames?: number };
    w.__twinFrames = (w.__twinFrames ?? 0) + 1;
    {
      const c = controls.current;
      if (c) {
        c.getTarget(target);
        const p = camera.position;
        const finite = Number.isFinite(target.x + target.y + target.z) && Number.isFinite(p.x + p.y + p.z);
        if (finite) {
          (goodTarget.current ??= new THREE.Vector3()).copy(target);
          (goodPosition.current ??= new THREE.Vector3()).copy(p);
        } else if (goodTarget.current && goodPosition.current) {
          const [t, q] = [goodTarget.current, goodPosition.current];
          void c.setLookAt(q.x, q.y, q.z, t.x, t.y, t.z, false);
          invalidate();
        }
      }
    }
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
