import { describe, expect, it } from "vitest";
import type { Building } from "../api/types";
import { buildModel } from "../model/model";
import { floorLayout, floorRoles } from "./floorVisibility";

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
