import { describe, expect, it } from "vitest";
import type { Building } from "../api/types";
import { buildModel } from "../model/model";
import type { Route } from "../api/types";
import { STACK_POLAR, floorChangeMarks, floorLayout, floorRoles, routeFloorIds, routeStackElevations, routeStackGap } from "./floorVisibility";
import { floorRuns } from "./RouteLine";

const square = (floor_id: string, id: string) => ({
  id,
  floor_id,
  type: "room",
  room_type: "living",
  name: id,
  ref: null,
  polygon: [[0, 0], [10, 0], [10, 10], [0, 10]] as [number, number][],
  anchor: [5, 5] as [number, number],
  area_m2: 100,
});

const model = buildModel({
  key: "t",
  name: "t",
  source: null,
  floors: [
    { id: "b", level: -1, name: "Basement", elevation_m: -3, height_m: 3 },
    { id: "g", level: 0, name: "Ground", elevation_m: 0, height_m: 3 },
    { id: "f1", level: 1, name: "Floor 1", elevation_m: 3, height_m: 3 },
  ],
  spaces: [square("b", "s1"), square("g", "s2"), square("f1", "s3")],
  openings: [],
  connectors: [],
  assets: [],
  state: {} as Building["state"],
});
const y = (id: string, mode: "single" | "exploded", focused = "g") => floorLayout(model.floorById.get(id)!, model, mode, null, focused);

describe("floorLayout in 'all floors' (exploded)", () => {
  it("pulls every floor apart in floor order, whichever floor is active", () => {
    expect(y("b", "exploded")).toBeLessThan(y("g", "exploded"));
    expect(y("g", "exploded")).toBeLessThan(y("f1", "exploded"));
    expect(y("f1", "exploded") - y("g", "exploded")).toBeGreaterThan(3);
    expect(y("g", "exploded", "f1")).toBe(y("g", "exploded", "g"));
  });

  it("uses the real elevations outside 'all floors'", () => {
    expect(y("b", "single")).toBe(-3);
    expect(y("f1", "single")).toBe(3);
  });
});

describe("floorRoles", () => {
  it("draws only the active floor in single mode (the plinth sits under it)", () => {
    const roles = floorRoles(model, "g", "single", false, null);
    expect([...roles.values()]).toEqual(["hidden", "full", "hidden"]);
  });

  it("draws every floor fully in 'all floors' (a hairline outline of a bigger floor below read as a stray frame)", () => {
    const roles = floorRoles(model, "g", "exploded", false, null);
    expect([...roles.values()]).toEqual(["full", "full", "full"]);
  });
});

const twoFloorRoute = {
  ok: true,
  start: "s2",
  destination: "s3",
  length_m: 30,
  floors: ["g", "f1"],
  segments: [
    { floor_id: "g", points: [[1, 1], [8, 1]] },
    { floor_id: "f1", points: [[8, 2], [8, 9]] },
  ],
} as unknown as Route;

describe("a route over two floors (stacked apart in 3D)", () => {
  it("knows its floors in route order", () => {
    expect(routeFloorIds(twoFloorRoute)).toEqual(["g", "f1"]);
    expect(routeFloorIds({ ...twoFloorRoute, segments: [twoFloorRoute.segments![0]] } as Route)).toBeNull();
  });

  it("draws exactly the route's floors, the others hidden", () => {
    const roles = floorRoles(model, "g", "single", false, ["g", "f1"]);
    expect(Object.fromEntries(roles)).toEqual({ b: "hidden", g: "full", f1: "full" });
    // 2D shows only the active floor, route or not
    expect(Object.fromEntries(floorRoles(model, "g", "single", true, ["g", "f1"]))).toEqual({ b: "hidden", g: "full", f1: "hidden" });
  });

  it("keeps the lowest route floor in place and lifts the next one by a readable gap", () => {
    const heights = routeStackElevations(model, ["f1", "g"]);
    expect(heights.get("g")).toBe(0);
    const gap = heights.get("f1")! - heights.get("g")!;
    expect(gap).toBe(routeStackGap(model.floorById.get("g")!, model.floorById.get("f1")!));
    // seen from the stack's tilt, the ground floor (walls included) ends on screen before most of Floor 1 begins
    const diagonal = Math.hypot(10, 10);
    expect(gap * Math.sin(STACK_POLAR)).toBeGreaterThan(0.75 * diagonal * Math.cos(STACK_POLAR) + 3 * Math.sin(STACK_POLAR));
    expect(gap).toBeGreaterThan(model.floorById.get("g")!.height_m + 5);
    // floorLayout uses the same heights; floors off the route keep their real elevation
    const at = (id: string) => floorLayout(model.floorById.get(id)!, model, "single", ["g", "f1"], "g");
    expect(at("f1")).toBe(heights.get("f1"));
    expect(at("b")).toBe(-3);
  });

  it("stacks route floors that skip a storey directly on top of each other", () => {
    const heights = routeStackElevations(model, ["b", "f1"]);
    expect(heights.get("b")).toBe(-3);
    expect(heights.get("f1")! - heights.get("b")!).toBe(routeStackGap(model.floorById.get("b")!, model.floorById.get("f1")!));
    expect(heights.has("g")).toBe(false);
  });

  it("joins the floors with one run at the stairs, from the last point below to the first above", () => {
    const y = (id: string) => (id === "g" ? 0 : 20);
    const runs = floorRuns(twoFloorRoute.segments!, y);
    expect(runs).toHaveLength(2);
    expect(runs[0].toArray().map((v) => Math.round(v * 100) / 100)).toEqual([8, 0.15, -1]);
    expect(runs[1].toArray().map((v) => Math.round(v * 100) / 100)).toEqual([8, 20.15, -2]);
    expect(floorRuns([twoFloorRoute.segments![0]], y)).toEqual([]);
  });
});

describe("floorChangeMarks: the same pill at both ends of a floor change", () => {
  const withStairs = {
    ...twoFloorRoute,
    floor_changes: [{ connector_id: "V02", kind: "stairs", name: "Main Stairs", from_floor: "g", to_floor: "f1", from_point: [8, 1], to_point: [8, 2], direction: "up" }],
  } as unknown as Route;

  it("says where the route leaves, with the stairs' name", () => {
    const [mark] = floorChangeMarks(withStairs, "g", model);
    expect(mark).toMatchObject({ leaving: true, otherFloor: "f1", point: [8, 1], kind: "stairs", text: "↑ Floor 1 via Main Stairs" });
  });

  it("says where it arrives on the next floor, pointing back down", () => {
    const [mark] = floorChangeMarks(withStairs, "f1", model);
    expect(mark).toMatchObject({ leaving: false, otherFloor: "g", point: [8, 2], text: "↓ from Ground, Main Stairs" });
  });

  it("names a lift 'Lift' when it has no name, and marks nothing on floors the change does not touch", () => {
    const lift = { ...withStairs, floor_changes: [{ ...withStairs.floor_changes![0], kind: "lift", name: "", direction: "down", from_floor: "f1", to_floor: "g" }] } as unknown as Route;
    expect(floorChangeMarks(lift, "f1", model)[0].text).toBe("↓ Ground via Lift");
    expect(floorChangeMarks(lift, "g", model)[0].text).toBe("↑ from Floor 1, Lift");
    expect(floorChangeMarks(withStairs, "b", model)).toEqual([]);
  });
});
