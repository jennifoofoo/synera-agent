import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { Building, BuildingState, PlannedRound } from "../api/types";
import type { BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { adoptRound, endRound, planRound, roundConfirmDoor, roundDone, roundHowFar, roundStatus, proposeDoor, startRound, useRound, whatIfLine } from "./round";

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
    expect(round).toHaveBeenCalledWith("b", "fire_extinguisher", { area: "Ground floor", start: "S1", startPoint: null, returnToStart: false });
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

describe("one stop per device", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    endRound();
  });

  // Two extinguishers in S2 (two stops), one in S3; the agent's round carries positions and legs.
  const deviceRound = {
    device_type: "fire_extinguisher",
    start: "S1",
    start_point: [1, 1] as [number, number],
    stops: [
      { space_id: "S2", asset_ids: ["A2"], asset_id: "A2", name: "Fire extinguisher 2", position: [2, 2] as [number, number], leg_m: 10 },
      { space_id: "S2", asset_ids: ["A2b"], asset_id: "A2b", name: "Fire extinguisher 2b", position: [2, 5] as [number, number], leg_m: 3 },
      { space_id: "S3", asset_ids: ["A3"], asset_id: "A3", name: "Fire extinguisher 3", position: [9, 9] as [number, number], leg_m: 20 },
    ],
    return_to_start: false,
    total_m: 33,
  };

  function setUp() {
    const building = { key: "b", floors: [floor], spaces, assets, openings: [], connectors: [] } as unknown as Building;
    const model = { building, spaceById: new Map(spaces.map((s) => [s.id, s])), floorById: new Map([["F0", floor]]), assetById: new Map() } as unknown as BuildingModel;
    const okRoute = { route: { ok: true, length_m: 12 }, state: emptyState };
    useTwin.setState({ buildingKey: "b", building, model, state: emptyState, startWalk: () => {}, stopWalk: () => {}, applyState: () => {}, clearRoute: async () => {}, flyTo: () => {}, setHighlight: () => {} } as never);
    return vi.spyOn(api, "route").mockResolvedValue(okRoute as never);
  }

  it("adopts a chat round device by device with its legs and total", () => {
    setUp();
    const plan = adoptRound(deviceRound, 99);
    expect(plan?.stops.map((stop) => stop.key)).toEqual(["A2", "A2b", "A3"]);
    expect(plan?.stops.map((stop) => stop.spaceId)).toEqual(["S2", "S2", "S3"]);
    expect(plan?.legsM).toEqual([10, 3, 20]);
    expect(plan?.lengthM).toBe(33);
    expect(plan?.startPoint).toEqual([1, 1]);
  });

  it("routes each leg from the previous device's position to this device's position", async () => {
    const route = setUp();
    adoptRound(deviceRound, null);
    await startRound();
    // First leg: from the start dot (no position known) to the first device.
    expect(route).toHaveBeenLastCalledWith("b", "S1", "S2", false, [], { start_point: { x: 1, y: 1 }, destination_point: { x: 2, y: 2 } });
    expect(roundStatus().label).toBe("Fire extinguisher 2");
    expect(roundStatus()).toMatchObject({ stop: 1, total: 3 });
    // Second device in the same room: no route, the panel says it is here.
    route.mockClear();
    await roundDone();
    expect(route).not.toHaveBeenCalled();
    expect(useRound.getState()).toMatchObject({ index: 1, checked: ["A2"] });
    expect(roundStatus().label).toBe("Fire extinguisher 2b");
    await roundDone();
    expect(route).toHaveBeenLastCalledWith("b", "S2", "S3", false, [], { start_point: { x: 2, y: 5 }, destination_point: { x: 9, y: 9 } });
    expect(useRound.getState().checked).toEqual(["A2", "A2b"]);
  });

  it("says how far to the next device and what is left, also for a chat-planned round", async () => {
    setUp();
    adoptRound(deviceRound, null);
    await startRound();
    expect(roundHowFar(8)).toBe("8 metres to the next stop, 31 metres left in the round.");
    await roundDone();
    expect(roundHowFar(null)).toBe("You are at stop 2, 20 metres left in the round.");
  });
});
