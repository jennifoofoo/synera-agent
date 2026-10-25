import { describe, expect, it } from "vitest";
import type { Asset, Floor, Opening, Space } from "../api/types";
import { areaOptions, entranceRoom, hallOf, missingDevicesNote, normType } from "./choices";

const floor = (id: string, level: number, name: string): Floor => ({ id, level, name, elevation_m: level * 4, height_m: 4 });
const space = (id: string, name: string, floor_id = "F0"): Space => ({
  id, floor_id, name, type: "room", room_type: "", ref: null, polygon: [], anchor: [0, 0], area_m2: 1,
});

describe("inspection round choices", () => {
  it("matches types and offers areas the way people say them", () => {
    expect(normType("Fire extinguishers")).toBe(normType("fire_extinguisher"));
    expect(hallOf("Production zone H-A3")).toBe("A");
    expect(hallOf("Server room 0.14")).toBeNull();
    const ground = floor("F0", 0, "Ground floor");
    expect(areaOptions([ground], [space("a", "Production zone H-A3"), space("b", "Main aisle H-B1")])).toEqual(["Whole building", "Ground floor", "Hall A", "Hall B"]);
  });

  it("starts at the room behind the first entrance", () => {
    const openings = [
      { id: "O2", kind: "entrance", space_ids: ["S9"] },
      { id: "O1", kind: "door", space_ids: ["S1", "S2"] },
      { id: "O3", kind: "entrance", space_ids: ["S4"] },
    ] as unknown as Opening[];
    expect(entranceRoom(openings)).toBe("S4");
    expect(entranceRoom([])).toBeNull();
  });

  it("says why there is no round on a map without the devices", () => {
    const extinguisher = { id: "A1", name: "FE 1", type: "fire_extinguisher" } as Asset;
    expect(missingDevicesNote([])).toBe("This map has no devices yet, so there is no round to plan.");
    expect(missingDevicesNote([], "fire_extinguisher")).toBe("This map has no devices yet, so there is no round to plan.");
    expect(missingDevicesNote([extinguisher], "defibrillator")).toBe("This map has no defibrillators yet.");
    expect(missingDevicesNote([extinguisher], "Fire extinguishers")).toBeNull();
    expect(missingDevicesNote([extinguisher])).toBeNull();
  });
});
