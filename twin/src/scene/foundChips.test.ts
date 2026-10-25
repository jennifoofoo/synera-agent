import { describe, expect, it } from "vitest";
import type { BuildingModel } from "../model/model";
import { foundChipIds } from "./Markers";

const asset = (id: string, floor_id: string, x: number) => [id, { id, floor_id, position: [x, 0] }] as const;
const model = {
  assetById: new Map([asset("a", "F0", 50), asset("b", "F0", 2), asset("c", "F1", 1), asset("d", "F0", 10), asset("e", "F0", 30), asset("f", "F0", 20), asset("g", "F0", 40)]),
  spaceById: new Map([["S1", { anchor: [0, 0] }]]),
} as unknown as BuildingModel;

describe("foundChipIds", () => {
  it("names the five nearest found things on the floor of 'you are here'", () => {
    const ids = foundChipIds(model, ["a", "b", "c", "d", "e", "f", "g"], { space_id: "S1", floor_id: "F0", point: [0, 0], source: "tap" });
    expect([...ids].sort()).toEqual(["b", "d", "e", "f", "g"]);
  });
  it("uses the room anchor when the position has no point", () => {
    const ids = foundChipIds(model, ["a", "b"], { space_id: "S1", floor_id: "F0", point: null, source: "said" }, 1);
    expect([...ids]).toEqual(["b"]);
  });
  it("keeps the agent's order without a position", () => {
    expect([...foundChipIds(model, ["a", "b", "c", "d", "e", "f", "g"], null)]).toEqual(["a", "b", "c", "d", "e"]);
  });
});
