import { describe, expect, it } from "vitest";
import type { Opening, Point, Space } from "../api/types";
import type { FloorModel } from "../model/model";
import { WALL_TOP_BAND, insidePolygon, roomBehindWall, wallHeightFor, wallTopOutline } from "./geometry";

function space(id: string, polygon: Point[], anchor: Point): Space {
  return { id, floor_id: "F0", type: "room", room_type: "office", name: id, ref: null, polygon, anchor, area_m2: 0 };
}

// Two rooms side by side (x 0..5 and 5..10, y 0..4) with a door in the shared wall at (5, 2).
const left = space("left", [[0, 0], [5, 0], [5, 4], [0, 4]], [2.5, 2]);
const right = space("right", [[5, 0], [10, 0], [10, 4], [5, 4]], [7.5, 2]);
const door: Opening = { id: "D1", floor_id: "F0", space_ids: ["left", "right"], kind: "door", position: [5, 2], width_m: 1, step_free: true, added: false };
const floor: FloorModel = {
  id: "F0",
  level: 0,
  name: "Ground floor",
  elevation_m: 0,
  height_m: 8,
  spaces: [left, right],
  openings: [door],
  assets: [],
  bounds: { minX: 0, minY: 0, maxX: 10, maxY: 4, cx: 5, cy: 2, size: 10 },
};

function vertices(geometry: ReturnType<typeof wallTopOutline>): [number, number, number][] {
  const position = geometry.getAttribute("position");
  return Array.from({ length: position.count }, (_, i) => [position.getX(i), position.getY(i), position.getZ(i)]);
}

describe("wallTopOutline", () => {
  it("lies on the room's polygon at wall-top height, within half a band of the walls", () => {
    const top = wallHeightFor(floor) + 0.015;
    const points = vertices(wallTopOutline(floor, "left"));
    const high = points.filter(([, y]) => Math.abs(y - top) < 1e-6);
    expect(high.length).toBeGreaterThan(0);
    const half = WALL_TOP_BAND / 2 + 1e-6;
    for (const [x, , z] of high) {
      const y = -z; // scene z = -model y
      // every band vertex is within half a band of one of the polygon's edges (x = 0, x = 5, y = 0, y = 4)
      const near = Math.min(Math.abs(x), Math.abs(x - 5), Math.abs(y), Math.abs(y - 4));
      expect(near).toBeLessThanOrEqual(half);
      expect(x).toBeGreaterThanOrEqual(-half);
      expect(x).toBeLessThanOrEqual(5 + half);
      expect(y).toBeGreaterThanOrEqual(-half);
      expect(y).toBeLessThanOrEqual(4 + half);
    }
  });

  it("drops to the floor across the door gap, so the outline stays closed", () => {
    const points = vertices(wallTopOutline(floor, "left"));
    const low = points.filter(([, y]) => y < 0.1);
    expect(low.length).toBe(6); // one quad across the door
    for (const [x, , z] of low) {
      expect(Math.abs(x - 5)).toBeLessThanOrEqual(WALL_TOP_BAND / 2 + 1e-6);
      expect(-z).toBeGreaterThan(1.3);
      expect(-z).toBeLessThan(2.7);
    }
  });

  it("is empty for an unknown room", () => {
    expect(wallTopOutline(floor, "nope").getAttribute("position").count).toBe(0);
  });
});

describe("roomBehindWall", () => {
  it("picks the room on the side of the wall the camera sees, with its anchor", () => {
    // the shared wall at x = 5, seen from the right room (looking west): the face normal points east (+x)
    const seenFromRight = roomBehindWall(floor.spaces, left, [5, 1], [1, 0, 0], [-1, -0.5, 0]);
    expect(seenFromRight.space.id).toBe("right");
    expect(seenFromRight.point).toEqual([7.5, 2]);
    // the same face with a flipped normal (winding) still resolves to the camera side
    expect(roomBehindWall(floor.spaces, left, [5, 1], [-1, 0, 0], [-1, -0.5, 0]).space.id).toBe("right");
    // seen from the left room (looking east)
    expect(roomBehindWall(floor.spaces, right, [5, 1], [1, 0, 0], [1, -0.5, 0]).space.id).toBe("left");
  });

  it("on a wall top takes the room the camera looks into", () => {
    expect(roomBehindWall(floor.spaces, right, [5, 1], [0, 1, 0], [-1, -1, 0]).space.id).toBe("left");
  });

  it("keeps the wall's own room when nothing lies behind it", () => {
    expect(roomBehindWall(floor.spaces, left, [0, 2], [-1, 0, 0], [1, -0.5, 0]).space.id).toBe("left");
  });
});

describe("insidePolygon", () => {
  it("handles a concave L shape", () => {
    const l: Point[] = [[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]];
    expect(insidePolygon([0.5, 3], l)).toBe(true);
    expect(insidePolygon([3, 0.5], l)).toBe(true);
    expect(insidePolygon([3, 3], l)).toBe(false);
  });
});
