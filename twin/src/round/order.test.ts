import { describe, expect, it } from "vitest";
import type { Floor, Space } from "../api/types";
import { areaOptions, hallOf, inArea, normType, orderRound } from "./order";

const floor = (id: string, level: number, name: string): Floor => ({ id, level, name, elevation_m: level * 4, height_m: 4 });
const space = (id: string, name: string, floor_id = "F0"): Space => ({
  id, floor_id, name, type: "room", room_type: "", ref: null, polygon: [], anchor: [0, 0], area_m2: 1,
});

describe("inspection round order", () => {
  it("walks a line in order and fixes a nearest-neighbour detour with 2-opt", () => {
    // points on a line at 0, 1, 3, 6, 10 (start at 0): the shortest open path is 1, 2, 3, 4.
    const xs = [0, 1, 3, 6, 10];
    const d = xs.map((a) => xs.map((b) => Math.abs(a - b)));
    expect(orderRound(d)).toEqual([1, 2, 3, 4]);
    // Start in the middle (5): the best open path goes left first, 5 -> 4 -> 0 -> 9 -> 10 = 1 + 4 + 9 + 1.
    const ys = [5, 4, 9, 0, 10];
    const e = ys.map((a) => ys.map((b) => Math.abs(a - b)));
    const order = orderRound(e);
    const length = [0, ...order].slice(1).reduce((sum, node, i) => sum + e[[0, ...order][i]][node], 0);
    expect(length).toBe(15);
    expect(order.length).toBe(4);
  });

  it("matches types and areas the way people say them", () => {
    expect(normType("Fire extinguishers")).toBe(normType("fire_extinguisher"));
    expect(hallOf("Production zone H-A3")).toBe("A");
    const ground = floor("F0", 0, "Ground floor");
    expect(inArea(space("a", "Production zone H-A3"), ground, "Hall A")).toBe(true);
    expect(inArea(space("a", "Main aisle H-B1"), ground, "Hall A")).toBe(false);
    expect(inArea(space("a", "Server room 0.14"), ground, "Ground floor")).toBe(true);
    expect(inArea(space("a", "Server room 1.14", "F1"), floor("F1", 1, "Floor 1"), "Ground floor")).toBe(false);
    expect(inArea(space("a", "Server room 1.14", "F1"), floor("F1", 1, "Floor 1"), "server room")).toBe(true);
    expect(areaOptions([ground], [space("a", "Production zone H-A3"), space("b", "Main aisle H-B1")])).toEqual(["Whole building", "Ground floor", "Hall A", "Hall B"]);
  });
});
