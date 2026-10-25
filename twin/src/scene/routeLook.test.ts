// The route reads as ONE clean line: one opaque casing plus one opaque line, and a path without redundant joints.
import { describe, expect, test } from "vitest";
import type { Point } from "../api/types";
import { COLOURS } from "../model/palette";
import routeLineSource from "./RouteLine.tsx?raw";
import { routeLayers, simplifyPolyline } from "./routeLook";

describe("routeLayers", () => {
  test("exactly one darker, wider casing under one Synera-blue line", () => {
    const [casing, line] = routeLayers();
    expect(routeLayers()).toHaveLength(2);
    expect(line.colour).toBe(COLOURS.signal);
    expect(casing.colour).toBe(COLOURS.mapBlueDark);
    expect(casing.widthPx).toBeGreaterThan(line.widthPx);
    expect(casing.renderOrder).toBeLessThan(line.renderOrder);
  });
  test("the pale variant (outside the guide leg) is a lighter opaque colour, not an alpha", () => {
    const [casing, line] = routeLayers(true);
    expect(line.colour).toMatch(/^#[0-9a-f]{6}$/);
    expect(line.colour).not.toBe(COLOURS.signal);
    expect(casing.colour).not.toBe(COLOURS.mapBlueDark);
    expect(Number.parseInt(line.colour.slice(1), 16)).toBeGreaterThan(Number.parseInt(COLOURS.signal.slice(1), 16));
  });
});

describe("RouteLine source", () => {
  // Regression: an old route stayed on screen as a dissolving ghost, and halo/flow layers drew translucent bands.
  const source: string = routeLineSource;
  test("keeps no copy of an earlier route and no halo or flow layer", () => {
    expect(source).not.toMatch(/ghost/i);
    expect(source).not.toMatch(/DISSOLVE|HALO|FLOW_/);
  });
});

describe("simplifyPolyline", () => {
  test("drops repeated and collinear points (the factory route's door approaches)", () => {
    const points: Point[] = [[0, 2.72], [0.5, 2.72], [2.01, 1.65], [3.41, 1.65], [4.5, 2.72], [5.0, 2.72], [5.5, 2.72], [5.5, 17.04], [5.0, 17.04], [4.5, 17.04], [2.5, 17.04]];
    expect(simplifyPolyline(points)).toEqual([[0, 2.72], [0.5, 2.72], [2.01, 1.65], [3.41, 1.65], [4.5, 2.72], [5.5, 2.72], [5.5, 17.04], [2.5, 17.04]]);
  });
  test("keeps ends, bends and a turn back", () => {
    expect(simplifyPolyline([[0, 0], [0, 0], [1, 0]])).toEqual([[0, 0], [1, 0]]);
    expect(simplifyPolyline([[0, 0], [2, 0], [1, 0]])).toEqual([[0, 0], [2, 0], [1, 0]]);
    expect(simplifyPolyline([[0, 0], [1, 0], [1, 1]])).toEqual([[0, 0], [1, 0], [1, 1]]);
  });
});
