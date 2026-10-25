import { describe, expect, it } from "vitest";
import type { Building } from "../api/types";
import type { BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { adoptRound, roundStatus, useRound } from "./round";

const floor = { id: "F0", level: 0, name: "Ground floor", elevation_m: 0, height_m: 3 };
const space = (id: string, name: string) => ({ id, name, floor_id: "F0", ref: null, anchor: [0, 0] });
const spaces = [space("S1", "Main aisle"), space("S2", "Server room"), space("S3", "Kitchen")];
const assets = [
  { id: "A2", type: "fire_extinguisher", name: "Fire extinguisher 2", space_id: "S2", floor_id: "F0" },
  { id: "A3", type: "fire_extinguisher", name: "Fire extinguisher 3", space_id: "S3", floor_id: "F0" },
];

describe("adoptRound", () => {
  it("takes the agent's stops in the agent's order", () => {
    const building = { key: "b", floors: [floor], spaces, assets, openings: [], connectors: [] } as unknown as Building;
    const model = { building, spaceById: new Map(spaces.map((s) => [s.id, s])), floorById: new Map([["F0", floor]]) } as unknown as BuildingModel;
    useTwin.setState({ buildingKey: "b", building, model });
    const plan = adoptRound(
      { device_type: "fire_extinguisher", start: "S1", stops: [{ space_id: "S3", asset_ids: ["A3"] }, { space_id: "S2", asset_ids: ["A2"] }], return_to_start: false },
      42.5,
    );
    expect(plan?.stops.map((stop) => stop.spaceId)).toEqual(["S3", "S2"]);
    expect(plan?.lengthM).toBe(42.5);
    expect(useRound.getState()).toMatchObject({ open: true, area: "Ground floor", startId: "S1", guiding: false, checked: [] });
    expect(roundStatus().text).toBe("0 of 2 stops checked, 2 left.");
  });

  it("refuses stops the building does not have", () => {
    expect(adoptRound({ device_type: "x", start: "S1", stops: [{ space_id: "nope", asset_ids: [] }], return_to_start: false }, null)).toBeNull();
  });
});
