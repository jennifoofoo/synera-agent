import { useMemo } from "react";
import * as THREE from "three";

interface Props {
  centre: [number, number, number];
  /** Radius (m) where the grid has faded out completely, measured from the centre. */
  radius: number;
  cell?: number;
  section?: number;
}

const vertex = /* glsl */ `
  varying vec2 vXZ;
  void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    vXZ = world.xz;
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

// Anti-aliased lines that fade out by themselves once a cell gets smaller than a few pixels. That is what removes
// the moire (thousands of dashes and dots) the infinite shader grid produced at shallow camera angles.
const fragment = /* glsl */ `
  varying vec2 vXZ;
  uniform vec2 uCentre;
  uniform float uRadius;
  uniform float uCell;
  uniform float uSection;
  uniform vec3 uCellColour;
  uniform vec3 uSectionColour;

  float gridLine(vec2 p, float size, out float footprint) {
    vec2 r = p / size;
    vec2 d = max(fwidth(r), vec2(1e-5));
    vec2 g = abs(fract(r - 0.5) - 0.5) / d;
    footprint = max(d.x, d.y);
    return 1.0 - min(min(g.x, g.y), 1.0);
  }

  void main() {
    float fc;
    float fs;
    float cell = gridLine(vXZ, uCell, fc) * (1.0 - smoothstep(0.12, 0.3, fc));
    float section = gridLine(vXZ, uSection, fs) * (1.0 - smoothstep(0.12, 0.3, fs));
    float radial = 1.0 - smoothstep(uRadius * 0.35, uRadius, distance(vXZ, uCentre));
    float a = max(cell * 0.45, section * 0.7) * radial;
    if (a < 0.003) discard;
    vec3 colour = mix(uCellColour, uSectionColour, step(cell * 0.45, section * 0.7));
    gl_FragColor = vec4(colour, a);
  }
`;

/** A finite ground grid around the building: no infinite plane, so nothing far away to alias. */
export function GroundGrid({ centre, radius, cell = 2, section = 10 }: Props) {
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: vertex,
        fragmentShader: fragment,
        transparent: true,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -2,
        polygonOffsetUnits: -2,
        uniforms: {
          uCentre: { value: new THREE.Vector2() },
          uRadius: { value: 1 },
          uCell: { value: cell },
          uSection: { value: section },
          uCellColour: { value: new THREE.Color("#c3d1e2") },
          uSectionColour: { value: new THREE.Color("#a9bdd5") },
        },
      }),
    [cell, section],
  );
  material.uniforms.uCentre.value.set(centre[0], centre[2]);
  material.uniforms.uRadius.value = radius;
  return (
    <mesh position={[centre[0], centre[1] + 0.03, centre[2]]} rotation-x={-Math.PI / 2} material={material} renderOrder={-0.5} frustumCulled={false}>
      <planeGeometry args={[radius * 2, radius * 2]} />
    </mesh>
  );
}
