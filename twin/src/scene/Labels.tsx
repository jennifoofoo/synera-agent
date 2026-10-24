import { useMemo, useState } from "react";
import * as THREE from "three";
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import type { FloorModel, BuildingModel } from "../model/model";

interface Props {
  floor: FloorModel;
  model: BuildingModel;
  y: number;
  limit: number;
  flat?: boolean;
}

const centre = new THREE.Vector3();
const LABEL_PX = 150; // typical label width on screen
const MIN_ROOM_PX = 56; // a room narrower than this on screen gets no label

/** Drops labels whose anchors sit too close to an already kept one (metres), so they never overlap. */
function cullOverlaps<T extends { anchor: [number, number] }>(items: T[], minDistance: number): T[] {
  const kept: T[] = [];
  for (const item of items) {
    if (kept.every((other) => Math.hypot(other.anchor[0] - item.anchor[0], other.anchor[1] - item.anchor[1]) >= minDistance)) kept.push(item);
  }
  return kept;
}

/** Room names on the focused floor. What is shown depends on the scale (metres per screen pixel): far away only
 * lifts and stairs, closer the rooms that are wide enough to carry a label, never overlapping. */
export function Labels({ floor, model, y, limit, flat = false }: Props) {
  const [scale, setScale] = useState(1); // metres per pixel, quantised so labels only re-flow on real zoom changes
  useFrame(({ camera, size }) => {
    let metresPerPixel: number;
    if ((camera as THREE.OrthographicCamera).isOrthographicCamera) {
      const ortho = camera as THREE.OrthographicCamera;
      metresPerPixel = (ortho.right - ortho.left) / ortho.zoom / Math.max(1, size.width);
    } else {
      const perspective = camera as THREE.PerspectiveCamera;
      centre.set(floor.bounds.cx, y, -floor.bounds.cy);
      const distance = camera.position.distanceTo(centre);
      metresPerPixel = (2 * distance * Math.tan(THREE.MathUtils.degToRad(perspective.fov / 2))) / Math.max(1, size.height);
    }
    const quantised = Math.pow(2, Math.round(Math.log2(Math.max(1e-3, metresPerPixel)) * 2) / 2);
    if (quantised !== scale) setScale(quantised);
  });
  const labelled = useMemo(() => {
    const named = floor.spaces.filter((space) => space.name && space.type !== "outdoor");
    const connectors = named.filter((space) => model.connectorBySpace.has(space.id));
    const lifts = connectors.filter((space) => model.connectorBySpace.get(space.id)?.kind === "lift");
    const minWidth = MIN_ROOM_PX * scale;
    const rooms = named
      .filter((space) => !model.connectorBySpace.has(space.id) && space.type !== "corridor" && Math.sqrt(space.area_m2) >= minWidth)
      .sort((a, b) => b.area_m2 - a.area_m2)
      .slice(0, limit);
    const far = floor.bounds.size / scale < 700; // the whole floor is under ~700 px wide
    const chosen = far ? [...lifts.slice(0, 4), ...rooms.slice(0, 6)] : [...connectors.slice(0, 12), ...rooms];
    return cullOverlaps(chosen, LABEL_PX * scale * (flat ? 0.9 : 1.1));
  }, [floor, model, limit, scale, flat]);
  // 2D: stairs, lifts, toilets and entrances as small round icons like a street map's points of interest.
  const pois = useMemo(() => {
    if (!flat) return [];
    const shownNames = new Set(labelled.map((space) => space.id));
    const items: { id: string; point: [number, number]; glyph: string; title: string }[] = [];
    for (const space of floor.spaces) {
      const connector = model.connectorBySpace.get(space.id);
      if (connector && !shownNames.has(space.id)) items.push({ id: space.id, point: space.anchor, glyph: connector.kind === "lift" ? "⇅" : "⟋", title: space.name });
      else if (space.room_type === "toilet" && Math.sqrt(space.area_m2) >= 24 * scale) items.push({ id: space.id, point: space.anchor, glyph: "WC", title: space.name });
    }
    for (const opening of floor.openings) {
      if (opening.kind === "entrance") items.push({ id: opening.id, point: opening.position, glyph: "⎆", title: "Entrance" });
    }
    return cullOverlaps(items.map((item) => ({ ...item, anchor: item.point })), 26 * scale);
  }, [flat, floor, model, labelled, scale]);
  return (
    <group position-y={y + 0.5}>
      {labelled.map((space) => (
        <Html key={space.id} position={[space.anchor[0], 0, -space.anchor[1]]} center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
          <div className={`label ${flat ? "label-plan" : ""} ${model.connectorBySpace.has(space.id) ? "label-connector" : ""}`}>{space.name}</div>
        </Html>
      ))}
      {pois.map((poi) => (
        <Html key={`poi-${poi.id}`} position={[poi.point[0], 0, -poi.point[1]]} center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
          <div className="poi" title={poi.title}>{poi.glyph}</div>
        </Html>
      ))}
    </group>
  );
}
