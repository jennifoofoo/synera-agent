import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { ContactShadows, GizmoHelper, GizmoViewcube, Grid, PerformanceMonitor } from "@react-three/drei";
import { EffectComposer, N8AO, SMAA, Vignette } from "@react-three/postprocessing";
import { floorElevation, type BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";
import { CameraRig } from "./CameraRig";
import { FloorMesh, buildTimes } from "./FloorMesh";
import { Labels } from "./Labels";
import { Markers } from "./Markers";
import { RouteLine } from "./RouteLine";
import { Shafts } from "./Shafts";
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
  const worker = profile === "worker";

  const elevations = useMemo(() => new Map(model.floors.map((floor) => [floor.id, floorElevation(floor, model, floorMode)])), [model, floorMode]);
  const floorY = useCallback((floorId: string) => elevations.get(floorId) ?? 0, [elevations]);
  const floorTop = useCallback((floorId: string) => (elevations.get(floorId) ?? 0) + (model.floorById.get(floorId)?.height_m ?? 3), [elevations, model]);
  const topY = Math.max(...model.floors.map((floor) => floorTop(floor.id)));
  const focused = focusedFloorId ?? model.floors[0]?.id ?? null;
  const visibleFloors = useMemo(
    () => new Set(model.floors.filter((floor) => floorMode !== "single" || floor.id === focused).map((floor) => floor.id)),
    [model, floorMode, focused],
  );
  const closed = useMemo(() => new Set(state?.closed ?? []), [state?.closed]);
  const route = state?.route ?? null;
  const guideSegments = state?.guide?.active ? state.guide.leg.segments : null;

  return (
    <group>
      {model.floors.map((floor) => {
        const isFocused = floor.id === focused;
        const ghost = floorMode === "stacked" && !isFocused;
        const visible = visibleFloors.has(floor.id);
        const showThings = visible && thingsMode !== "off" && (thingsMode === "all" ? !ghost : isFocused);
        return (
          <group key={floor.id}>
            <FloorMesh floor={floor} model={model} y={floorY(floor.id)} ghost={ghost} visible={visible} />
            {showThings && <Things floor={floor} y={floorY(floor.id)} state={state} limit={thingsMode === "all" ? ALL_THINGS_LIMIT : NEAR_THINGS_LIMIT} />}
            {isFocused && visible && <Labels floor={floor} model={model} y={floorY(floor.id)} limit={worker ? 14 : 36} />}
          </group>
        );
      })}
      {floorMode !== "single" && <Shafts model={model} floorY={floorY} floorTop={floorTop} closed={closed} />}
      <RouteLine route={route} guideSegments={guideSegments} model={model} floorY={floorY} onlyFloor={floorMode === "single" ? focused : null} reducedMotion={reducedMotion} />
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
      />
      <CameraRig model={model} floorY={floorY} floorTop={floorTop} topY={topY} />
      {!worker && (
        <ContactShadows
          key={`${model.building.key}-${floorMode}`}
          position={[model.bounds.cx, Math.min(...model.floors.map((floor) => floor.elevation_m)) - 0.25, -model.bounds.cy]}
          scale={model.bounds.size * 1.6}
          blur={2.4}
          opacity={0.45}
          far={topY + 4}
          resolution={512}
          frames={1}
          color="#061227"
        />
      )}
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
    (window as unknown as { __twinStats: () => unknown }).__twinStats = () => ({
      calls: gl.info.render.calls,
      triangles: gl.info.render.triangles,
      buildMs: Object.fromEntries([...buildTimes].map(([id, ms]) => [id, Math.round(ms)])),
    });
  }, [gl, scene]);
  useFrame(() => {
    const w = window as unknown as { __twinFirstFrame?: number };
    if (w.__twinFirstFrame === undefined && gl.info.render.triangles > 100) w.__twinFirstFrame = Math.round(performance.now());
  });
  return null;
}

export function Scene() {
  const model = useTwin((s) => s.model);
  const profile = useTwin((s) => s.profile);
  const ao = useTwin((s) => s.ao);
  const worker = profile === "worker";
  const size = model?.bounds.size ?? 60;
  const groundY = (model ? Math.min(...model.floors.map((floor) => floor.elevation_m)) : 0) - 0.3;
  const centre: [number, number, number] = model ? [model.bounds.cx, groundY, -model.bounds.cy] : [0, groundY, 0];
  const select = useTwin((s) => s.select);
  // Adaptive quality: the PerformanceMonitor steps this down when frames drop (pixel ratio, AO quality).
  const [quality, setQuality] = useState(2);
  const dpr = worker ? [1, 1.5][Math.min(quality, 1)] : [1, 1.5, 2][quality];

  return (
    <Canvas
      dpr={dpr}
      camera={{ fov: 38, near: 0.5, far: size * 12, position: [centre[0] + size, size * 0.9, centre[2] + size] }}
      gl={{ antialias: !ao, powerPreference: "high-performance", logarithmicDepthBuffer: false }}
      onPointerMissed={() => select(null)}
      shadows={false}
      style={{ touchAction: "none" }}
    >
      <color attach="background" args={[COLOURS.background]} />
      <fog attach="fog" args={[COLOURS.background, size * 6, size * 16]} />
      <hemisphereLight args={["#e8f0fa", "#0b1e3a", 1.1]} />
      <directionalLight position={[centre[0] + size * 0.6, size * 1.2, centre[2] + size * 0.4]} intensity={1.25} color="#fdfdff" />
      <directionalLight position={[centre[0] - size * 0.8, size * 0.5, centre[2] - size * 0.6]} intensity={0.35} color="#bcd3f0" />
      <PerformanceMonitor
        flipflops={4}
        bounds={() => [40, 58]}
        onDecline={() => setQuality((q) => Math.max(0, q - 1))}
        onIncline={() => setQuality((q) => Math.min(2, q + 1))}
      />
      <mesh rotation-x={-Math.PI / 2} position={[centre[0], groundY, centre[2]]} renderOrder={-1}>
        <planeGeometry args={[size * 12, size * 12]} />
        <meshBasicMaterial color={COLOURS.ground} />
      </mesh>
      <Grid
        position={[centre[0], groundY + 0.02, centre[2]]}
        args={[size * 6, size * 6]}
        cellSize={2}
        cellThickness={0.6}
        cellColor="#1a3864"
        sectionSize={10}
        sectionThickness={1}
        sectionColor="#26507f"
        fadeDistance={size * 3.2}
        fadeStrength={1.2}
        infiniteGrid
        followCamera={false}
      />
      <Stats />
      <Suspense fallback={null}>{model && <Building model={model} />}</Suspense>
      {!worker && (
        <GizmoHelper alignment="bottom-right" margin={[72, 72]} renderPriority={2}>
          <GizmoViewcube color="#17345f" hoverColor="#2b5a95" textColor="#dbe7f5" strokeColor="#5eead4" opacity={0.92} faces={["E", "W", "Top", "Bottom", "N", "S"]} />
        </GizmoHelper>
      )}
      {ao && !worker && (
        <EffectComposer multisampling={0} enableNormalPass={false}>
          <N8AO aoRadius={2.2} intensity={2.4} distanceFalloff={1.2} quality={quality === 2 ? "medium" : "low"} halfRes color={new THREE.Color("#061227")} />
          <SMAA />
          <Vignette eskil={false} offset={0.25} darkness={0.32} />
        </EffectComposer>
      )}
    </Canvas>
  );
}
