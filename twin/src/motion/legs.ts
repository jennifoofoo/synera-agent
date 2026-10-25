import type { Route, RouteSegment } from "../api/types";
import type { MotionLeg, Point } from "./types";

/** Turn the page's route (POST /api/route, or state.route) into motion legs.
 *
 * The server sends one segment per floor stretch and one floor_change per stair/lift, in route order; a segment
 * ends where its floor change starts. A floor change between two segments makes the first leg end at a
 * connector (the matcher waits there). Two consecutive segments on the same floor with no floor change between
 * them (walk -> outside) are one leg boundary of kind "pass". The last leg ends with "arrival". */
export function legsFromRoute(route: Pick<Route, "segments" | "floor_changes">): MotionLeg[] {
  const segments = (route.segments ?? []).filter((segment) => segment.points.length > 0);
  const changes = [...(route.floor_changes ?? [])];
  const legs: MotionLeg[] = [];
  segments.forEach((segment, index) => {
    const next = segments[index + 1];
    const leg: MotionLeg = { floorId: segment.floor_id, points: segment.points.map(copy), end: "arrival" };
    if (next) {
      const change = next.floor_id !== segment.floor_id ? takeChange(changes, segment, next) : undefined;
      if (change) {
        leg.end = "connector";
        leg.connector = {
          id: change.connector_id,
          kind: change.kind,
          name: change.name,
          toFloor: change.to_floor,
          direction: change.direction,
        };
      } else {
        leg.end = next.floor_id !== segment.floor_id ? "connector" : "pass";
      }
    }
    legs.push(leg);
  });
  return legs;
}

/** Legs from the guide's current leg (state.guide.leg.segments): same rules, one guide step. */
export function legsFromSegments(segments: RouteSegment[]): MotionLeg[] {
  return legsFromRoute({ segments, floor_changes: [] });
}

function takeChange(changes: NonNullable<Route["floor_changes"]>, from: RouteSegment, to: RouteSegment) {
  const index = changes.findIndex((change) => change.from_floor === from.floor_id && change.to_floor === to.floor_id);
  if (index < 0) return undefined;
  return changes.splice(index, 1)[0];
}

const copy = (point: Point): Point => [point[0], point[1]];
