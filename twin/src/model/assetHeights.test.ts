import { describe, expect, it } from "vitest";
import {
  DEFAULT_HEIGHT,
  FAR_FURNITURE_CAP,
  FULL_AT_MPP,
  MACHINE_HEIGHT,
  MARKING_HEIGHT,
  assetHeight,
  growsWithZoom,
  isFloorMarking,
  zoomedHeight,
} from "./assetHeights";

describe("zoomedHeight", () => {
  const bed = { type: "bed", category: "furniture" };
  const wardrobe = { type: "wardrobe", category: "furniture" };

  it("keeps furniture a low block far out and grows it to full height near", () => {
    expect(zoomedHeight(wardrobe, 0.5)).toBe(FAR_FURNITURE_CAP);
    expect(zoomedHeight(wardrobe, FULL_AT_MPP)).toBeCloseTo(1.2);
    expect(zoomedHeight(wardrobe, 0.05)).toBeCloseTo(1.2);
    const mid = zoomedHeight(wardrobe, 0.16);
    expect(mid).toBeGreaterThan(FAR_FURNITURE_CAP);
    expect(mid).toBeLessThan(1.2);
  });

  it("keeps a small flat low at its overview even at a near scale (the whole floor fits the screen)", () => {
    expect(zoomedHeight(wardrobe, 0.05, 0.5)).toBe(FAR_FURNITURE_CAP);
    expect(zoomedHeight(wardrobe, 0.05, 3)).toBeCloseTo(1.2);
  });

  it("never makes a low piece taller than its type height", () => {
    expect(zoomedHeight({ type: "shower", category: "fixture" }, 0.5)).toBe(0.1);
    expect(zoomedHeight(bed, 0.5)).toBe(FAR_FURNITURE_CAP);
  });

  it("keeps machines, equipment, factory furniture and kept things at full height at every zoom", () => {
    expect(zoomedHeight({ type: "cnc_mill", category: "machine" }, 1)).toBe(MACHINE_HEIGHT);
    expect(zoomedHeight({ type: "fridge", category: "equipment" }, 1)).toBe(1.2);
    expect(zoomedHeight({ type: "pallet_rack", category: "furniture" }, 1)).toBe(1.2);
    expect(zoomedHeight(wardrobe, 1, 0.5, true)).toBe(1.2);
    expect(growsWithZoom(bed)).toBe(true);
    expect(growsWithZoom({ type: "workbench", category: "furniture" })).toBe(false);
  });
});

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
