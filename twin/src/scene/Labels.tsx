import { useMemo, useState } from "react";
import * as THREE from "three";
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import type { Point } from "../api/types";
import type { FloorModel, BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { LABEL_LIFT } from "./markerLayout";
import { LIFT as ROUTE_LIFT } from "./RouteLine";

interface Props {
  floor: FloorModel;
  model: BuildingModel;
  y: number;
  limit: number;
  flat?: boolean;
}

const centre = new THREE.Vector3();

/** Tabler Icons "door-exit" (MIT, https://tabler.io/icons): a door with an arrow out. */
const EXIT_ICON = (
  <svg viewBox="0 0 24 24" aria-hidden>
    <path d="M13 12v.01" />
    <path d="M3 21h18" />
    <path d="M5 21v-16a2 2 0 0 1 2 -2h7.5m2.5 10.5v7.5" />
    <path d="M14 7h7m-3 -3l3 3l-3 3" />
  </svg>
);
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
  // Rooms with a marker (you are here, route ends, the guide's next target): their label moves just above the
  // marker (screen px), so the marker never covers the name. Other labels stay at the room anchor.
  const state = useTwin((s) => s.state);
  const marks = useMemo(() => {
    const out = new Map<string, { point: Point; lift: number; height: number }>();
    const put = (spaceId: string | undefined | null, point: Point | null | undefined, lift: number, height = 0) => {
      const space = spaceId ? model.spaceById.get(spaceId) : undefined;
      if (!space || space.floor_id !== floor.id || !point) return;
      const known = out.get(space.id);
      if (!known || known.lift < lift) out.set(space.id, { point, lift, height });
    };
    const route = state?.route;
    if (route?.ok && route.segments?.length) {
      const first = route.segments[0];
      const last = route.segments[route.segments.length - 1];
      if (first.floor_id === floor.id) put(route.start, first.points[0], LABEL_LIFT.end, ROUTE_LIFT);
      if (last.floor_id === floor.id) put(route.destination, last.points[last.points.length - 1], LABEL_LIFT.end, ROUTE_LIFT);
    }
    const guide = state?.guide;
    if (guide?.active) put(guide.leg.to_space_id, model.spaceById.get(guide.leg.to_space_id)?.anchor, LABEL_LIFT.guide);
    const here = state?.position;
    if (here) put(here.space_id, here.point ?? model.spaceById.get(here.space_id)?.anchor, LABEL_LIFT.here);
    return out;
  }, [state?.route, state?.guide, state?.position, model, floor.id]);
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
    // Marked rooms always keep their label (they stack above their own markers, so they are never culled);
    // the other labels keep clear of them.
    const marked = named.filter((space) => marks.has(space.id));
    const rest = chosen.filter((space) => !marks.has(space.id));
    const minDistance = LABEL_PX * scale * (flat ? 0.9 : 1.1);
    const kept = cullOverlaps(rest, minDistance);
    return [
      ...marked,
      ...kept.filter((space) => marked.every((other) => Math.hypot(other.anchor[0] - space.anchor[0], other.anchor[1] - space.anchor[1]) >= minDistance)),
    ];
  }, [floor, model, limit, scale, flat, marks]);
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
      if (opening.kind === "entrance") items.push({ id: opening.id, point: opening.position, glyph: "exit", title: opening.step_free === false ? "Entrance / exit (not step-free)" : "Entrance / exit" });
      else if (opening.step_free === false) items.push({ id: opening.id, point: opening.position, glyph: "⌇", title: "Not step-free (a step or threshold)" });
    }
    // Icons keep clear of each other and of the text labels (which win).
    const taken = labelled.map((space) => ({ anchor: space.anchor, id: "", point: space.anchor, glyph: "", title: "" }));
    return cullOverlaps([...taken, ...items.map((item) => ({ ...item, anchor: item.point }))], 26 * scale).filter((item) => item.id);
  }, [flat, floor, model, labelled, scale]);
  return (
    <group position-y={y + 0.5}>
      {labelled.map((space) => {
        const mark = marks.get(space.id);
        const where = mark?.point ?? space.anchor;
        return (
          <Html
            key={space.id}
            position={[where[0], mark ? mark.height - 0.5 : 0, -where[1]]} // at the marker's own height
            center
            zIndexRange={[2, 0]}
            style={{ pointerEvents: "none" }}
          >
            <div
              className={`label label-halo ${flat ? "label-plan" : ""} ${model.connectorBySpace.has(space.id) ? "label-connector" : ""}`}
              data-label-space={space.id}
              style={mark ? { transform: `translateY(calc(-50% - ${mark.lift}px))` } : undefined}
            >
              {space.name}
            </div>
          </Html>
        );
      })}
      {pois.map((poi) => (
        <Html key={`poi-${poi.id}`} position={[poi.point[0], 0, -poi.point[1]]} center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
          <div className="poi" title={poi.title}>{poi.glyph === "exit" ? EXIT_ICON : poi.glyph}</div>
        </Html>
      ))}
    </group>
  );
}
