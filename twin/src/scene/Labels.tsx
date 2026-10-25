import { useEffect, useMemo, useRef } from "react";
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { controlsRef } from "./FloorMesh";
import type { Asset, Point, Space } from "../api/types";
import type { FloorModel, BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { useMapZoom, type MapTier } from "./mapZoom";
import { areasOf, type Area } from "./areas";
import { prettyType } from "../model/palette";
import { clusterDisruptions } from "./Markers";
import { closedConnectorStops } from "../model/closures";
import { HERE_RIM_PX, LABEL_LIFT, PIN_HEAD_PX, PIN_HEIGHT_PX, START_DOT_PX, TAP_CROSS_PX, TAP_STALK_M } from "./markerLayout";
import { LIFT as ROUTE_LIFT } from "./RouteLine";
import { useLandmarks } from "./landmarks";
import { CLOSED_TAG_PX, FLOOR_BADGE_H_PX, FOUND_DOT_PX, FOUND_MANY_PX, FloorBadge, FoundDot, PoiBadge, POI_PX, amenityKindOf, floorBadgeWidth, type PoiKind } from "./poiIcons";

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
const CHAR_PX = 7.0; // average glyph width of the 12 px semibold label font (Inter)
const LABEL_H_PX = 16;
const PILL_PAD_PX = 8; // horizontal padding of a pill label (each side); marked and tapped rooms are pills
const DEST_CHAR_PX = 8.2; // the destination's label is 14 px semibold
const DEST_H_PX = 24; // its height (18 px line plus 3 px padding above and below)
const DEST_PAD_PX = 11; // its horizontal padding (each side)
const PILL_H_PX = 20; // a pill's height (16 px line plus 2 px padding above and below)
const HALO_PAD_PX = 2; // 3D room names are halo text (no box): the halo reaches about 2 px past the glyphs
/** 3D points of interest (Apple Maps style): a small coloured dot in the overview, from the mid tier on a round badge
 * with its glyph and the name beside it (POI_TEXT_KINDS only). Sizes must match .poi-pin in poiIcons.css. */
const POI_DOT_PX = 10;
const POI_BADGE_3D_PX = 20;
const POI_TEXT_GAP_PX = 4;
const POI_TEXT_KINDS: ReadonlySet<PoiKind> = new Set(["lift", "stairs", "toilet"]);
const GAP_PX = 4; // free space kept around every label and badge
const THING_LIFT_PX = 9; // a thing's name sits just above its shape, never on it
const ROUTE_CLEAR_PX = 7; // half the route line width plus a margin: room names never sit on the route
const FOUND_NAMES = 3; // found things whose name is shown (in the agent's order); the selected one always tries too
const FOUND_CHAR_PX = 7.2; // the found names are semibold
const CHIP_CHAR_PX = 7.4; // 12 px semibold chip text
const CHIP_H_PX = 22; // 16 px line plus 3 px padding above and below
const AREA_CHAR_PX = 8.6; // area names: 14 px semibold with a little tracking
const AREA_H_PX = 20;
const AREA_FIT_OVERFLOW = 1.3;
const AREA_SHIFT_PX = 28; // an area name may move this far up or down to make way for a symbol
const AREA_FIT_OVERFLOW_H = 1.6; // a long, narrow strip of offices may carry its name a little past its walls
const SUB_CHAR_PX = 5.9; // second line under a room name: 10.5 px
const SUB_H_PX = 13;
const SUB_DY_PX = (LABEL_H_PX + SUB_H_PX) / 2; // its centre below the room name's centre
const DOOR_CHAR_PX = 5.8; // door widths: 10 px tabular numerals
const DOOR_H_PX = 13;
const WIDE_DOOR_M = 1.2; // doors at least this wide show their clear width (near tier)

interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

type Item =
  | { kind: "poi"; id: string; point: Point; poi: PoiKind; title: string; closed?: boolean }
  | { kind: "tag"; id: string; point: Point; dx: number }
  | { kind: "room"; id: string; point: Point; space: Space }
  | { kind: "area"; id: string; point: Point; area: Area }
  | { kind: "thing"; id: string; point: Point; asset: Asset; landmark: boolean }
  | { kind: "sub"; id: string; point: Point; text: string }
  | { kind: "door"; id: string; point: Point; text: string; title: string };

/** Map markers laid out before the labels (screen px), in this order: they win every collision. */
type Pin =
  | { kind: "floor"; id: string; point: Point; connector: "stairs" | "lift"; direction: "up" | "down"; level: number; title: string }
  | { kind: "found"; id: string; point: Point; ids: string[]; title: string }
  | { kind: "closed"; id: string; point: Point; text: string; title: string; dy: number }
  | { kind: "name"; id: string; point: Point; text: string; dx: number; dy: number };

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

function insidePolygon([x, y]: Point, polygon: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Does the box lie on the polygon (a sample point of the box inside it, or a polygon corner inside the box)? */
function boxOnPolygon(box: Box, polygon: Point[]): boolean {
  const xs = [box.x0, (box.x0 + box.x1) / 2, box.x1];
  const ys = [box.y0, (box.y0 + box.y1) / 2, box.y1];
  if (xs.some((x) => ys.some((y) => insidePolygon([x, y], polygon)))) return true;
  return polygon.some(([x, y]) => x > box.x0 && x < box.x1 && y > box.y0 && y < box.y1);
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
function candidates(
  floor: FloorModel,
  model: BuildingModel,
  tier: MapTier,
  scale: number,
  limit: number,
  flat: boolean,
  landmarks: ReadonlySet<string>,
  closedStops: ReadonlyMap<string, string>,
): Item[] {
  const pois: Item[] = [];
  const later: Item[] = []; // symbols that yield to room names (fire extinguishers: many, and not sought after)
  const rooms: Space[] = [];
  for (const space of floor.spaces) {
    const poi = poiKindOf(space, model);
    const closed = closedStops.has(space.id);
    if (poi) pois.push({ kind: "poi", id: space.id, point: space.anchor, poi, title: closed ? `${space.name || closedStops.get(space.id)} (closed)` : space.name, closed });
    else if (space.name && space.type !== "outdoor" && space.type !== "corridor") rooms.push(space);
  }
  for (const opening of floor.openings) {
    if (opening.kind === "entrance")
      pois.push({ kind: "poi", id: opening.id, point: opening.position, poi: "entrance", title: opening.step_free === false ? "Entrance / exit (not step-free)" : "Entrance / exit" });
    else if (opening.step_free === false) pois.push({ kind: "poi", id: opening.id, point: opening.position, poi: "step", title: "Not step-free (a step or threshold)" });
  }
  // 2D, from mid on: the amenity symbols (coffee, printer, first aid, and the fire extinguishers after the room
  // names). Landmarks of the current directions always carry their name; machine names from near on (mapZoom.ts).
  const landmarkItems: Item[] = [];
  const machineNames: Item[] = [];
  if (flat) {
    for (const asset of floor.assets) {
      // Fire extinguishers hang every few metres: only from near on, else they pepper the overview.
      const kind = amenityKindOf(asset.type);
      const amenity = kind && (tier === "near" || tier === "mid") ? kind : null;
      if (amenity) (amenity === "extinguisher" ? later : pois).push({ kind: "poi", id: asset.id, point: asset.position, poi: amenity, title: asset.name });
      if (landmarks.has(asset.id)) landmarkItems.push({ kind: "thing", id: asset.id, point: asset.position, asset, landmark: true });
      else if (tier === "near" && asset.category === "machine" && asset.name)
        machineNames.push({ kind: "thing", id: asset.id, point: asset.position, asset, landmark: false });
    }
    landmarkItems.sort((a, b) => a.id.localeCompare(b.id));
    machineNames.sort((a, b) => a.id.localeCompare(b.id));
  }
  const poiRank: Record<PoiKind, number> = { entrance: 0, lift: 1, stairs: 2, toilet: 3, step: 4, firstaid: 5, extinguisher: 6, coffee: 7, printer: 8 };
  // Closed lifts and stairs first: they must never yield to another symbol.
  const rankOf = (item: Item) => (item.kind === "poi" ? (item.closed ? -1 : poiRank[item.poi]) : 0);
  pois.sort((a, b) => rankOf(a) - rankOf(b) || a.id.localeCompare(b.id));
  later.sort((a, b) => a.id.localeCompare(b.id));
  // Near, 2D: the clear width of wide doors, last (they yield to everything else).
  const doors: Item[] = [];
  if (flat && tier === "near") {
    for (const opening of floor.openings) {
      if ((opening.kind !== "door" && opening.kind !== "entrance") || !opening.width_m || opening.width_m < WIDE_DOOR_M) continue;
      const text = `${opening.width_m.toFixed(1)} m`;
      doors.push({ kind: "door", id: opening.id, point: opening.position, text, title: `Door ${text} wide` });
    }
    doors.sort((a, b) => a.id.localeCompare(b.id));
  }
  // Overview (area tier, 2D): one calm name per area of same-kind rooms instead of single room names, if it fits.
  if (tier === "area") {
    const areas = areasOf(floor)
      .filter((area) => area.name.length * AREA_CHAR_PX * scale <= area.width * AREA_FIT_OVERFLOW && AREA_H_PX * scale <= area.height * AREA_FIT_OVERFLOW_H)
      .map((area): Item => ({ kind: "area", id: area.id, point: area.point, area }));
    return [...pois, ...landmarkItems, ...areas];
  }
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
  return [...pois, ...landmarkItems, ...named, ...machineNames, ...later, ...doors];
}

/** Everything with text or an icon on the focused floor, laid out together in screen px so nothing overlaps
 * (lower priority yields): kept clear of the "You are here" dot and the route ends; in 2D also the route's
 * floor-change badges ("↑ 1"), closures ("⚠ Kitchen 0.28"), found things (dots, names for the first few
 * and the selected one); then points of interest and room names in fixed zoom tiers (see mapZoom.ts). Room
 * names never sit on the drawn route; a room with a marker shows its name just above that marker. */
export function Labels({ floor, model, y, limit, flat = false }: Props) {
  const zoom = useMapZoom(floor.bounds.cx, y, -floor.bounds.cy, floor.bounds.size);
  const scale = zoom.scale;
  const tier: MapTier = flat || zoom.tier !== "area" ? zoom.tier : "far"; // 3D keeps its own labels
  useEffect(() => {
    if (flat) (window as unknown as { __twinMapZoom?: unknown }).__twinMapZoom = { tier, scale };
  }, [flat, tier, scale]);
  const landmarks = useLandmarks();
  const state = useTwin((s) => s.state);
  const highlights = useTwin((s) => s.highlights);
  const selectedAssetId = useTwin((s) => (s.selection?.kind === "asset" ? s.selection.id : null));
  const route = state?.route ?? null;
  // The tapped room always carries its name (like a marked room), and no other name may sit on it (mobile session).
  const selectedId = useTwin((s) => (s.selection ? (s.selection.kind === "space" ? s.selection.id : s.selection.space_id) : undefined));
  // Where the tap pin stands (HerePin.tsx TapPin): the tapped room's name moves above it like above the other markers.
  const tapPoint = useTwin((s) => (s.selection?.point && s.selection.kind !== "asset" && s.selection.kind !== "opening" ? s.selection.point : null));
  const marks = useMemo(() => {
    const out = new Map<string, { point: Point; lift: number; height: number; kind: "end" | "start" | "here" | "selected" }>();
    const put = (spaceId: string | undefined | null, point: Point | null | undefined, lift: number, kind: "end" | "start" | "here" | "selected", height = 0) => {
      const space = spaceId ? model.spaceById.get(spaceId) : undefined;
      if (!space || space.floor_id !== floor.id || !point) return;
      const known = out.get(space.id);
      if (!known || known.lift < lift) out.set(space.id, { point, lift, height, kind });
    };
    if (route?.ok && route.segments?.length) {
      const first = route.segments[0];
      const last = route.segments[route.segments.length - 1];
      if (first.floor_id === floor.id) put(route.start, first.points[0], LABEL_LIFT.start, "start", ROUTE_LIFT);
      if (last.floor_id === floor.id) put(route.destination, last.points[last.points.length - 1], LABEL_LIFT.end, "end", ROUTE_LIFT);
    }
    const here = state?.position;
    if (here) put(here.space_id, here.point ?? model.spaceById.get(here.space_id)?.anchor, LABEL_LIFT.here, "here");
    if (selectedId) {
      // The tap pin: 2D above its crosshair, 3D above the head of its stalk. A selection without a spot keeps the
      // name on the room's anchor. A marker already in the room with a larger lift wins (put keeps the larger lift).
      if (tapPoint) put(selectedId, tapPoint, flat ? LABEL_LIFT.tap : LABEL_LIFT.tapHead, "selected", flat ? 0 : TAP_STALK_M);
      else put(selectedId, model.spaceById.get(selectedId)?.anchor, 0, "selected");
    }
    return out;
  }, [route, state?.position, model, floor.id, selectedId, tapPoint, flat]);
  const routeOnFloor = useMemo(
    () => (route?.ok && route.segments ? route.segments.filter((segment) => segment.floor_id === floor.id).map((segment) => segment.points) : []),
    [route, floor.id],
  );
  // Found things on this floor, in the agent's order (2D: Labels draws them; 3D keeps the rings in Markers.tsx).
  const found = useMemo(() => {
    if (!flat) return [];
    const ids = Object.values(highlights).flatMap((highlight) => highlight.ids);
    return [...new Set(ids)].flatMap((id) => {
      const asset = model.assetById.get(id);
      const point = state?.moved_assets?.[id]?.position ?? asset?.position;
      return asset && point && asset.floor_id === floor.id ? [{ id, name: asset.name, point }] : [];
    });
  }, [flat, highlights, model, floor.id, state?.moved_assets]);
  const closed = useMemo(
    () => (flat ? clusterDisruptions(model, state?.closed ?? []).filter((d) => d.floor_id === floor.id) : []),
    [flat, model, state?.closed, floor.id],
  );
  const closedStops = useMemo(() => closedConnectorStops(model, state?.closed ?? []), [model, state?.closed]);
  const changes = useMemo(() => (flat && route?.ok ? (route.floor_changes ?? []).filter((change) => change.from_floor === floor.id) : []), [flat, route, floor.id]);

  const { shown, pins } = useMemo(() => {
    // Layout in screen pixels at the bucket's coarsest scale (y flipped: north is up on screen).
    const px = ([x, yy]: Point): Point => [x / scale, -yy / scale];
    const routePx = routeOnFloor.map((points) => points.map(px));
    const boxOf = (point: Point, halfW: number, halfH: number, lift = 0): Box => {
      const [cx, cy] = px(point);
      const y = cy - lift - (lift ? halfH : 0); // a lifted label's bottom edge sits `lift` px above the point
      return { x0: cx - halfW - GAP_PX / 2, y0: y - halfH - GAP_PX / 2, x1: cx + halfW + GAP_PX / 2, y1: y + halfH + GAP_PX / 2 };
    };
    const kept: Box[] = [];
    const pins: Pin[] = [];
    // 1. Fixed markers drawn elsewhere: the "You are here" dot and the route ends. Nothing may sit on them.
    const here = state?.position;
    const herePoint = here?.floor_id === floor.id ? (here.point ?? model.spaceById.get(here.space_id)?.anchor) : undefined;
    if (herePoint) kept.push(boxOf(herePoint, HERE_RIM_PX, HERE_RIM_PX));
    // The tap pin with its small crosshair (2D; in 3D the stalk stands up and the layout is approximate anyway).
    if (flat && tapPoint && selectedId && model.spaceById.get(selectedId)?.floor_id === floor.id) kept.push(boxOf(tapPoint, TAP_CROSS_PX, TAP_CROSS_PX));
    for (const points of routeOnFloor) {
      if (points.length < 2) continue;
      kept.push(boxOf(points[0], START_DOT_PX + 2, START_DOT_PX + 2));
      const [ex, ey] = px(points[points.length - 1]); // the destination pin stands on its tip
      kept.push({ x0: ex - PIN_HEAD_PX - 2, y0: ey - PIN_HEIGHT_PX, x1: ex + PIN_HEAD_PX + 2, y1: ey + 2 });
    }
    // 2. Floor changes of the route: one small badge where to go up or down (it replaces that stairs/lift POI).
    const replaced = new Set<string>();
    for (const change of changes) {
      const connector = model.connectorById.get(change.connector_id);
      for (const spaceId of connector?.space_ids ?? []) replaced.add(spaceId);
      const level = model.floorById.get(change.to_floor)?.level ?? 0;
      const box = boxOf(change.from_point, floorBadgeWidth(level) / 2, FLOOR_BADGE_H_PX / 2);
      kept.push(box);
      const toName = model.floorById.get(change.to_floor)?.name ?? change.to_floor;
      pins.push({ kind: "floor", id: `fc-${change.connector_id}-${change.to_floor}`, point: change.from_point, connector: change.kind === "lift" ? "lift" : "stairs", direction: change.direction, level, title: `${change.name} ${change.direction} to ${toName}` });
    }
    // 3. Found things: a dot each; dots that would touch merge into one with a count.
    const dots: { pin: Extract<Pin, { kind: "found" }>; names: string[]; box: Box }[] = [];
    for (const item of found) {
      const near = dots.find((dot) => overlaps(dot.box, boxOf(item.point, FOUND_DOT_PX / 2, FOUND_DOT_PX / 2)));
      if (near) {
        near.pin.ids.push(item.id);
        near.names.push(item.name);
        near.box = boxOf(near.pin.point, FOUND_MANY_PX / 2, FOUND_MANY_PX / 2);
        near.pin.title = near.names.join(", ");
        continue;
      }
      dots.push({ pin: { kind: "found", id: item.id, point: item.point, ids: [item.id], title: item.name }, names: [item.name], box: boxOf(item.point, FOUND_DOT_PX / 2, FOUND_DOT_PX / 2) });
    }
    for (const dot of dots) {
      kept.push(dot.box);
      pins.push(dot.pin);
    }
    // 4. Closures: "Closed · Kitchen 0.28" on the closed element (or just above / below it), else a bare badge, if free.
    closed.forEach((d, index) => {
      const text = d.names.length === 1 ? `Closed · ${d.names[0]}` : `${d.names.length} closed`;
      const title = `Closed: ${d.names.join(", ")}`;
      const [cx, cy] = px(d.point);
      const halfW = (text.length * CHIP_CHAR_PX + 30) / 2; // text, icon and padding
      const halfH = CHIP_H_PX / 2;
      const tries: [number, number, string][] = [[halfW, 0, text], [halfW, -(halfH + 6), text], [halfW, halfH + 6, text], [CHIP_H_PX / 2, 0, ""]];
      for (const [w, dy, label] of tries) {
        const box = { x0: cx - w - GAP_PX / 2, y0: cy + dy - halfH - GAP_PX / 2, x1: cx + w + GAP_PX / 2, y1: cy + dy + halfH + GAP_PX / 2 };
        if (kept.some((other) => overlaps(box, other))) continue;
        kept.push(box);
        pins.push({ kind: "closed", id: `closed-${index}`, point: d.point, text: label, title, dy });
        break;
      }
    });
    // 5. Names of the first found things (and the selected one): beside the dot, right / left / above / below, if free.
    const top = new Set(found.slice(0, FOUND_NAMES).map((item) => item.id));
    const named = dots.filter((dot) => dot.pin.ids.length === 1 && (top.has(dot.pin.id) || dot.pin.id === selectedAssetId));
    named.sort((a, b) => Number(b.pin.id === selectedAssetId) - Number(a.pin.id === selectedAssetId));
    for (const dot of named) {
      const text = dot.names[0];
      const halfW = (text.length * FOUND_CHAR_PX) / 2;
      const halfH = LABEL_H_PX / 2;
      const r = FOUND_DOT_PX / 2 + GAP_PX; // clear of its own dot (whose box carries the gap too)
      const [cx, cy] = px(dot.pin.point);
      const spots: [number, number][] = [[r + halfW, 0], [-(r + halfW), 0], [0, -(r + halfH)], [0, r + halfH]];
      for (const [dx, dy] of spots) {
        const box = { x0: cx + dx - halfW - GAP_PX / 2, y0: cy + dy - halfH - GAP_PX / 2, x1: cx + dx + halfW + GAP_PX / 2, y1: cy + dy + halfH + GAP_PX / 2 };
        if (kept.some((other) => overlaps(box, other))) continue;
        kept.push(box);
        pins.push({ kind: "name", id: dot.pin.id, point: dot.pin.point, text, dx, dy });
        break;
      }
    }
    // 6. Room names of marked rooms: they keep their name (above their marker) unless a marker above sits there.
    const markedItems = floor.spaces
      .filter((space) => space.name && marks.has(space.id))
      .sort((a, b) => Number(b.id === selectedId) - Number(a.id === selectedId) || a.id.localeCompare(b.id)) // the tapped room first
      .map((space): Item => ({ kind: "room", id: space.id, point: marks.get(space.id)!.point, space }));
    const result: Item[] = [];
    for (const item of markedItems) {
      // marked rooms are pills in both views
      const mark = marks.get(item.id)!;
      const dest = mark.kind === "end";
      const chars = item.kind === "room" ? item.space.name.length * (dest ? DEST_CHAR_PX : CHAR_PX) : 0;
      const box = boxOf(item.point, chars / 2 + (dest ? DEST_PAD_PX : PILL_PAD_PX), (dest ? DEST_H_PX : PILL_H_PX) / 2, mark.lift);
      if (kept.some((other) => overlaps(box, other))) continue;
      kept.push(box);
      result.push(item);
    }
    // 7. Points of interest and room names, by priority; no other name sits on the tapped room.
    const selected = selectedId ? model.spaceById.get(selectedId) : undefined;
    const selectedPx = selected && selected.floor_id === floor.id ? selected.polygon.map(px) : null;
    const onRoute = (box: Box) => {
      const clear = { x0: box.x0 - ROUTE_CLEAR_PX, y0: box.y0 - ROUTE_CLEAR_PX, x1: box.x1 + ROUTE_CLEAR_PX, y1: box.y1 + ROUTE_CLEAR_PX };
      return routePx.some((points) => points.some((p, i) => i > 0 && segmentHitsBox(points[i - 1], p, clear)));
    };
    const roomBoxes = new Map<string, Box>();
    const all = candidates(floor, model, tier, scale, limit, flat, landmarks, closedStops);
    const showTag = tier === "mid" || tier === "near"; // "Closed" beside a closed glyph, from the mid tier on
    // Closed lifts and stairs come first in `all`; once they are placed, each gets its "Closed" tag (right of the
    // glyph, else left), before any other symbol or name.
    const closedPlaced: Extract<Item, { kind: "poi" }>[] = [];
    let tagsDone = !showTag;
    const placeTags = () => {
      tagsDone = true;
      for (const item of closedPlaced) {
        for (const dx of [POI_PX / 2 + GAP_PX + CLOSED_TAG_PX / 2, -(POI_PX / 2 + GAP_PX + CLOSED_TAG_PX / 2)]) {
          const tagBox = boxOf([item.point[0] + dx * scale, item.point[1]], CLOSED_TAG_PX / 2, LABEL_H_PX / 2);
          if (kept.some((other) => overlaps(tagBox, other))) continue;
          kept.push(tagBox);
          result.push({ kind: "tag", id: item.id, point: item.point, dx });
          break;
        }
      }
    };
    for (const item of all) {
      if (!tagsDone && !(item.kind === "poi" && item.closed)) placeTags();
      if (item.kind === "door" || item.kind === "tag") continue; // doors after the second lines, below
      if ((marks.has(item.id) && !(item.kind === "poi" && item.closed)) || replaced.has(item.id)) continue; // a closed glyph always shows
      const text = item.kind === "room" ? item.space.name : item.kind === "thing" ? item.asset.name : item.kind === "area" ? item.area.name : "";
      // Halo text in both views (3D keeps a 2 px margin for the halo); 3D symbols are a dot or a badge with a name.
      const pillPad = flat || item.kind === "poi" ? 0 : HALO_PAD_PX;
      const poi3d = !flat && item.kind === "poi" ? poiLayout3d(item, tier) : null;
      const halfW = poi3d ? poi3d.halfW : (item.kind === "poi" ? POI_PX / 2 : (text.length * (item.kind === "area" ? AREA_CHAR_PX : CHAR_PX)) / 2) + pillPad;
      const halfH = poi3d ? poi3d.size / 2 : item.kind === "poi" ? POI_PX / 2 : item.kind === "area" ? AREA_H_PX / 2 + (flat ? 0 : 2) : LABEL_H_PX / 2;
      // An area name may also move up or down a little (inside the area) to make way for a symbol.
      const shifts = item.kind === "area" ? [0, AREA_SHIFT_PX, -AREA_SHIFT_PX] : [0];
      for (const shift of shifts) {
        const point: Point = shift ? [item.point[0], item.point[1] - shift * scale] : item.point;
        if (item.kind === "area" && shift && !item.area.polygons.some((polygon) => insidePolygon(point, polygon))) continue;
        const box = boxOf(point, halfW, halfH, item.kind === "thing" ? THING_LIFT_PX : 0);
        if (poi3d) {
          // the badge sits on the point, its name to the right: shift the box so it covers both and nothing else
          box.x0 += poi3d.shift;
          box.x1 += poi3d.shift;
        }
        if (kept.some((other) => overlaps(box, other))) continue;
        if ((item.kind === "room" || item.kind === "area") && selectedPx && boxOnPolygon(box, selectedPx)) continue;
        if ((item.kind === "room" || item.kind === "area" || (item.kind === "thing" && !item.landmark)) && onRoute(box)) continue; // landmarks keep their name on the route
        kept.push(box);
        result.push(shift ? { ...item, point } : item);
        if (item.kind === "room") roomBoxes.set(item.id, box);
        if (item.kind === "poi" && item.closed) closedPlaced.push(item);
        break;
      }
    }
    if (!tagsDone) placeTags();
    // Near, 2D: a second line under the room names shown ("Kitchen · 24 m²"), if it fits in the room and is free.
    if (flat && tier === "near") {
      for (const item of [...result]) {
        if (item.kind !== "room") continue;
        const space = item.space;
        const text = `${prettyType(space.room_type)} · ${Math.round(space.area_m2)} m²`;
        const [w, h] = spanOf(space.polygon);
        if (text.length * SUB_CHAR_PX * scale > w * FIT_OVERFLOW || (LABEL_H_PX + SUB_H_PX) * scale > h) continue;
        const [cx, cy] = px(item.point);
        const halfW = (text.length * SUB_CHAR_PX) / 2;
        const box = { x0: cx - halfW - GAP_PX / 2, y0: cy + SUB_DY_PX - SUB_H_PX / 2, x1: cx + halfW + GAP_PX / 2, y1: cy + SUB_DY_PX + SUB_H_PX / 2 + GAP_PX / 2 };
        const own = roomBoxes.get(space.id);
        if (kept.some((other) => other !== own && overlaps(box, other))) continue;
        if (selectedPx && space.id !== selectedId && boxOnPolygon(box, selectedPx)) continue;
        if (onRoute(box)) continue;
        kept.push(box);
        result.push({ kind: "sub", id: space.id, point: item.point, text });
      }
    }
    for (const item of all) {
      if (item.kind !== "door") continue;
      const box = boxOf(item.point, (item.text.length * DOOR_CHAR_PX) / 2, DOOR_H_PX / 2);
      if (kept.some((other) => overlaps(box, other))) continue;
      kept.push(box);
      result.push(item);
    }
    return { shown: result, pins };
  }, [floor, model, tier, scale, limit, routeOnFloor, marks, changes, found, closed, closedStops, selectedId, selectedAssetId, state?.position, flat, landmarks, tapPoint]);

  return (
    <group position-y={y + 0.5}>
      {pins.map((pin) => (
        <Html key={`${pin.kind}-${pin.id}`} position={[pin.point[0], 0, -pin.point[1]]} center zIndexRange={[4, 0]} style={{ pointerEvents: "none" }}>
          {pin.kind === "floor" ? (
            <FloorBadge kind={pin.connector} direction={pin.direction} level={pin.level} title={pin.title} />
          ) : pin.kind === "found" ? (
            <FoundDot count={pin.ids.length} title={pin.title} />
          ) : pin.kind === "closed" ? (
            <div className="chip chip-danger chip-closed" title={pin.title} style={{ transform: `translateY(${pin.dy}px)` }}>
              <ClosedGlyph />
              {pin.text}
            </div>
          ) : (
            <div className="label label-halo label-plan found-name" style={{ transform: `translate(${pin.dx}px, ${pin.dy}px)` }}>
              {pin.text}
            </div>
          )}
        </Html>
      ))}
      {shown.map((item) =>
        item.kind === "room" ? (
          <RoomLabel key={item.id} item={item} mark={marks.get(item.id)} flat={flat} selected={item.id === selectedId} y={y + 0.5} />
        ) : item.kind === "area" ? (
          <Html key={item.id} position={[item.point[0], 0, -item.point[1]]} center zIndexRange={[2, 0]} style={{ pointerEvents: "none" }}>
            <div className={`label label-halo label-area ${flat ? "label-plan" : ""} zoom-fade`} data-zoom-kind="area" data-area-rooms={item.area.space_ids.length}>
              {item.area.name}
            </div>
          </Html>
        ) : item.kind === "sub" ? (
          <Html key={`sub-${item.id}`} position={[item.point[0], 0, -item.point[1]]} center zIndexRange={[1, 0]} style={{ pointerEvents: "none" }}>
            <div className="label label-halo label-plan label-sub zoom-fade" data-zoom-kind="sub" style={{ transform: `translateY(${SUB_DY_PX}px)` }}>
              {item.text}
            </div>
          </Html>
        ) : item.kind === "door" ? (
          <Html key={`door-${item.id}`} position={[item.point[0], 0, -item.point[1]]} center zIndexRange={[1, 0]} style={{ pointerEvents: "none" }}>
            <div className="label label-halo label-plan label-door zoom-fade" data-zoom-kind="door" title={item.title}>
              {item.text}
            </div>
          </Html>
        ) : item.kind === "tag" ? (
          <Html key={`tag-${item.id}`} position={[item.point[0], 0, -item.point[1]]} center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
            <div className={`label label-halo ${flat ? "label-plan" : ""} closed-tag zoom-fade`} data-zoom-kind="closed-tag" data-closed-space={item.id} style={{ transform: `translateX(${item.dx}px)` }}>
              Closed
            </div>
          </Html>
        ) : item.kind === "thing" ? (
          <Html key={`thing-${item.id}`} position={[item.point[0], 0, -item.point[1]]} center zIndexRange={[1, 0]} style={{ pointerEvents: "none" }}>
            <div className={`label label-halo label-plan label-thing ${item.landmark ? "label-landmark" : ""} zoom-fade`} data-zoom-kind="thing" data-label-asset={item.asset.id} style={{ transform: `translateY(calc(-50% - ${THING_LIFT_PX}px))` }}>
              {item.asset.name}
            </div>
          </Html>
        ) : (
          <Html key={`poi-${item.id}`} position={[item.point[0], 0, -item.point[1]]} center zIndexRange={[3, 0]} style={{ pointerEvents: "none" }}>
            {flat ? (
              <div className="zoom-fade" data-zoom-kind={`poi-${item.poi}`} data-poi-space={item.id}>
                <PoiBadge kind={item.poi} title={item.title} closed={item.closed} />
              </div>
            ) : (
              <PoiPin item={item} tier={tier} />
            )}
          </Html>
        ),
      )}
    </group>
  );
}

/** "No entry" glyph of the closed badge: a circle with a bar. */
export function ClosedGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.4" />
      <path d="M7 12h10" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}

/** 3D: a room name further from the camera than this many times the orbit distance is hidden (the far side of a
 * tilted view, near the horizon, where names pile up). Marked and selected rooms always keep theirs. */
const FAR_LABEL = 1.3;

function RoomLabel({ item, mark, flat, selected, y }: { item: Extract<Item, { kind: "room" }>; mark?: { lift: number; height: number; kind: string }; flat: boolean; selected: boolean; y: number }) {
  const div = useRef<HTMLDivElement>(null);
  const cull = !flat && !mark && !selected;
  useFrame(({ camera }) => {
    const el = div.current;
    const c = controlsRef.current;
    if (!el) return;
    let hide = false;
    if (cull && c) {
      const dx = camera.position.x - item.point[0];
      const dy = camera.position.y - y;
      const dz = camera.position.z + item.point[1];
      hide = Math.hypot(dx, dy, dz) > c.distance * FAR_LABEL;
    }
    const want = hide ? "hidden" : "";
    if (el.style.visibility !== want) el.style.visibility = want;
  });
  return (
    <Html
      position={[item.point[0], mark ? mark.height - 0.5 : 0, -item.point[1]]} // at the marker's own height
      center
      zIndexRange={[2, 0]}
      style={{ pointerEvents: "none" }}
    >
      <div
        ref={div}
        className={`label label-halo ${flat ? "label-plan" : ""} ${mark ? "label-marked" : ""} ${selected ? "label-selected" : ""} ${mark?.kind === "end" ? "label-dest" : ""} zoom-fade`}
        data-label-space={item.space.id}
        data-zoom-kind="room"
        style={mark ? { transform: `translateY(calc(-50% - ${mark.lift}px))` } : undefined}
      >
        {item.space.name}
      </div>
    </Html>
  );
}

/** 3D symbol layout: dot (far) or badge (mid, near), and the name beside the badge for the sought-after kinds. `halfW`
 * and `shift` describe the collision box relative to the point (badge centred on it, name to the right). */
function poiLayout3d(item: Extract<Item, { kind: "poi" }>, tier: MapTier): { size: number; text: string; halfW: number; shift: number } {
  const badge = tier !== "far" || item.closed;
  const size = badge ? POI_BADGE_3D_PX : POI_DOT_PX;
  const text = badge && !item.closed && POI_TEXT_KINDS.has(item.poi) && item.title ? item.title : "";
  const textW = text ? POI_TEXT_GAP_PX + text.length * CHAR_PX : 0;
  return { size, text, halfW: (size + textW) / 2, shift: textW / 2 };
}

/** A 3D point of interest: a coloured dot, or a round badge with its glyph and the name beside it (Apple Maps style). */
function PoiPin({ item, tier }: { item: Extract<Item, { kind: "poi" }>; tier: MapTier }) {
  const { size, text } = poiLayout3d(item, tier);
  return (
    <div className={`poi-pin poi-pin-${item.poi} ${size === POI_DOT_PX ? "poi-pin-dot" : ""} zoom-fade`} data-zoom-kind={`poi-${item.poi}`} data-poi-space={item.id}>
      <PoiBadge kind={item.poi} title={item.title} closed={item.closed} />
      {text && <span className="label label-halo poi-pin-name">{text}</span>}
    </div>
  );
}
