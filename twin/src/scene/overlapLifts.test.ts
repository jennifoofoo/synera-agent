import { describe, expect, it } from "vitest";
import { overlapLifts } from "./geometry";

describe("overlapLifts", () => {
  it("lifts a room drawn inside a larger one, so the two slabs never flicker", () => {
    const corridor: [number, number][] = [[0, 0], [20, 0], [20, 10], [0, 10]];
    const stairs: [number, number][] = [[1, 1], [5, 1], [5, 4], [1, 4]];
    const [c, s] = overlapLifts([corridor, stairs]);
    expect(c).toBe(0);
    expect(s).toBeGreaterThan(0);
  });
  it("leaves rooms that only share an edge at floor level", () => {
    const a: [number, number][] = [[0, 0], [5, 0], [5, 5], [0, 5]];
    const b: [number, number][] = [[5, 0], [12, 0], [12, 5], [5, 5]];
    expect(overlapLifts([a, b])).toEqual([0, 0]);
  });
});
