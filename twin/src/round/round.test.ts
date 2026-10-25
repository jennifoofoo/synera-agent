import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { Building, BuildingState, PlannedRound } from "../api/types";
import type { BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { adoptRound, planRound, roundConfirmDoor, roundStatus, proposeDoor, useRound, whatIfLine } from "./round";

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

const emptyState = { closed: [], added_doors: [], route: null, position: null } as unknown as BuildingState;

function serverRound(order: string[], total: number, legs: number[]): PlannedRound {
  return {
    ok: true,
    device_type: "fire extinguisher",
    start: "Main aisle",
    stops: order.map((space_id, i) => ({ n: i + 1, room: space_id, space_id, floor: "Ground floor", devices: [], leg_m: legs[i] })),
    total_m: total,
    info: { device_type: "fire_extinguisher", start: "S1", stops: order.map((space_id) => ({ space_id, asset_ids: [`A${space_id.slice(1)}`] })), return_to_start: false },
    route: { ok: true, length_m: total },
  };
}

describe("planRound", () => {
  afterEach(() => vi.restoreAllMocks());

  function setUp() {
    const building = { key: "b", floors: [floor], spaces, assets, openings: [], connectors: [] } as unknown as Building;
    const model = { building, spaceById: new Map(spaces.map((s) => [s.id, s])), floorById: new Map([["F0", floor]]) } as unknown as BuildingModel;
    useTwin.setState({ buildingKey: "b", building, model, state: emptyState });
    useRound.setState({ open: true, type: "fire_extinguisher", area: "Ground floor", startId: "S1", returnToStart: false, plan: null, whatIf: null, error: null, guiding: false });
  }

  it("asks the server and takes its stops, order, total and legs", async () => {
    setUp();
    const round = vi.spyOn(api, "round").mockResolvedValue({ round: serverRound(["S3", "S2"], 99.1, [60, 39.1]), state: emptyState });
    const plan = await planRound();
    expect(round).toHaveBeenCalledWith("b", "fire_extinguisher", { area: "Ground floor", start: "S1", returnToStart: false });
    expect(plan?.stops.map((stop) => stop.spaceId)).toEqual(["S3", "S2"]);
    expect(plan?.lengthM).toBe(99.1);
    expect(plan?.legsM).toEqual([60, 39.1]);
    expect(useRound.getState()).toMatchObject({ area: "Ground floor", startId: "S1", error: null });
  });

  it("shows the server's refusal and plans nothing on the page", async () => {
    setUp();
    const route = vi.spyOn(api, "route");
    vi.spyOn(api, "round").mockResolvedValue({ round: { ok: false, error: "No device here matches 'unicorn'." }, state: emptyState });
    expect(await planRound()).toBeNull();
    expect(useRound.getState()).toMatchObject({ plan: null, error: "No device here matches 'unicorn'." });
    expect(route).not.toHaveBeenCalled();
  });

  it("compares the server totals before and after a what-if door", async () => {
    setUp();
    vi.spyOn(api, "round")
      .mockResolvedValueOnce({ round: serverRound(["S3", "S2"], 99.1, [60, 39.1]), state: emptyState })
      .mockResolvedValueOnce({ round: serverRound(["S2", "S3"], 60.4, [30, 30.4]), state: emptyState });
    const added = { ...emptyState, added_doors: [{ id: "D1", floor_id: "F0", space_ids: ["S2", "S3"] }] } as unknown as BuildingState;
    const addDoor = vi.spyOn(api, "addDoor").mockResolvedValue({ state: added, door: { id: "D1" } } as never);
    await planRound();
    proposeDoor("S2", "S3");
    expect(addDoor).not.toHaveBeenCalled(); // nothing changes before the yes
    const whatIf = await roundConfirmDoor();
    expect(addDoor).toHaveBeenCalledWith("b", "S2", "S3", true);
    expect(whatIf).toMatchObject({ beforeM: 99.1, afterM: 60.4 });
    expect(whatIfLine(whatIf!)).toBe("Round 39 m shorter (99 → 60 m)");
    expect(useRound.getState().plan?.stops.map((stop) => stop.spaceId)).toEqual(["S2", "S3"]);
  });
});
