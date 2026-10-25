import { useEffect, useRef } from "react";
import * as THREE from "three";
import { useThree } from "@react-three/fiber";
import { EffectComposer, N8AO, SMAA, Vignette } from "@react-three/postprocessing";
import type { EffectComposer as EffectComposerImpl } from "postprocessing";
import { COLOURS } from "../model/palette";

/** Planner-only effects: ambient occlusion (N8AO), anti-aliasing, a weak vignette. No DoF, no chromatic aberration. */
export default function Effects({ quality }: { quality: number }) {
  const composer = useRef<EffectComposerImpl>(null);
  const size = useThree((s) => s.size);
  const dpr = useThree((s) => s.viewport.dpr);
  // @react-three/postprocessing resizes the composer only when the CSS size changes. The PerformanceMonitor lowers
  // the pixel ratio at the same CSS size, so the buffers (and N8AO's targets) kept the old, larger size and the AO
  // pass drew a blurred, enlarged copy of the building ("ghost") into the upper right. Resize on every dpr change.
  useEffect(() => {
    composer.current?.setSize(size.width, size.height);
  }, [dpr, size]);
  useEffect(() => {
    (window as unknown as { __twinComposer: unknown }).__twinComposer = composer.current;
  });
  return (
    <EffectComposer ref={composer} multisampling={0} enableNormalPass={false}>
      <N8AO aoRadius={1.0} intensity={0.8} distanceFalloff={1.0} quality={quality === 2 ? "medium" : "low"} halfRes color={new THREE.Color(COLOURS.aoTint)} />
      <SMAA />
      <Vignette eskil={false} offset={0.35} darkness={0.1} />
    </EffectComposer>
  );
}
