// Everything the state adds to the building: "You are here", disruptions (red circles, area grows with the
// count), added / moved / removed things, highlights (finds) and the selection. Never colour alone: each
// marker also has a shape (ring, "!" badge, box, dashed ghost) and, unless reduced motion, movement.

import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { Html, Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import type { BuildingState, Point } from "../api/types";
import type { BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { closedConnectorStops } from "../model/closures";
import type { Highlight, Selection } from "../store";
import { openingEditsOf, outlineGeometry, polygonGeometry, wallTopOutline, withCutaway } from "./geometry";
import { cutawayUniforms } from "./FloorMesh";
import { HereDot, TapPin } from "./HerePin";
import { ClosedGlyph } from "./Labels";
import { Pulse, PulseFew } from "./markerLayout";
import { FloorBadge } from "./poiIcons";
import { assetSize } from "./Things";

interface Props {
  model: BuildingModel;
  state: BuildingState | null;
  floorY: (floorId: string) => number;
  visibleFloors: Set<string>;
  focusedFloorId: string | null;
  highlights: Record<string, Highlight>;
  selection: Selection | null;
  reducedMotion: boolean;
  worker: boolean;
  flat?: boolean;
}

export interface Disruption {
  floor_id: string;
  point: Point;
  names: string[];
}

/** Closed rooms and doors (red disc and chip). Closed lifts and stairs are not in here: their own glyph, a hatched
 * fill and a "Closed" tag mark them (ClosedFill below, Labels.tsx; model/closures.ts). */
export function clusterDisruptions(model: BuildingModel, closed: string[]): Disruption[] {
  const items: Disruption[] = [];
  for (const id of closed) {
    if (model.connectorById.has(id) || model.connectorBySpace.has(id)) continue;
    const space = model.spaceById.get(id);
    const opening = model.openingById.get(id);
    if (space) items.push({ floor_id: space.floor_id, point: space.anchor, names: [space.name || space.id] });
    else if (opening) items.push({ floor_id: opening.floor_id, point: opening.position, names: [`Door ${opening.id.split("-").pop()}`] });
  }
  const clusters: Disruption[] = [];
  for (const item of items) {
    const near = clusters.find(
      (c) => c.floor_id === item.floor_id && Math.hypot(c.point[0] - item.point[0], c.point[1] - item.point[1]) < 10,
    );
    if (near) {
      near.names.push(...item.names);
      near.point = [(near.point[0] * (near.names.length - 1) + item.point[0]) / near.names.length, (near.point[1] * (near.names.length - 1) + item.point[1]) / near.names.length];
    } else clusters.push({ ...item, names: [...item.names] });
  }
  return clusters;
}

export { Pulse };

export function Ring({ radius, colour, width = 0.18, y = 0.06, opacity = 1, through = false, order }: { radius: number; colour: string; width?: number; y?: number; opacity?: number; through?: boolean; order?: number }) {
  return (
    <mesh rotation-x={-Math.PI / 2} position-y={y} renderOrder={order ?? (through ? 19 : 15)}>
      <ringGeometry args={[Math.max(0.05, radius - width), radius, 48]} />
      <meshBasicMaterial color={colour} transparent opacity={opacity} depthWrite={false} depthTest={!through} side={THREE.DoubleSide} />
    </mesh>
  );
}

export function Disc({ radius, colour, y = 0.05, opacity = 0.22, through = false, order }: { radius: number; colour: string; y?: number; opacity?: number; through?: boolean; order?: number }) {
  return (
    <mesh rotation-x={-Math.PI / 2} position-y={y} renderOrder={order ?? (through ? 18 : 14)}>
      <circleGeometry args={[radius, 48]} />
      <meshBasicMaterial color={colour} transparent opacity={opacity} depthWrite={false} depthTest={!through} side={THREE.DoubleSide} />
    </mesh>
  );
}

// Pale red hatching in world metres (stripes at 45°, every HATCH_M), anti-aliased; when the stripes get finer than a
// pixel they fade into their mean colour, so the far tiers show a calm pale red tint instead of moiré.
const HATCH_M = 0.7;
const hatchVertex = `
  varying vec3 vWorld;
  void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    vWorld = world.xyz;
    gl_Position = projectionMatrix * viewMatrix * world;
  }`;
const hatchFragment = `
  uniform vec3 tint;
  uniform vec3 stripe;
  uniform float spacing;
  uniform float opacity;
  varying vec3 vWorld;
  void main() {
    float u = (vWorld.x + vWorld.z) / spacing;
    float fw = max(fwidth(u), 1e-4);
    float d = abs(fract(u) - 0.5);
    float half_ = 0.18;
    float line = 1.0 - smoothstep(half_ - fw, half_ + fw, d);
    line = mix(line, 2.0 * half_, clamp(fw * 2.0 - 0.5, 0.0, 1.0));
    gl_FragColor = vec4(mix(tint, stripe, line * 0.6), opacity);
  }`;

/** A closed lift or stair stop: its slab gets the pale red hatching instead of the stairs-and-lifts violet. */
function ClosedFill({ polygon, spaceId }: { polygon: Point[]; spaceId: string }) {
  const geometry = useMemo(() => polygonGeometry(polygon, 0.1), [polygon]);
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: hatchVertex,
        fragmentShader: hatchFragment,
        uniforms: {
          tint: { value: new THREE.Color("#f4dfdb") },
          stripe: { value: new THREE.Color(COLOURS.danger) },
          spacing: { value: HATCH_M },
          opacity: { value: 0.92 },
        },
        transparent: true,
        depthWrite: false,
      }),
    [],
  );
  return (
    <group name="closed-fill" userData={{ count: 1, space: spaceId }}>
      <mesh geometry={geometry} material={material} position-y={0.03} renderOrder={12} />
    </group>
  );
}

function SpaceOverlay({ polygon, height, colour, opacity, outline }: { polygon: Point[]; height: number; colour: string; opacity: number; outline: boolean }) {
  const geometry = useMemo(() => polygonGeometry(polygon, height), [polygon, height]);
  const edges = useMemo(() => outlineGeometry(polygon, height + 0.02), [polygon, height]);
  return (
    <group>
      <mesh geometry={geometry} position-y={0.03} renderOrder={12}>
        <meshBasicMaterial color={colour} transparent opacity={opacity} depthWrite={false} />
      </mesh>
      {outline && (
        <lineSegments geometry={edges} position-y={0.03} renderOrder={13}>
          <lineBasicMaterial color={colour} depthTest={false} />
        </lineSegments>
      )}
    </group>
  );
}

/** The selected room in 3D: its wall tops painted in the selection colour (the band follows the dollhouse cutaway
 * and runs over the floor across door gaps, geometry.ts wallTopOutline) over a light tint of its floor. */
function WallTopSelection({ model, spaceId, state }: { model: BuildingModel; spaceId: string; state: BuildingState | null }) {
  const space = model.spaceById.get(spaceId);
  const floor = space ? model.floorById.get(space.floor_id) : undefined;
  const editsKey = JSON.stringify(openingEditsOf(state));
  const band = useMemo(() => (floor ? wallTopOutline(floor, spaceId, JSON.parse(editsKey)) : null), [floor, spaceId, editsKey]);
  const material = useMemo(
    () =>
      withCutaway(
        new THREE.MeshBasicMaterial({ color: COLOURS.selection, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4 }),
        cutawayUniforms,
      ),
    [],
  );
  useEffect(() => () => band?.dispose(), [band]);
  useEffect(() => () => material.dispose(), [material]);
  if (!space || !band) return null;
  return (
    <group name="selection-room">
      <SpaceOverlay polygon={space.polygon} height={0.12} colour={COLOURS.selection} opacity={0.12} outline={false} />
      <mesh name="selection-walls" geometry={band} material={material} renderOrder={13} />
    </group>
  );
}

/** Closed rooms (not lifts or stairs: their stops get the hatched fill), for the red tint of the whole room. */
export function closedSpaces(model: BuildingModel, closed: string[]): { id: string; floor_id: string; polygon: Point[] }[] {
  const spaces: { id: string; floor_id: string; polygon: Point[] }[] = [];
  for (const id of closed) {
    if (model.connectorById.has(id) || model.connectorBySpace.has(id)) continue;
    const space = model.spaceById.get(id);
    if (space) spaces.push({ id: space.id, floor_id: space.floor_id, polygon: space.polygon });
  }
  return spaces;
}

/** Found things (3D) with a ring and a name: the nearest this many, the rest are a small dot. */
const FOUND_NAMED = 5;

export function Markers({ model, state, floorY, visibleFloors, focusedFloorId, highlights, selection, reducedMotion, worker, flat = false }: Props) {
  const hereColour = COLOURS.here;
  const disruptions = useMemo(() => clusterDisruptions(model, state?.closed ?? []), [model, state?.closed]);
  const closedRooms = useMemo(() => closedSpaces(model, state?.closed ?? []), [model, state?.closed]);
  const closedStops = useMemo(() => closedConnectorStops(model, state?.closed ?? []), [model, state?.closed]);
  const at = (floorId: string, point: Point): [number, number, number] => [point[0], floorY(floorId), -point[1]];
  const shown = (floorId: string) => visibleFloors.has(floorId);
  // Finds with many hits stay calm: only the nearest few get a ring and a name, the rest a small dot.
  const position = state?.position ?? null;
  const namedFinds = useMemo(() => {
    const named = new Set<string>();
    for (const highlight of Object.values(highlights)) {
      const assets = highlight.ids.map((id) => model.assetById.get(id)).filter((asset): asset is NonNullable<typeof asset> => !!asset);
      const from = position?.point ? { floor: position.floor_id, point: position.point } : assets[0] ? { floor: assets[0].floor_id, point: assets[0].position } : null;
      const away = (asset: (typeof assets)[number]) =>
        from ? Math.hypot(asset.position[0] - from.point[0], asset.position[1] - from.point[1]) + (asset.floor_id === from.floor ? 0 : 1e4) : 0;
      for (const asset of [...assets].sort((a, b) => away(a) - away(b)).slice(0, FOUND_NAMED)) named.add(asset.id);
    }
    return named;
  }, [highlights, model, position?.floor_id, position?.point]);
  const destination = state?.route?.ok ? state.route.destination : null;
  const chip = (text: string, kind: string) => (
    <Html center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
      <div className={`chip chip-${kind}`}>{text}</div>
    </Html>
  );

  const added = state?.added_assets ?? {};
  const moved = state?.moved_assets ?? {};
  const removed = state?.removed_assets ?? [];

  return (
    <group>
      {/* You are here (draggable) and the pin of the last floor tap */}
      <HereDot model={model} floorY={floorY} visibleFloors={visibleFloors} flat={flat} reducedMotion={reducedMotion} worker={worker} colour={hereColour} />
      <TapPin model={model} floorY={floorY} visibleFloors={visibleFloors} flat={flat} />

      {/* floor changes of the route in 3D: one small "↑ 1" badge where to go up or down (2D: Labels.tsx lays it out) */}
      {!flat &&
        state?.route?.ok &&
        state.route.floor_changes?.map((change, index) =>
          shown(change.from_floor) ? (
            <group key={`fc-${index}`} position={at(change.from_floor, change.from_point)}>
              <Html center position-y={1.4} zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
                <FloorBadge
                  kind={change.kind === "lift" ? "lift" : "stairs"}
                  direction={change.direction}
                  level={model.floorById.get(change.to_floor)?.level ?? 0}
                  title={`${change.name} ${change.direction} to ${model.floorById.get(change.to_floor)?.name ?? change.to_floor}`}
                />
              </Html>
            </group>
          ) : null,
        )}

      {/* closures: a closed room gets a red tint with an outline ... */}
      {closedRooms
        .filter((room) => shown(room.floor_id))
        .map((room) => (
          <group key={room.id} name="closed-room" position-y={floorY(room.floor_id)}>
            <SpaceOverlay polygon={room.polygon} height={0.12} colour={COLOURS.danger} opacity={0.1} outline />
          </group>
        ))}
      {/* ... and a small flat disc with a "Closed · name" badge on the spot (2D: Labels.tsx lays the badge out) */}
      {disruptions
        .filter((d) => shown(d.floor_id))
        .map((d, index) => {
          const label = d.names.length === 1 ? `Closed · ${d.names[0]}` : `${d.names.length} closed`;
          return (
            <group key={index} name="closed-marker" userData={{ count: d.names.length }} position={at(d.floor_id, d.point)}>
              <Disc radius={0.9} colour={COLOURS.danger} opacity={0.14} through />
              {!flat && (
                <group position-y={1.6}>
                  <Html center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
                    <div className="chip chip-danger chip-closed">
                      <ClosedGlyph />
                      {label}
                    </div>
                  </Html>
                </group>
              )}
            </group>
          );
        })}

      {/* closed lifts and stairs: pale red hatching on their slab (2D and 3D); in 2D the glyph and tag come from
          Labels.tsx, in 3D (no POI glyphs there) a "Closed · name" badge floats above the stop */}
      {[...closedStops.entries()].map(([spaceId, name]) => {
        const space = model.spaceById.get(spaceId);
        if (!space || !shown(space.floor_id)) return null;
        return (
          <group key={`closed-fill-${spaceId}`} position-y={floorY(space.floor_id)}>
            <ClosedFill polygon={space.polygon} spaceId={spaceId} />
            {!flat && (
              <group position={[space.anchor[0], 1.6, -space.anchor[1]]}>
                <Html center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
                  <div className="chip chip-danger chip-closed">
                    <ClosedGlyph />
                    {`Closed · ${name}`}
                  </div>
                </Html>
              </group>
            )}
          </group>
        );
      })}

      {/* added things: green box with a halo */}
      {Object.entries(added)
        .filter(([, edit]) => shown(edit.floor_id))
        .map(([id, edit]) => {
          const size = assetSize({ id, name: edit.name, type: edit.type ?? "", category: edit.category ?? "equipment", space_id: edit.space_id, floor_id: edit.floor_id, position: edit.position, footprint: null });
          return (
            <group key={id} position={at(edit.floor_id, edit.position)} rotation-y={THREE.MathUtils.degToRad(edit.rotation_deg ?? 0)}>
              <mesh position-y={size[1] / 2}>
                <boxGeometry args={size} />
                <meshStandardMaterial color={COLOURS.added} roughness={0.7} />
              </mesh>
              <Ring radius={Math.max(size[0], size[2]) * 0.9 + 0.3} colour={COLOURS.added} />
              <group position-y={size[1] + 0.9}>{chip(`+ ${edit.name}`, "ok")}</group>
            </group>
          );
        })}

      {/* moved things: dashed ghost ring at the old place */}
      {Object.keys(moved).map((id) => {
        const asset = model.assetById.get(id);
        if (!asset || !shown(asset.floor_id) || added[id]) return null;
        return (
          <group key={`moved-${id}`} position={at(asset.floor_id, asset.position)}>
            <Ring radius={0.7} colour={COLOURS.removed} width={0.1} opacity={0.7} />
            <group position-y={1.2}>{chip(`${asset.name} moved`, "muted")}</group>
          </group>
        );
      })}

      {/* removed things: grey ghost */}
      {removed.map((id) => {
        const asset = model.assetById.get(id);
        if (!asset || !shown(asset.floor_id)) return null;
        const size = assetSize(asset);
        return (
          <group key={`removed-${id}`} position={at(asset.floor_id, asset.position)}>
            <mesh position-y={size[1] / 2}>
              <boxGeometry args={size} />
              <meshBasicMaterial color={COLOURS.removed} transparent opacity={0.25} wireframe />
            </mesh>
            <group position-y={size[1] + 0.7}>{chip(`${asset.name} removed`, "muted")}</group>
          </group>
        );
      })}

      {/* highlights (finds etc.); found things in 2D are dots laid out by Labels.tsx, collision-free */}
      {Object.entries(highlights).flatMap(([name, highlight]) =>
        highlight.ids.map((id) => {
          const space = model.spaceById.get(id);
          // the route's destination is blue already: no second tint on top
          if (space && shown(space.floor_id) && space.id !== destination) {
            return (
              <group key={`${name}-${id}`} position-y={floorY(space.floor_id)}>
                <SpaceOverlay polygon={space.polygon} height={0.2} colour={highlight.colour} opacity={0.4} outline />
              </group>
            );
          }
          const asset = model.assetById.get(id);
          if (asset && shown(asset.floor_id) && !flat) {
            const size = assetSize(asset);
            if (!namedFinds.has(id)) {
              return (
                <group key={`${name}-${id}`} position={at(asset.floor_id, asset.position)}>
                  <Disc radius={0.28} colour={highlight.colour} opacity={0.85} y={size[1] + 0.05} />
                </group>
              );
            }
            return (
              <group key={`${name}-${id}`} position={at(asset.floor_id, asset.position)}>
                <PulseFew reducedMotion={reducedMotion} times={3} speed={1.2} amount={0.2}>
                  <Ring radius={Math.max(size[0], size[2]) * 0.6 + 0.35} colour={highlight.colour} width={0.12} />
                </PulseFew>
                <group position-y={size[1] + 0.9}>{chip(asset.name, "accent")}</group>
              </group>
            );
          }
          return null;
        }),
      )}

      {/* focus mode: the destination room of a shown route gets a signal edge and a light tint */}
      {state?.route?.ok &&
        state.route.destination &&
        (() => {
          const space = model.spaceById.get(state.route.destination);
          if (!space || !shown(space.floor_id)) return null;
          return (
            <group name="route-destination-room" position-y={floorY(space.floor_id)}>
              {/* with a route the destination is the answer: a saturated blue body (walls and floor), like a model
                  with one painted room; without a route nothing is blue */}
              <SpaceOverlay polygon={space.polygon} height={flat ? 0.12 : 1.25} colour={COLOURS.signal} opacity={flat ? 0.22 : 0.32} outline />
            </group>
          );
        })()}

      {/* selection */}
      {selection &&
        shown(selection.floor_id) &&
        (() => {
          if (selection.kind === "space" || selection.kind === "connector") {
            const space = model.spaceById.get(selection.kind === "space" ? selection.id : selection.space_id ?? "");
            if (!space) return null;
            return (
              <group position-y={floorY(space.floor_id)}>
                {flat ? (
                  <SpaceOverlay polygon={space.polygon} height={0.12} colour={COLOURS.selection} opacity={0.12} outline />
                ) : (
                  <WallTopSelection model={model} spaceId={space.id} state={state} />
                )}
              </group>
            );
          }
          if (selection.kind === "asset") {
            const asset = model.assetById.get(selection.id);
            if (!asset) return null;
            const size = assetSize(asset);
            // A tight outline of the footprint (rotated like the thing, 0.15 m padding); walls hide it in 3D.
            const rotation = moved[asset.id]?.rotation_deg ?? asset.footprint?.rotation_deg ?? 0;
            const [hw, hd, y] = [size[0] / 2 + 0.15, size[2] / 2 + 0.15, 0.06];
            return (
              <group position={at(asset.floor_id, moved[asset.id]?.position ?? asset.position)} rotation-y={THREE.MathUtils.degToRad(rotation)}>
                <Line
                  name="asset-selection"
                  points={[[-hw, y, -hd], [hw, y, -hd], [hw, y, hd], [-hw, y, hd], [-hw, y, -hd]]}
                  color={COLOURS.selection}
                  lineWidth={3}
                  depthTest={!flat}
                  depthWrite={false}
                  renderOrder={16}
                />
              </group>
            );
          }
          return null;
        })()}
      {worker || focusedFloorId ? null : null}
    </group>
  );
}
