import { useMemo } from "react";
import { Html } from "@react-three/drei";
import type { Point, Space } from "../api/types";
import type { FloorModel, BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { useMapZoom, type MapTier } from "./mapZoom";
import { LABEL_LIFT, guideNextPoint } from "./markerLayout";
import { LIFT as ROUTE_LIFT } from "./RouteLine";
import { PoiBadge, POI_PX, type PoiKind } from "./poiIcons";

interface Props {
  floor: FloorModel;
  model: BuildingModel;
  y: number;
  limit: number;
  flat?: boolean;
}

/** Room names shown at every tier: the largest rooms (the zones of the floor). */
const ZONE_COUNT = 6;
const FIT_OVERFLOW = 1.15; // a name may run 15 % past its room's width
const CHAR_PX = 6.8; // average glyph width of the 12 px label font
const LABEL_H_PX = 16;
const GAP_PX = 4; // free space kept around every label and badge
const ROUTE_CLEAR_PX = 7; // half the route line width plus a margin: room names never sit on the route

interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

type Item =
  | { kind: "poi"; id: string; point: Point; poi: PoiKind; title: string }
  | { kind: "room"; id: string; point: Point; space: Space };

function overlaps(a: Box, b: Box): boolean {
  return a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
}

/** Does the segment p-q (screen px) pass through the box? Liang-Barsky clipping. */
function segmentHitsBox(p: Point, q: Point, box: Box): boolean {
  let t0 = 0;
  let t1 = 1;
  const dx = q[0] - p[0];
  const dy = q[1] - p[1];
  const edges: [number, number][] = [
    [-dx, p[0] - box.x0],
    [dx, box.x1 - p[0]],
    [-dy, p[1] - box.y0],
    [dy, box.y1 - p[1]],
  ];
  for (const [denominator, numerator] of edges) {
    if (denominator === 0) {
      if (numerator < 0) return false;
      continue;
    }
    const t = numerator / denominator;
    if (denominator < 0) t0 = Math.max(t0, t);
    else t1 = Math.min(t1, t);
    if (t0 > t1) return false;
  }
  return true;
}

function spanOf(polygon: Point[]): [number, number] {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const [x, y] of polygon) {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  }
  return [maxX - minX, maxY - minY];
}

function poiKindOf(space: Space, model: BuildingModel): PoiKind | null {
  const connector = model.connectorBySpace.get(space.id);
  if (connector) return connector.kind === "lift" ? "lift" : "stairs";
  if (space.room_type === "toilet") return "toilet";
  return null;
}

/** What one zoom tier shows, in priority order (earlier items win collisions). Deterministic: sorted by a fixed
 * key with the id as tie-break, so the same scale always gives the same set. */
function candidates(floor: FloorModel, model: BuildingModel, tier: MapTier, scale: number, limit: number): Item[] {
  const pois: Item[] = [];
  const rooms: Space[] = [];
  for (const space of floor.spaces) {
    const poi = poiKindOf(space, model);
    if (poi) pois.push({ kind: "poi", id: space.id, point: space.anchor, poi, title: space.name });
    else if (space.name && space.type !== "outdoor" && space.type !== "corridor") rooms.push(space);
  }
  for (const opening of floor.openings) {
    if (opening.kind === "entrance")
      pois.push({ kind: "poi", id: opening.id, point: opening.position, poi: "entrance", title: opening.step_free === false ? "Entrance / exit (not step-free)" : "Entrance / exit" });
    else if (opening.step_free === false) pois.push({ kind: "poi", id: opening.id, point: opening.position, poi: "step", title: "Not step-free (a step or threshold)" });
  }
  const poiRank: Record<PoiKind, number> = { entrance: 0, lift: 1, stairs: 2, toilet: 3, step: 4 };
  pois.sort((a, b) => (a.kind === "poi" && b.kind === "poi" ? poiRank[a.poi] - poiRank[b.poi] : 0) || a.id.localeCompare(b.id));
  // Every tier: the zones (largest rooms), whatever their size on screen. Mid and near add every room whose
  // name (nearly) fits inside it at this scale. Tiers are cumulative, like a street map.
  rooms.sort((a, b) => b.area_m2 - a.area_m2 || a.id.localeCompare(b.id));
  const zones = rooms.slice(0, ZONE_COUNT);
  const fitting =
    tier === "far"
      ? []
      : rooms.slice(ZONE_COUNT).filter((space) => {
          const [w, h] = spanOf(space.polygon);
          return space.name.length * CHAR_PX * scale <= w * FIT_OVERFLOW && LABEL_H_PX * scale <= h;
        });
  const named = [...zones, ...fitting].slice(0, limit).map((space): Item => ({ kind: "room", id: space.id, point: space.anchor, space }));
  return [...pois, ...named];
}

/** Room names and points of interest of the focused floor, in fixed zoom tiers (see mapZoom.ts). Lower
 * priority yields: nothing overlaps another label, and room names never sit on the drawn route. Rooms with a
 * marker (you are here, route ends, the guide's next target) always keep their name, lifted just above the
 * marker (screen px) so the marker never covers it. */
export function Labels({ floor, model, y, limit, flat = false }: Props) {
  const { scale, tier } = useMapZoom(floor.bounds.cx, y, -floor.bounds.cy);
  const state = useTwin((s) => s.state);
  const route = state?.route ?? null;
  const marks = useMemo(() => {
    const out = new Map<string, { point: Point; lift: number; height: number }>();
    const put = (spaceId: string | undefined | null, point: Point | null | undefined, lift: number, height = 0) => {
      const space = spaceId ? model.spaceById.get(spaceId) : undefined;
      if (!space || space.floor_id !== floor.id || !point) return;
      const known = out.get(space.id);
      if (!known || known.lift < lift) out.set(space.id, { point, lift, height });
    };
    if (route?.ok && route.segments?.length) {
      const first = route.segments[0];
      const last = route.segments[route.segments.length - 1];
      if (first.floor_id === floor.id) put(route.start, first.points[0], LABEL_LIFT.start, ROUTE_LIFT);
      if (last.floor_id === floor.id) put(route.destination, last.points[last.points.length - 1], LABEL_LIFT.end, ROUTE_LIFT);
    }
    const guide = state?.guide;
    const next = guide?.active && guide.leg.to_space_id !== route?.destination ? model.spaceById.get(guide.leg.to_space_id) : undefined;
    if (guide && next) put(next.id, guideNextPoint(guide, next), LABEL_LIFT.guide);
    const here = state?.position;
    if (here) put(here.space_id, here.point ?? model.spaceById.get(here.space_id)?.anchor, LABEL_LIFT.here);
    return out;
  }, [route, state?.guide, state?.position, model, floor.id]);
  const routeOnFloor = useMemo(
    () => (route?.ok && route.segments ? route.segments.filter((segment) => segment.floor_id === floor.id).map((segment) => segment.points) : []),
    [route, floor.id],
  );
  const shown = useMemo(() => {
    // Layout in screen pixels at the bucket's coarsest scale (y flipped: north is up on screen).
    const px = ([x, yy]: Point): Point => [x / scale, -yy / scale];
    const routePx = routeOnFloor.map((points) => points.map(px));
    const boxOf = (point: Point, halfW: number, halfH: number, lift = 0): Box => {
      const [cx, cy] = px(point);
      const y = cy - lift - (lift ? halfH : 0); // a lifted label's bottom edge sits `lift` px above the point
      return { x0: cx - halfW - GAP_PX / 2, y0: y - halfH - GAP_PX / 2, x1: cx + halfW + GAP_PX / 2, y1: y + halfH + GAP_PX / 2 };
    };
    // Marked rooms first: they always keep their name (above their marker); everything else keeps clear of them.
    const markedItems = floor.spaces
      .filter((space) => space.name && marks.has(space.id))
      .sort((a, b) => a.id.localeCompare(b.id))
      .map((space): Item => ({ kind: "room", id: space.id, point: marks.get(space.id)!.point, space }));
    const kept: Box[] = markedItems.map((item) =>
      boxOf(item.point, (item.kind === "room" ? item.space.name.length * CHAR_PX : 0) / 2, LABEL_H_PX / 2, marks.get(item.id)!.lift),
    );
    const result: Item[] = [...markedItems];
    for (const item of candidates(floor, model, tier, scale, limit)) {
      if (marks.has(item.id)) continue;
      const halfW = item.kind === "poi" ? POI_PX / 2 : (item.space.name.length * CHAR_PX) / 2;
      const halfH = item.kind === "poi" ? POI_PX / 2 : LABEL_H_PX / 2;
      const box = boxOf(item.point, halfW, halfH);
      if (kept.some((other) => overlaps(box, other))) continue;
      if (item.kind === "room") {
        const clear = { x0: box.x0 - ROUTE_CLEAR_PX, y0: box.y0 - ROUTE_CLEAR_PX, x1: box.x1 + ROUTE_CLEAR_PX, y1: box.y1 + ROUTE_CLEAR_PX };
        if (routePx.some((points) => points.some((p, i) => i > 0 && segmentHitsBox(points[i - 1], p, clear)))) continue;
      }
      kept.push(box);
      result.push(item);
    }
    return result;
  }, [floor, model, tier, scale, limit, routeOnFloor, marks]);

  return (
    <group position-y={y + 0.5}>
      {shown.map((item) =>
        item.kind === "room" ? (
          <RoomLabel key={item.id} item={item} mark={marks.get(item.id)} flat={flat} />
        ) : (
          <Html key={`poi-${item.id}`} position={[item.point[0], 0, -item.point[1]]} center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
            <PoiBadge kind={item.poi} title={item.title} />
          </Html>
        ),
      )}
    </group>
  );
}

function RoomLabel({ item, mark, flat }: { item: Extract<Item, { kind: "room" }>; mark?: { lift: number; height: number }; flat: boolean }) {
  return (
    <Html
      position={[item.point[0], mark ? mark.height - 0.5 : 0, -item.point[1]]} // at the marker's own height
      center
      zIndexRange={[2, 0]}
      style={{ pointerEvents: "none" }}
    >
      <div
        className={`label label-halo ${flat ? "label-plan" : ""}`}
        data-label-space={item.space.id}
        style={mark ? { transform: `translateY(calc(-50% - ${mark.lift}px))` } : undefined}
      >
        {item.space.name}
      </div>
    </Html>
  );
}
