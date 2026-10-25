import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import type { FloorModel, BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";
import { tapMap } from "../tapAnswer";
import { buildFloorGeometry, openingEditsOf, withCutaway } from "./geometry";

interface Props {
  floor: FloorModel;
  model: BuildingModel;
  y: number;
  ghost: boolean;
  visible: boolean;
}

/** Shared uniforms for the dollhouse cutaway: direction from the building centre to the camera, and on/off. */
export const cutawayUniforms = {
  uCamDir: { value: new THREE.Vector2(0, 1) },
  uCut: { value: 1 },
  uFlat: { value: 0 },
  /** Focus mode strength: 0 without a route, 1 with one (rooms off the route fade toward uPaper). */
  uFocus: { value: 0 },
  uPaper: { value: new THREE.Color(COLOURS.groundInner) },
};

/** The focus blend, shared by every floor: each FloorMesh evaluates it from the clock, so it is the same no matter
 * how many floors run useFrame (no per-frame allocation, no double stepping). */
const FOCUS_MS = 300;
const focusBlend = { from: 0, to: 0, start: 0 };
function setFocusTarget(target: number, jump: boolean) {
  if (focusBlend.to === target) return;
  focusBlend.from = jump ? target : cutawayUniforms.uFocus.value;
  focusBlend.to = target;
  focusBlend.start = performance.now();
}

/** The one CameraControls instance (set by CameraRig), for gestures handled on meshes (double tap zoom). */
export const controlsRef: { current: import("camera-controls").default | null } = { current: null };

export function FloorMesh({ floor, model, y, ghost, visible }: Props) {
  const select = tapMap; // a map tap selects, or answers Wanda's "where are you?" (tapAnswer.ts)
  const flat = useTwin((s) => s.viewMode === "2d");
  const reducedMotion = useTwin((s) => s.reducedMotion);
  // Doors added, removed or widened in this session change the walls; the key keeps route updates from rebuilding.
  const state = useTwin((s) => s.state);
  const editsKey = JSON.stringify(openingEditsOf(state));
  const built = useMemo(() => {
    const started = performance.now();
    const geometry = buildFloorGeometry(floor, JSON.parse(editsKey));
    buildTimes.set(floor.id, performance.now() - started);
    return geometry;
  }, [floor, editsKey]);
  useEffect(() => () => {
    built.solid.disposeBoundsTree?.();
    built.solid.dispose();
    built.edges.dispose();
    built.zones.dispose();
  }, [built]);

  const materials = useMemo(() => {
    const solid = withCutaway(
      new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, metalness: 0.0, flatShading: false }),
      cutawayUniforms,
    );
    const edges = withCutaway(new THREE.LineBasicMaterial({ color: COLOURS.edge, transparent: true, opacity: 0.7 }), cutawayUniforms);
    const ghostSolid = new THREE.MeshBasicMaterial({
      color: COLOURS.ghost,
      transparent: true,
      opacity: 0.1,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const ghostEdges = new THREE.LineBasicMaterial({ color: COLOURS.edgeGhost, transparent: true, opacity: 0.35, depthWrite: false });
    const zones = new THREE.LineBasicMaterial({ color: COLOURS.edgeGhost, transparent: true, opacity: 0.8 });
    return { solid, edges, ghostSolid, ghostEdges, zones };
  }, []);
  useEffect(() => () => Object.values(materials).forEach((m) => m.dispose()), [materials]);
  useEffect(() => {
    materials.edges.color.set(flat ? COLOURS.planEdge : COLOURS.edge);
    materials.edges.opacity = flat ? 1 : 0.7;
    materials.zones.color.set(flat ? COLOURS.planZone : COLOURS.edgeGhost);
    materials.solid.roughness = flat ? 1 : 0.95;
  }, [flat, materials]);

  const onDoubleClick = (event: ThreeEvent<MouseEvent>) => {
    if (!flat || ghost) return;
    event.stopPropagation();
    const c = controlsRef.current;
    if (!c) return;
    // Zoom in 2x towards the clicked point, which stays where it is on screen (map style).
    const zoom = Math.min(c.maxZoom, c.camera.zoom * 2);
    const keep = c.camera.zoom / zoom;
    const target = c.getTarget(new THREE.Vector3());
    const y = target.y;
    target.sub(event.point).multiplyScalar(keep).add(event.point).setY(y);
    void c.moveTo(target.x, target.y, target.z, !reducedMotion);
    void c.zoomTo(zoom, !reducedMotion);
  };

  const group = useRef<THREE.Group>(null);
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    invalidate(); // frameloop="demand": draw the floor as soon as its geometry is mounted or swapped
  }, [built, ghost, visible, flat, invalidate]);
  // Focus mode: with a route, every room off route.space_path fades toward the paper (slab and walls together).
  const route = state?.route;
  const routeOn = !!route?.ok;
  const pathKey = routeOn ? (route?.space_path ?? []).join("|") : "";
  useEffect(() => {
    // No route: keep the last marks, so the fade out shows the same rooms stepping forward again.
    if (!pathKey) return;
    const onRoute = new Set(pathKey.split("|"));
    const focus = built.solid.getAttribute("focus") as THREE.BufferAttribute;
    const spaceIndex = built.solid.getAttribute("spaceIndex") as THREE.BufferAttribute;
    const marks = floor.spaces.map((space) => (onRoute.has(space.id) ? 1 : 0));
    const array = focus.array as Float32Array;
    for (let i = 0; i < array.length; i++) array[i] = marks[spaceIndex.getX(i)] ?? 1;
    focus.needsUpdate = true;
    invalidate();
  }, [built, pathKey, floor, invalidate]);
  useEffect(() => {
    setFocusTarget(routeOn ? 1 : 0, reducedMotion);
    invalidate();
  }, [routeOn, reducedMotion, invalidate]);
  useEffect(() => {
    cutawayUniforms.uPaper.value.set(flat ? COLOURS.plan : COLOURS.groundInner);
  }, [flat]);

  useFrame(() => {
    if (group.current) group.current.position.y = y; // no React re-render for the exploded animation
    const t = Math.min(1, (performance.now() - focusBlend.start) / FOCUS_MS);
    const eased = t * t * (3 - 2 * t);
    cutawayUniforms.uFocus.value = focusBlend.from + (focusBlend.to - focusBlend.from) * eased;
    if (t < 1) invalidate(); // frameloop="demand": frames only while the blend runs
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
        onClick={ghost || !visible ? undefined : onClick}
        onDoubleClick={ghost || !visible ? undefined : onDoubleClick}
        renderOrder={ghost ? 10 : 0}
        layers-mask={ghost ? 2 : 1}
        userData={{ floorId: floor.id, ghost }}
        castShadow
        frustumCulled
      />
      <lineSegments geometry={built.edges} material={ghost ? materials.ghostEdges : materials.edges} renderOrder={ghost ? 11 : 1} layers-mask={ghost ? 2 : 1} />
      {!ghost && <lineSegments name="zone-lines" geometry={built.zones} material={materials.zones} renderOrder={1} layers-mask={1} />}
    </group>
  );
}

export const buildTimes = new Map<string, number>();
