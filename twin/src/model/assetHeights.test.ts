import { describe, expect, it } from "vitest";
import { DEFAULT_HEIGHT, MACHINE_HEIGHT, MARKING_HEIGHT, assetHeight, isFloorMarking } from "./assetHeights";

describe("assetHeight", () => {
  it("gives every thing a body height by type", () => {
    expect(assetHeight({ type: "desk", category: "furniture" })).toBe(0.75);
    expect(assetHeight({ type: "pallet_jack", category: "equipment" })).toBe(0.15);
    expect(assetHeight({ type: "pallet_rack", category: "furniture" })).toBe(1.2);
    expect(assetHeight({ type: "chair", category: "furniture" })).toBe(0.45);
  });

  it("falls back to 0.3 m for unknown types and keeps machines tall", () => {
    expect(assetHeight({ type: "something_new", category: "equipment" })).toBe(DEFAULT_HEIGHT);
    expect(assetHeight({ type: "cnc_mill", category: "machine" })).toBe(MACHINE_HEIGHT);
  });

  it("keeps floor markings flat", () => {
    expect(isFloorMarking({ type: "floor_marking" })).toBe(true);
    expect(assetHeight({ type: "floor_marking", category: "fixture" })).toBe(MARKING_HEIGHT);
    expect(isFloorMarking({ type: "desk" })).toBe(false);
  });

  it("never draws a body taller than the 3D office walls (about 1.5 m), machines aside", () => {
    for (const type of ["wardrobe", "bookshelf", "server_rack", "fridge", "vending_machine", "lectern"]) {
      expect(assetHeight({ type, category: "furniture" })).toBeLessThanOrEqual(1.2);
    }
  });
});
