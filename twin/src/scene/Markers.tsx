// Everything the state adds to the building: "You are here", disruptions (red circles, area grows with the
// count), added / moved / removed things, highlights (finds) and the selection. Never colour alone: each
// marker also has a shape (ring, "!" badge, box, dashed ghost) and, unless reduced motion, movement.

import { useMemo, useRef } from "react";
import * as THREE from "three";
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import type { BuildingState, Point } from "../api/types";
import type { BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import type { Highlight, Selection } from "../store";
import { outlineGeometry, polygonGeometry } from "./geometry";
import { HereDot, TapPin } from "./HerePin";
import { BADGE_GAP_PX, END_RING_PX, ScreenSized } from "./markerLayout";
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

interface Disruption {
  floor_id: string;
  point: Point;
  names: string[];
}

function clusterDisruptions(model: BuildingModel, closed: string[]): Disruption[] {
  const items: Disruption[] = [];
  for (const id of closed) {
    const space = model.spaceById.get(id);
    const opening = model.openingById.get(id);
    const connector = model.connectorById.get(id);
    if (space) items.push({ floor_id: space.floor_id, point: space.anchor, names: [space.name || space.id] });
    else if (opening) items.push({ floor_id: opening.floor_id, point: opening.position, names: [`Door ${opening.id.split("-").pop()}`] });
    else if (connector) {
      for (const spaceId of connector.space_ids) {
        const stop = model.spaceById.get(spaceId);
        if (stop) items.push({ floor_id: stop.floor_id, point: stop.anchor, names: [connector.name] });
      }
    }
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

export function Pulse({ children, reducedMotion, speed = 1.6, amount = 0.12 }: { children: React.ReactNode; reducedMotion: boolean; speed?: number; amount?: number }) {
  const group = useRef<THREE.Group>(null);
  useFrame(({ clock, invalidate }) => {
    if (!group.current || reducedMotion) return;
    invalidate();
    const s = 1 + amount * (0.5 + 0.5 * Math.sin(clock.elapsedTime * speed * Math.PI));
    group.current.scale.set(s, 1, s);
  });
  return <group ref={group}>{children}</group>;
}

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

export function Markers({ model, state, floorY, visibleFloors, focusedFloorId, highlights, selection, reducedMotion, worker, flat = false }: Props) {
  const hereColour = flat ? COLOURS.mapBlue : COLOURS.here;
  const disruptions = useMemo(() => clusterDisruptions(model, state?.closed ?? []), [model, state?.closed]);
  const at = (floorId: string, point: Point): [number, number, number] => [point[0], floorY(floorId), -point[1]];
  const shown = (floorId: string) => visibleFloors.has(floorId);
  const chip = (text: string, kind: string) => (
    <Html center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
      <div className={`chip chip-${kind}`}>{text}</div>
    </Html>
  );

  const position = state?.position;
  const guide = state?.guide;
  const added = state?.added_assets ?? {};
  const moved = state?.moved_assets ?? {};
  const removed = state?.removed_assets ?? [];

  return (
    <group>
      {/* You are here (draggable) and the pin of the last floor tap */}
      <HereDot model={model} floorY={floorY} visibleFloors={visibleFloors} flat={flat} reducedMotion={reducedMotion} colour={hereColour} />
      <TapPin model={model} floorY={floorY} visibleFloors={visibleFloors} flat={flat} />

      {/* floor changes of the route: where to go up or down (needed in 2D and single-floor views) */}
      {state?.route?.ok &&
        state.route.floor_changes?.map((change, index) => {
          const fromFloor = model.floorById.get(change.from_floor);
          const toFloor = model.floorById.get(change.to_floor);
          const arrow = change.direction === "up" ? "↑" : "↓";
          return (
            <group key={`fc-${index}`}>
              {shown(change.from_floor) && (
                <group position={at(change.from_floor, change.from_point)}>
                  <Ring radius={0.9} colour={COLOURS.route} width={0.14} through />
                  <group position-y={1.4}>{chip(`${arrow} ${change.name} to ${toFloor?.name ?? change.to_floor}`, "route")}</group>
                </group>
              )}
              {shown(change.to_floor) && (
                <group position={at(change.to_floor, change.to_point)}>
                  <Ring radius={0.9} colour={COLOURS.route} width={0.14} through />
                  <group position-y={1.4}>{chip(`from ${fromFloor?.name ?? change.from_floor}`, "route")}</group>
                </group>
              )}
            </group>
          );
        })}

      {/* guide: destination of the current leg */}
      {guide?.active &&
        (() => {
          const target = model.spaceById.get(guide.leg.to_space_id);
          if (!target || !shown(target.floor_id)) return null;
          return (
            <group position={at(target.floor_id, target.anchor)} name="guide-next">
              <ScreenSized>
                <Ring radius={END_RING_PX} colour={COLOURS.route} width={3} through order={30} />
              </ScreenSized>
              <Html center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
                <div className="chip chip-route guide-next" style={{ transform: `translateY(calc(-50% - ${END_RING_PX + BADGE_GAP_PX}px))` }}>
                  Next: {target.name}
                </div>
              </Html>
            </group>
          );
        })()}

      {/* disruptions: red circles, radius ~ sqrt(n), pulsing ring and a "!" badge */}
      {disruptions
        .filter((d) => shown(d.floor_id))
        .map((d, index) => {
          const radius = 1.6 * Math.sqrt(d.names.length) + 0.6;
          const label = d.names.length === 1 ? d.names[0] : `${d.names.length} closed`;
          return (
            <group key={index} position={at(d.floor_id, d.point)}>
              <Disc radius={radius} colour={COLOURS.danger} opacity={0.28} through />
              <Pulse reducedMotion={reducedMotion}>
                <Ring radius={radius} colour={COLOURS.danger} width={0.2} through />
              </Pulse>
              <group position-y={1.6}>{chip(`⚠ ${label}`, "danger")}</group>
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

      {/* highlights (finds etc.) */}
      {Object.entries(highlights).flatMap(([name, highlight]) =>
        highlight.ids.map((id) => {
          const space = model.spaceById.get(id);
          if (space && shown(space.floor_id)) {
            return (
              <group key={`${name}-${id}`} position-y={floorY(space.floor_id)}>
                <SpaceOverlay polygon={space.polygon} height={0.2} colour={highlight.colour} opacity={0.4} outline />
              </group>
            );
          }
          const asset = model.assetById.get(id);
          if (asset && shown(asset.floor_id)) {
            const size = assetSize(asset);
            return (
              <group key={`${name}-${id}`} position={at(asset.floor_id, asset.position)}>
                <Pulse reducedMotion={reducedMotion} speed={1.2} amount={0.2}>
                  <Ring radius={Math.max(size[0], size[2]) * 0.8 + 0.5} colour={highlight.colour} width={0.16} />
                </Pulse>
                <group position-y={size[1] + 0.9}>{chip(asset.name, "accent")}</group>
              </group>
            );
          }
          return null;
        }),
      )}

      {/* selection */}
      {selection &&
        shown(selection.floor_id) &&
        (() => {
          if (selection.kind === "space" || selection.kind === "connector") {
            const space = model.spaceById.get(selection.kind === "space" ? selection.id : selection.space_id ?? "");
            if (!space) return null;
            return (
              <group position-y={floorY(space.floor_id)}>
                <SpaceOverlay polygon={space.polygon} height={0.12} colour={COLOURS.selection} opacity={0.35} outline />
              </group>
            );
          }
          if (selection.kind === "asset") {
            const asset = model.assetById.get(selection.id);
            if (!asset) return null;
            const size = assetSize(asset);
            return (
              <group position={at(asset.floor_id, moved[asset.id]?.position ?? asset.position)}>
                <Ring radius={Math.max(size[0], size[2]) * 0.8 + 0.4} colour={COLOURS.selection} width={0.14} />
              </group>
            );
          }
          return null;
        })()}
      {worker || focusedFloorId ? null : null}
    </group>
  );
}
