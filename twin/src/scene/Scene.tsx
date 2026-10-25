import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { NoToneMapping } from "three";
import { OrthographicCamera, PerformanceMonitor, PerspectiveCamera } from "@react-three/drei";

// Postprocessing (N8AO etc.) is planner-only and loaded on demand, so phones never download it.
const Effects = lazy(() => import("./Effects"));
import type { BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";
import { CameraRig } from "./CameraRig";
import { FollowCam } from "./FollowCam";
import { Declutter } from "./Declutter";
import { FloorRise } from "./FloorRise";
import { FloorMesh, buildTimes, controlsRef } from "./FloorMesh";
import { Labels } from "./Labels";
import { Markers } from "./Markers";
import { FactPins } from "./FactPins";
import { OpeningMarks } from "./OpeningMarks";
import { RouteLine } from "./RouteLine";
import { RoundMarks } from "./RoundMarks";
import { FloorOutline, floorLayout, floorRoles, routeFloorIds } from "./floorVisibility";
import { Things } from "./Things";
import { Plinth, StudioLight, StudioShadows, useSoftwareGl } from "./Studio";
import { openingEditsOf } from "./geometry";

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
  const software = useSoftwareGl();

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
  // The soft shadow is baked again only when what casts it changes (floor, floor mode, route floors, things, doors).
  const bakeKey = `${model.building.key}:${focused}:${floorMode}:${thingsMode}:${routeFloorsKey}:${JSON.stringify(openingEditsOf(state))}`;
  const shadowFloor = routeFloors ? routeFloors.reduce((top, id) => (floorY(id) > floorY(top) ? id : top), routeFloors[0]) : focused;
  const guideSegments = state?.guide?.active ? state.guide.leg.segments : null;

  return (
    <group>
      {model.floors.map((floor) => {
        const isFocused = floor.id === focused;
        const visible = visibleFloors.has(floor.id);
        const showThings = visible && thingsMode !== "off" && (thingsMode === "all" || isFocused);
        return (
          <FloorRise key={floor.id} active={visible} y={floorY(floor.id)}>
            <FloorMesh floor={floor} model={model} y={floorY(floor.id)} ghost={false} visible={visible} />
            {roles.get(floor.id) === "outline" && <FloorOutline floor={floor} y={floorY(floor.id)} />}
            {showThings && <Things floor={floor} y={floorY(floor.id)} state={state} limit={thingsMode === "all" ? ALL_THINGS_LIMIT : NEAR_THINGS_LIMIT} flat={flat} />}
            {isFocused && visible && <Labels floor={floor} model={model} y={floorY(floor.id)} limit={flat ? (worker ? 30 : 80) : worker ? 14 : 36} flat={flat} />}
          </FloorRise>
        );
      })}
      {/* the shadow lies on the top full floor: a floor stacked above would throw its slab over the one below */}
      {!flat && !worker && !software && shadowFloor && <StudioShadows model={model} y={floorY(shadowFloor)} bakeKey={bakeKey} />}
      {/* No see-through stair and lift shafts any more: a multi-floor route draws its vertical run (RouteLine). */}
      <RouteLine route={route} guideSegments={guideSegments} model={model} floorY={floorY} onlyFloor={routeFloors ? null : focused} reducedMotion={reducedMotion} flat={flat} worker={worker} />
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
      <RoundMarks floorY={floorY} visibleFloors={visibleFloors} reducedMotion={reducedMotion} />
      <FactPins model={model} floorY={floorY} visibleFloors={visibleFloors} />
      <CameraRig model={model} floorY={floorY} floorTop={floorTop} topY={topY} />
      <FollowCam model={model} floorY={floorY} />
      <Declutter />
    </group>
  );
}

/** Planner (3D): studio light from an environment map plus a low sky dome as a safety net. Phone, 2D and software
 * WebGL: the cheap lights (a bright sky dome, a steep key light, a cool fill). */
function Lights({ studio, centre, size }: { studio: boolean; centre: [number, number, number]; size: number }) {
  const software = useSoftwareGl();
  const full = studio && !software;
  return (
    <>
      {full && <StudioLight />}
      <hemisphereLight args={[COLOURS.sky, COLOURS.groundLight, full ? 0.6 : 2.1]} />
      {!full && <directionalLight position={[centre[0] + size * 0.6, size * 1.6, centre[2] + size * 0.4]} intensity={0.9} color={COLOURS.sky} />}
      {!full && <directionalLight position={[centre[0] - size * 0.8, size * 0.5, centre[2] - size * 0.6]} intensity={0.6} color={COLOURS.fill} />}
    </>
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
      // 3D: transparent over the CSS studio backdrop (styles.css, .app.solid); 2D keeps its solid plan colour.
      gl={{ alpha: true, antialias: !ao || worker, powerPreference: "high-performance", logarithmicDepthBuffer: false, toneMapping: NoToneMapping }}
      onPointerMissed={() => select(null)}
      shadows={!worker}
      style={{ position: "absolute", inset: 0, touchAction: "none" }}
    >
      {flat ? (
        <OrthographicCamera makeDefault position={[centre[0], size * 2, centre[2]]} near={0.1} far={size * 12} zoom={4} />
      ) : (
        <PerspectiveCamera makeDefault fov={32} near={0.5} far={size * 12} position={[centre[0] + size, size * 0.9, centre[2] + size]} />
      )}
      {flat && <color attach="background" args={[COLOURS.plan]} />}
      {!flat && <fog attach="fog" args={[COLOURS.studioBottom, size * 3, size * 10]} />}
      <Lights studio={!flat && !worker} centre={centre} size={size} />
      <PerformanceMonitor
        flipflops={4}
        bounds={() => [40, 58]}
        onDecline={() => setQuality((q) => Math.max(0, q - 1))}
        onIncline={() => setQuality((q) => Math.min(2, q + 1))}
      />
      {flat && (
        <mesh rotation-x={-Math.PI / 2} position={[centre[0], groundY, centre[2]]} renderOrder={-1}>
          <planeGeometry args={[size * 60, size * 60]} />
          <meshBasicMaterial color={COLOURS.plan} />
        </mesh>
      )}
      {model && !flat && <Plinth model={model} />}
      <Stats />
      <Suspense fallback={null}>{model && <Building model={model} />}</Suspense>
      {ao && !worker && !flat && (
        <Suspense fallback={null}>
          <Effects quality={quality} />
        </Suspense>
      )}
    </Canvas>
  );
}
