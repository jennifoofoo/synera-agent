import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { GizmoHelper, GizmoViewcube, OrthographicCamera, PerformanceMonitor, PerspectiveCamera } from "@react-three/drei";

// Postprocessing (N8AO etc.) is planner-only and loaded on demand, so phones never download it.
const Effects = lazy(() => import("./Effects"));
import type { BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";
import { CameraRig } from "./CameraRig";
import { FloorMesh, buildTimes, controlsRef } from "./FloorMesh";
import { GroundGrid } from "./GroundGrid";
import { Labels } from "./Labels";
import { Markers } from "./Markers";
import { OpeningMarks } from "./OpeningMarks";
import { RouteLine } from "./RouteLine";
import { FloorOutline, floorLayout, floorRoles, routeFloorIds } from "./floorVisibility";
import { Things } from "./Things";

const NEAR_THINGS_LIMIT = 6000;
const ALL_THINGS_LIMIT = 4000;

function Building({ model }: { model: BuildingModel }) {
  const floorMode = useTwin((s) => s.floorMode);
  const focusedFloorId = useTwin((s) => s.focusedFloorId);
  const thingsMode = useTwin((s) => s.thingsMode);
  const state = useTwin((s) => s.state);
  const highlights = useTwin((s) => s.highlights);
  const selection = useTwin((s) => s.selection);
  const reducedMotion = useTwin((s) => s.reducedMotion);
  const profile = useTwin((s) => s.profile);
  const viewMode = useTwin((s) => s.viewMode);
  const worker = profile === "worker";
  const flat = viewMode === "2d";

  const focused = focusedFloorId ?? model.floors[0]?.id ?? null;
  // Floor rule (floorVisibility.tsx): active floor full, floors below as outlines, floors above hidden; a route over
  // several floors shows exactly its floors, stacked apart.
  const routeFloorsKey = flat ? "" : (routeFloorIds(state?.route)?.join("|") ?? "");
  const routeFloors = useMemo(() => (routeFloorsKey ? routeFloorsKey.split("|") : null), [routeFloorsKey]);
  const elevations = useMemo(
    () => new Map(model.floors.map((floor) => [floor.id, floorLayout(floor, model, floorMode, routeFloors)])),
    [model, floorMode, routeFloors],
  );
  const floorY = useCallback((floorId: string) => elevations.get(floorId) ?? 0, [elevations]);
  const floorTop = useCallback((floorId: string) => (elevations.get(floorId) ?? 0) + (model.floorById.get(floorId)?.height_m ?? 3), [elevations, model]);
  const topY = Math.max(...model.floors.map((floor) => floorTop(floor.id)));
  const roles = useMemo(() => floorRoles(model, focused, floorMode, flat, routeFloors), [model, focused, floorMode, flat, routeFloors]);
  const visibleFloors = useMemo(() => new Set(model.floors.filter((floor) => roles.get(floor.id) === "full").map((floor) => floor.id)), [model, roles]);
  const route = state?.route ?? null;
  const guideSegments = state?.guide?.active ? state.guide.leg.segments : null;

  return (
    <group>
      {model.floors.map((floor) => {
        const isFocused = floor.id === focused;
        const visible = visibleFloors.has(floor.id);
        const showThings = visible && thingsMode !== "off" && (thingsMode === "all" || isFocused);
        return (
          <group key={floor.id}>
            <FloorMesh floor={floor} model={model} y={floorY(floor.id)} ghost={false} visible={visible} />
            {roles.get(floor.id) === "outline" && <FloorOutline floor={floor} y={floorY(floor.id)} />}
            {showThings && <Things floor={floor} y={floorY(floor.id)} state={state} limit={thingsMode === "all" ? ALL_THINGS_LIMIT : NEAR_THINGS_LIMIT} flat={flat} />}
            {isFocused && visible && <Labels floor={floor} model={model} y={floorY(floor.id)} limit={flat ? (worker ? 30 : 80) : worker ? 14 : 36} flat={flat} />}
          </group>
        );
      })}
      {/* No see-through stair and lift shafts any more: a multi-floor route draws its vertical run (RouteLine). */}
      <RouteLine route={route} guideSegments={guideSegments} model={model} floorY={floorY} onlyFloor={routeFloors ? null : focused} reducedMotion={reducedMotion} flat={flat} />
      <Markers
        model={model}
        state={state}
        floorY={floorY}
        visibleFloors={visibleFloors}
        focusedFloorId={focused}
        highlights={highlights}
        selection={selection}
        reducedMotion={reducedMotion}
        worker={worker}
        flat={flat}
      />
      <OpeningMarks model={model} state={state} floorY={floorY} visibleFloors={visibleFloors} />
      <CameraRig model={model} floorY={floorY} floorTop={floorTop} topY={topY} />
    </group>
  );
}

/** `window.__twinStats()` for measuring: draw calls, triangles, geometry build times per floor (ms). */
function Stats() {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  useEffect(() => {
    (window as unknown as { __twinMounted: number }).__twinMounted = Math.round(performance.now());
    (window as unknown as { __twinScene: unknown }).__twinScene = scene;
    (window as unknown as { __twinControls: unknown }).__twinControls = controlsRef;
    (window as unknown as { __twinStats: () => unknown }).__twinStats = () => ({
      calls: gl.info.render.calls,
      triangles: gl.info.render.triangles,
      buildMs: Object.fromEntries([...buildTimes].map(([id, ms]) => [id, Math.round(ms)])),
    });
  }, [gl, scene]);
  const invalidate = useThree((s) => s.invalidate);
  const model = useTwin((s) => s.model);
  const viewMode = useTwin((s) => s.viewMode);
  const state = useTwin((s) => s.state);
  useEffect(() => {
    // frameloop="demand": anything that changes what is drawn asks for a frame (and one more after layout).
    invalidate();
    const timer = setTimeout(invalidate, 50);
    return () => clearTimeout(timer);
  }, [model, viewMode, state, invalidate]);
  useFrame(() => {
    const w = window as unknown as { __twinFirstFrame?: number };
    // With the EffectComposer gl.info holds only the last pass, so count frames instead of triangles.
    if (w.__twinFirstFrame === undefined && gl.info.render.frame > 2 && buildTimes.size > 0) w.__twinFirstFrame = Math.round(performance.now());
  });
  return null;
}

export function Scene() {
  const model = useTwin((s) => s.model);
  const profile = useTwin((s) => s.profile);
  const ao = useTwin((s) => s.ao);
  const viewMode = useTwin((s) => s.viewMode);
  const worker = profile === "worker";
  const flat = viewMode === "2d";
  const size = model?.bounds.size ?? 60;
  const groundY = (model ? Math.min(...model.floors.map((floor) => floor.elevation_m)) : 0) - 0.3;
  const centre: [number, number, number] = model ? [model.bounds.cx, groundY, -model.bounds.cy] : [0, groundY, 0];
  const select = useTwin((s) => s.select);
  // Adaptive quality: the PerformanceMonitor steps this down when frames drop (pixel ratio, AO quality).
  const [quality, setQuality] = useState(2);
  const dpr = worker ? [1, 1.5][Math.min(quality, 1)] : [1, 1.5, 2][quality];
  // Test hook (tests/e2e/test_twin_ghost.py): step the quality like the PerformanceMonitor does.
  useEffect(() => {
    (window as unknown as { __twinSetQuality: (q: number) => void }).__twinSetQuality = (q) => setQuality(Math.max(0, Math.min(2, q)));
  }, []);

  return (
    <Canvas
      dpr={dpr}
      frameloop={worker ? "demand" : "always"}
      gl={{ antialias: !ao || worker, powerPreference: "high-performance", logarithmicDepthBuffer: false }}
      onPointerMissed={() => select(null)}
      shadows={false}
      style={{ position: "absolute", inset: 0, touchAction: "none" }}
    >
      {flat ? (
        <OrthographicCamera makeDefault position={[centre[0], size * 2, centre[2]]} near={0.1} far={size * 12} zoom={4} />
      ) : (
        <PerspectiveCamera makeDefault fov={38} near={0.5} far={size * 12} position={[centre[0] + size, size * 0.9, centre[2] + size]} />
      )}
      <color attach="background" args={[flat ? COLOURS.plan : COLOURS.background]} />
      {!flat && <fog attach="fog" args={[COLOURS.background, size * 2.5, size * 9]} />}
      <hemisphereLight args={["#ffffff", "#b8b4ac", 1.0]} />
      <directionalLight position={[centre[0] + size * 0.6, size * 1.2, centre[2] + size * 0.4]} intensity={1.25} color="#ffffff" />
      <directionalLight position={[centre[0] - size * 0.8, size * 0.5, centre[2] - size * 0.6]} intensity={0.35} color="#e8e4dc" />
      <PerformanceMonitor
        flipflops={4}
        bounds={() => [40, 58]}
        onDecline={() => setQuality((q) => Math.max(0, q - 1))}
        onIncline={() => setQuality((q) => Math.min(2, q + 1))}
      />
      <mesh rotation-x={-Math.PI / 2} position={[centre[0], groundY, centre[2]]} renderOrder={-1}>
        <planeGeometry args={[size * 60, size * 60]} />
        <meshBasicMaterial color={flat ? COLOURS.plan : COLOURS.ground} />
      </mesh>
      {!flat && <GroundGrid centre={centre} radius={size * 1.6} />}
      <Stats />
      <Suspense fallback={null}>{model && <Building model={model} />}</Suspense>
      {!worker && !flat && (
        <GizmoHelper alignment="bottom-right" margin={[64, 64]} renderPriority={2}>
          <GizmoViewcube color="#fbfaf8" hoverColor="#eae7e1" textColor="#1d2430" strokeColor="#bdb7ab" opacity={0.95} faces={["E", "W", "Top", "Bottom", "N", "S"]} />
        </GizmoHelper>
      )}
      {ao && !worker && !flat && (
        <Suspense fallback={null}>
          <Effects quality={quality} />
        </Suspense>
      )}
    </Canvas>
  );
}
