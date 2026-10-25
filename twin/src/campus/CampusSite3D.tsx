// The site in 3D: every building at its place (origin, rotation), floors as light blue slabs with fine edges, links
// between the entrances (walkway on the ground, bridge raised by its level_delta), the route as one glowing line.
// Tap a building (or its name) = enter it. Own small Canvas, independent of the building scene.

import { CameraControls, Line } from "@react-three/drei";
import { Html } from "../scene/SharpHtml";
import { Canvas, type ThreeEvent } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef } from "react";
import CameraControlsImpl from "camera-controls";
import { useCameraKeys } from "../scene/cameraKeys";
import { useCameraMouse } from "../scene/cameraMouse";
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { CampusBuilding, CampusLink, CampusView } from "../api/campus";
import type { Building, Point } from "../api/types";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";
import { boundsOf, campusPoints, floorRings, levelElevation, toWorld, type FloorRings } from "./campusGeometry";
import { steps, useCampus } from "./campusStore";

const TAP_PX = 6;

function v3(point: Point, height: number): THREE.Vector3 {
  return new THREE.Vector3(point[0], height, -point[1]);
}

function floorGeometry(floor: FloorRings) {
  const shapes = floor.rings.map((ring) => new THREE.ShapeGeometry(new THREE.Shape(ring.map(([x, y]) => new THREE.Vector2(x, y)))));
  const slab = shapes.length ? mergeGeometries(shapes) : null;
  shapes.forEach((shape) => shape.dispose());
  const edges: number[] = [];
  for (const ring of floor.rings) {
    for (let i = 0; i < ring.length; i++) {
      const a = ring[i];
      const b = ring[(i + 1) % ring.length];
      edges.push(a[0], 0, -a[1], b[0], 0, -b[1]);
    }
  }
  const lines = new THREE.BufferGeometry();
  lines.setAttribute("position", new THREE.Float32BufferAttribute(edges, 3));
  return { slab, lines };
}

function BuildingBlock({ building, detail, onRoute, active }: { building: CampusBuilding; detail: Building | undefined; onRoute: boolean; active: boolean }) {
  const enterBuilding = useCampus((s) => s.enterBuilding);
  const floors = useMemo(() => floorRings(building, detail).map((floor) => ({ floor, ...floorGeometry(floor) })), [building, detail]);
  const top = floors.length ? floors[floors.length - 1].floor.elevation + floors[floors.length - 1].floor.height : 4;
  const enter = (event: ThreeEvent<MouseEvent>) => {
    if (event.delta > TAP_PX) return;
    event.stopPropagation();
    void enterBuilding(building.id);
  };
  const colour = active ? "#9db6dc" : onRoute ? "#d3e0f4" : "#cfccc4";
  return (
    <group>
      {floors.map(({ floor, slab, lines }, index) => (
        <group key={floor.floorId} position={[0, floor.elevation, 0]}>
          {slab && (
            <mesh geometry={slab} rotation={[-Math.PI / 2, 0, 0]} onClick={enter} onPointerOver={() => (document.body.style.cursor = "pointer")} onPointerOut={() => (document.body.style.cursor = "")}>
              <meshStandardMaterial color={colour} transparent opacity={index === 0 ? 1 : 0.6} side={THREE.DoubleSide} depthWrite={index === 0} />
            </mesh>
          )}
          <lineSegments geometry={lines}>
            <lineBasicMaterial color={COLOURS.edge} transparent opacity={index === 0 ? 0.55 : 0.35} />
          </lineSegments>
        </group>
      ))}
      {building.world_center && (
        <Html position={v3(building.world_center, top + 3)} center zIndexRange={[2, 0]}>
          <button className={`campus-3d-label ${onRoute ? "on-route" : ""}`} onClick={() => void enterBuilding(building.id)}>
            {building.name}
          </button>
        </Html>
      )}
    </group>
  );
}

function LinkBlock({ link, height, onRoute, selected }: { link: CampusLink; height: number; onRoute: boolean; selected: boolean }) {
  const selectLink = useCampus((s) => s.selectLink);
  const from = link.from.world_point;
  const to = link.to.world_point;
  const shape = useMemo(() => {
    if (!from || !to) return null;
    const dx = to[0] - from[0];
    const dz = -(to[1] - from[1]);
    const length = Math.hypot(dx, dz);
    return { length, angle: Math.atan2(-dz, dx), mid: v3([(from[0] + to[0]) / 2, (from[1] + to[1]) / 2], 0) };
  }, [from, to]);
  if (!from || !to || !shape) return null;
  const width = link.width_m ?? 2.5;
  const raised = link.kind === "bridge" || height > 0;
  const y = raised ? height : 0.06;
  const colour = link.closed ? COLOURS.danger : selected ? COLOURS.signal : "#fbfaf8";
  const mx = (from[0] + to[0]) / 2;
  const my = (from[1] + to[1]) / 2;
  return (
    <group>
      <mesh
        position={[shape.mid.x, y, shape.mid.z]}
        rotation={[0, shape.angle, 0]}
        onClick={(event) => {
          if (event.delta > TAP_PX) return;
          event.stopPropagation();
          selectLink(link.id);
          useTwin.getState().dismissReply();
        }}
      >
        <boxGeometry args={[shape.length, raised ? 0.5 : 0.12, width]} />
        <meshStandardMaterial color={colour} transparent={raised} opacity={raised ? 0.8 : 1} />
      </mesh>
      {raised &&
        [from, to].map((end, index) => (
          <mesh key={index} position={[end[0], height / 2, -end[1]]}>
            <boxGeometry args={[0.5, height, 0.5]} />
            <meshStandardMaterial color="#8f949b" />
          </mesh>
        ))}
      <Html position={[mx, y + 2, -my]} center zIndexRange={[1, 0]} style={{ pointerEvents: "none" }}>
        <span className={`campus-3d-link ${link.closed ? "closed" : ""} ${onRoute ? "on-route" : ""}`}>
          {link.name} · {Math.round(link.length_m)} m{link.closed ? " · closed" : ""}
        </span>
      </Html>
    </group>
  );
}

function routePoints(view: CampusView, legs: ReturnType<typeof steps>, heights: Map<string, number>): THREE.Vector3[] {
  const out: THREE.Vector3[] = [];
  const lift = 0.5;
  for (const leg of legs) {
    if (leg.kind === "link") {
      if (!leg.from.world_point || !leg.to.world_point) continue;
      const h = heights.get(leg.link_id) ?? 0;
      out.push(v3(leg.from.world_point, lift));
      if (h > 0) out.push(v3(leg.from.world_point, h + lift), v3(leg.to.world_point, h + lift));
      out.push(v3(leg.to.world_point, lift));
      continue;
    }
    const building = view.buildings.find((item) => item.id === leg.building_id);
    if (!building) continue;
    for (const segment of leg.segments) {
      const elevation = building.floors.find((floor) => floor.id === segment.floor_id)?.elevation_m ?? 0;
      for (const point of segment.points) out.push(v3(toWorld(building, point), elevation + lift));
    }
  }
  return out;
}

interface Frame {
  centre: THREE.Vector3;
  target: THREE.Vector3;
  camera: THREE.Vector3;
  size: number;
}

/** The same camera rig as the building view (camera-controls, same damping, mouse, touch and keys), with the site's limits. */
function CampusRig({ frame }: { frame: Frame }) {
  const controls = useRef<CameraControlsImpl>(null);
  useEffect(() => {
    (window as unknown as Record<string, unknown>).__twinCampusControls = controls; // test hook
  }, []);
  const onHome = useCallback(() => {
    void controls.current?.setLookAt(frame.camera.x, frame.camera.y, frame.camera.z, frame.target.x, frame.target.y, frame.target.z, true);
  }, [frame]);
  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    const A = CameraControlsImpl.ACTION;
    c.minDistance = frame.size * 0.15;
    c.maxDistance = frame.size * 3;
    c.minPolarAngle = 0.08;
    c.maxPolarAngle = Math.PI * 0.47;
    c.mouseButtons.left = A.NONE; // left and middle drag pan in cameraMouse.ts
    c.mouseButtons.middle = A.NONE;
    c.mouseButtons.right = A.ROTATE;
    c.mouseButtons.wheel = A.DOLLY;
    c.touches.one = A.NONE;
    c.touches.two = A.TOUCH_DOLLY_ROTATE;
    c.smoothTime = 0.13;
    c.draggingSmoothTime = 0.04;
    c.dollyToCursor = true;
    c.infinityDolly = false;
    const margin = frame.size * 0.5;
    c.setBoundary(new THREE.Box3(new THREE.Vector3(frame.centre.x - margin, -1, frame.centre.z - margin), new THREE.Vector3(frame.centre.x + margin, frame.size, frame.centre.z + margin)));
    void c.setLookAt(frame.camera.x, frame.camera.y, frame.camera.z, frame.target.x, frame.target.y, frame.target.z, false);
  }, [frame]);
  useCameraMouse({ controls });
  useCameraKeys({ controls, flat: false, onHome });
  return <CameraControls ref={controls} makeDefault />;
}

export function CampusSite3D() {
  const view = useCampus((s) => s.view)!;
  const details = useCampus((s) => s.details);
  const route = useCampus((s) => s.route);
  const step = useCampus((s) => s.step);
  const selectedLink = useCampus((s) => s.selectedLink);
  const selectLink = useCampus((s) => s.selectLink);
  const loaded = Object.keys(details).length;

  const frame = useMemo(() => {
    const b = boundsOf(campusPoints(view, details));
    const centre = new THREE.Vector3((b.minX + b.maxX) / 2, 0, -(b.minY + b.maxY) / 2);
    const size = Math.max(b.maxX - b.minX, b.maxY - b.minY, 40);
    // aim a little south of the centre so the site sits above the card and input at the bottom
    const target = centre.clone().add(new THREE.Vector3(0, 0, size * 0.18));
    const camera = target.clone().add(new THREE.Vector3(size * 0.35, size * 0.95, size * 0.85));
    return { centre, target, size, camera };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.key, loaded]);

  const heights = useMemo(() => {
    const map = new Map<string, number>();
    for (const link of view.links) {
      const from = view.buildings.find((item) => item.id === link.from.building_id) ?? null;
      map.set(link.id, link.level_delta ? levelElevation(from, Math.abs(link.level_delta)) || 3.5 * Math.abs(link.level_delta) : 0);
    }
    return map;
  }, [view]);

  const legs = steps(route);
  const line = useMemo(() => (route?.ok ? routePoints(view, route.legs ?? [], heights) : []), [view, route, heights]);
  const activeLeg = step !== null ? legs[step] : undefined;
  const routeBuildings = new Set(route?.ok ? route.buildings : []);
  const routeLinks = new Set(route?.ok ? route.links_used : []);

  return (
    <Canvas
      className="campus-3d"
      frameloop="demand"
      dpr={[1, 2]}
      camera={{ position: frame.camera.toArray(), fov: 40, near: 1, far: frame.size * 20 }}
      onPointerMissed={() => selectLink(null)}
      key={`${view.key}-${loaded}`}
    >
      <color attach="background" args={[COLOURS.background]} />
      <ambientLight intensity={1.6} />
      <directionalLight position={[frame.size, frame.size * 2, frame.size * 0.6]} intensity={1.4} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[frame.centre.x, -0.05, frame.centre.z]} onClick={() => selectLink(null)}>
        <planeGeometry args={[frame.size * 4, frame.size * 4]} />
        <meshStandardMaterial color={COLOURS.ground} />
      </mesh>
      {view.buildings.map((building) => (
        <BuildingBlock
          key={building.id}
          building={building}
          detail={details[building.id]}
          onRoute={routeBuildings.has(building.id)}
          active={activeLeg?.kind === "building" && activeLeg.building_id === building.id}
        />
      ))}
      {view.links.map((link) => (
        <LinkBlock key={link.id} link={link} height={heights.get(link.id) ?? 0} onRoute={routeLinks.has(link.id)} selected={selectedLink === link.id} />
      ))}
      {line.length > 1 && (
        <>
          <Line points={line} color="#ffffff" lineWidth={9} transparent depthTest={false} depthWrite={false} renderOrder={10} />
          <Line points={line} color={COLOURS.route} lineWidth={5} transparent depthTest={false} depthWrite={false} renderOrder={11} />
        </>
      )}
      <CampusRig frame={frame} />
    </Canvas>
  );
}
