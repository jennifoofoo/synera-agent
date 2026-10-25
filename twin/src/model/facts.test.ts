import { describe, expect, it } from "vitest";
import type { Fact } from "../api/types";
import { closedOnRoute } from "./closures";
import { factPlace, factsForStep, groupFactPins, pinFacts, sinceText, untilByPlace, untilText, whenText } from "./facts";
import type { BuildingModel } from "./model";

// 25 Oct 2026 is the day summer time ends in Berlin: 10:00 Berlin = 09:00 UTC (CET, +01:00).
const NOW = new Date("2026-10-25T10:00:00+01:00");

const model = {
  spaceById: new Map([
    ["S1", { id: "S1", floor_id: "F0", name: "Hall A2", anchor: [10, 5], polygon: [], type: "room" }],
    ["S2", { id: "S2", floor_id: "F0", name: "Kitchen", anchor: [30, 5], polygon: [], type: "room" }],
    ["L0", { id: "L0", floor_id: "F0", name: "", anchor: [50, 5], polygon: [], type: "lift" }],
    ["L1", { id: "L1", floor_id: "F1", name: "", anchor: [50, 5], polygon: [], type: "lift" }],
  ]),
  assetById: new Map([["A1", { id: "A1", name: "Press 2", floor_id: "F0", space_id: "S1", position: [12, 6] }]]),
  openingById: new Map([["D1", { id: "D1", floor_id: "F0", position: [20, 5] }]]),
  connectorById: new Map([["V1", { id: "V1", kind: "lift", name: "Office lift", space_ids: ["L0", "L1"], floor_ids: ["F0", "F1"], step_free: true }]]),
  connectorBySpace: new Map(),
  floorById: new Map(),
} as unknown as BuildingModel;

function fact(id: string, over: Partial<Omit<Fact, "anchor">> & { anchor?: Partial<Fact["anchor"]> } = {}): Fact {
  return {
    id,
    kind: "note",
    text: `text ${id}`,
    valid_from: "2026-10-25T08:10:00+01:00",
    valid_to: null,
    status: "open",
    author: "Technician A",
    photo: null,
    created_at: "2026-10-25T08:10:00+01:00",
    ...over,
    anchor: { space_id: "S1", asset_id: null, element_id: null, point: null, floor_id: "F0", ...over.anchor },
  };
}

describe("time words on the page", () => {
  it("says until when a closure holds, in Berlin time", () => {
    expect(untilText("2026-10-25T18:00:00+01:00", NOW)).toBe("until 18:00");
    expect(untilText("2026-10-26T18:00:00+01:00", NOW)).toBe("until tomorrow 18:00");
    expect(untilText("2026-10-30T18:00:00+01:00", NOW)).toBe("until Fri 18:00");
    expect(untilText("2026-11-10T09:30:00+01:00", NOW)).toBe("until 10 Nov 9:30");
    expect(untilText("not a time", NOW)).toBe("");
  });

  it("says since when a fact holds", () => {
    expect(sinceText("2026-10-25T08:10:00+01:00", NOW)).toBe("since 8:10");
    expect(sinceText("2026-10-24T12:40:00+02:00", NOW)).toBe("since yesterday 12:40");
    expect(sinceText("2026-10-22T09:00:00+02:00", NOW)).toBe("since Thu 9:00");
    expect(sinceText("2026-10-01T09:00:00+02:00", NOW)).toBe("since 1 Oct");
    expect(whenText("2026-10-25T08:10:00+01:00", NOW)).toBe("today 8:10");
  });
});

describe("pins", () => {
  it("stand on the point, else the thing, the door, the room", () => {
    expect(factPlace(model, fact("f1", { anchor: { point: [11, 4] } }))?.point).toEqual([11, 4]);
    expect(factPlace(model, fact("f2", { anchor: { asset_id: "A1" } }))?.point).toEqual([12, 6]);
    expect(factPlace(model, fact("f3", { anchor: { element_id: "D1" } }))?.point).toEqual([20, 5]);
    expect(factPlace(model, fact("f4"))?.point).toEqual([10, 5]);
  });

  it("only open notes and issues are pins (no closures, resolved or resolving facts)", () => {
    const facts = [fact("a"), fact("b", { kind: "closure" }), fact("c", { status: "resolved" }), fact("d", { resolves: "a" }), fact("e", { kind: "issue" })];
    expect(pinFacts(facts).map((f) => f.id)).toEqual(["a", "e"]);
  });

  it("share one pin per spot, issues first; a room-only pin is marked so it sits above the name", () => {
    const groups = groupFactPins(model, [fact("a"), fact("b", { kind: "issue" }), fact("c", { anchor: { asset_id: "A1" } })]);
    expect(groups).toHaveLength(2);
    const room = groups.find((g) => g.roomOnly)!;
    expect(room.facts.map((f) => f.id)).toEqual(["b", "a"]);
    expect(groups.find((g) => !g.roomOnly)!.facts.map((f) => f.id)).toEqual(["c"]);
  });

  it("while walking, the step that names a room shows its notes; the last step the destination's", () => {
    const facts = [fact("a"), fact("k", { anchor: { space_id: "S2" } })];
    expect(factsForStep(model, facts, "Walk through Hall A2 to the door.").map((f) => f.id)).toEqual(["a"]);
    expect(factsForStep(model, facts, "Turn left.", "S2", true).map((f) => f.id)).toEqual(["k"]);
    expect(factsForStep(model, facts, "Turn left.", "S2", false)).toEqual([]);
  });
});

describe("closed until", () => {
  it("maps a closed lift's end to its stops and names it on the route", () => {
    const until = untilByPlace(model, { V1: "2026-10-26T18:00:00+01:00" });
    expect(until.get("L0")).toBe("2026-10-26T18:00:00+01:00");
    expect(until.get("L1")).toBe("2026-10-26T18:00:00+01:00");
    const route = { ok: true, floors: ["F0"] };
    expect(closedOnRoute(model, route, ["V1"], { V1: "until tomorrow 18:00" })).toEqual(["Office lift until tomorrow 18:00"]);
    expect(closedOnRoute(model, route, ["V1"])).toEqual(["Office lift"]);
  });
});
