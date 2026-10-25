import { useMemo } from "react";
import * as THREE from "three";
import { COLOURS } from "../model/palette";

interface Props {
  centre: [number, number, number];
  /** Radius (m) of the ground disc: the gradient reaches the outer paper tone there, the dots are gone long before. */
  radius: number;
  cell?: number;
}

const vertex = /* glsl */ `
  varying vec2 vXZ;
  void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    vXZ = world.xz;
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

// A calm ground: a soft radial gradient (lighter under the building), a faint contact shadow blob around it, and a
// dot lattice at the cell corners that fades out by pixel footprint (no moire at shallow angles) and by distance.
// No lines: the building is the only thing with edges.
const fragment = /* glsl */ `
  varying vec2 vXZ;
  uniform vec2 uCentre;
  uniform float uRadius;
  uniform float uCell;
  uniform float uShadow0;
  uniform float uShadow1;
  uniform vec3 uInner;
  uniform vec3 uOuter;
  uniform vec3 uDot;

  void main() {
    float d = distance(vXZ, uCentre);
    vec3 colour = mix(uInner, uOuter, smoothstep(0.0, uRadius * 0.55, d));
    float shadow = (1.0 - smoothstep(uShadow0, uShadow1, d)) * 0.07;
    colour *= 1.0 - shadow;
    vec2 r = vXZ / uCell;
    vec2 cell = fract(r) - 0.5;
    vec2 fwv = fwidth(r);
    float fw = max(max(fwv.x, fwv.y), 1e-5);
    float px = length(cell) / fw;
    float dot = (1.0 - smoothstep(1.2, 2.0, px)) * (1.0 - smoothstep(0.12, 0.3, fw)) * (1.0 - smoothstep(uRadius * 0.2, uRadius * 0.5, d));
    colour = mix(colour, uDot, dot * 0.28);
    gl_FragColor = vec4(colour, 1.0);
  }
`;

/** The finite ground around the building: a gradient disc with a faint dot lattice, nothing far away to alias. */
export function GroundGrid({ centre, radius, cell = 2 }: Props) {
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: vertex,
        fragmentShader: fragment,
        transparent: false,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -2,
        polygonOffsetUnits: -2,
        uniforms: {
          uCentre: { value: new THREE.Vector2() },
          uRadius: { value: 1 },
          uCell: { value: cell },
          uShadow0: { value: 1 },
          uShadow1: { value: 2 },
          uInner: { value: new THREE.Color(COLOURS.groundInner) },
          uOuter: { value: new THREE.Color(COLOURS.groundOuter) },
          uDot: { value: new THREE.Color(COLOURS.dot) },
        },
      }),
    [cell],
  );
  material.uniforms.uCentre.value.set(centre[0], centre[2]);
  material.uniforms.uRadius.value = radius;
  material.uniforms.uShadow0.value = radius * 0.25;
  material.uniforms.uShadow1.value = radius * 0.5;
  return (
    <mesh position={[centre[0], centre[1] + 0.03, centre[2]]} rotation-x={-Math.PI / 2} material={material} renderOrder={-0.5} frustumCulled={false}>
      <planeGeometry args={[radius * 2, radius * 2]} />
    </mesh>
  );
}
