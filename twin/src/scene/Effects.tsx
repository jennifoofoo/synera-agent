import * as THREE from "three";
import { EffectComposer, N8AO, SMAA, Vignette } from "@react-three/postprocessing";
import { COLOURS } from "../model/palette";

/** Planner-only effects: ambient occlusion (N8AO), anti-aliasing, a weak vignette. No DoF, no chromatic aberration. */
export default function Effects({ quality }: { quality: number }) {
  return (
    <EffectComposer multisampling={0} enableNormalPass={false}>
      <N8AO aoRadius={2.2} intensity={1.8} distanceFalloff={1.2} quality={quality === 2 ? "medium" : "low"} halfRes color={new THREE.Color(COLOURS.edge)} />
      <SMAA />
      <Vignette eskil={false} offset={0.3} darkness={0.22} />
    </EffectComposer>
  );
}
