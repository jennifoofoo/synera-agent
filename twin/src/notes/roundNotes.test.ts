import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { Building, BuildingState, Route } from "../api/types";
import type { BuildingModel } from "../model/model";
import { cancelDoor, openRound, proposeDoor, roundConfirmDoor, roundDone, roundHowFar, roundStatus, useRound, type RoundPlan } from "../round/round";
import { useTwin } from "../store";
import { stopsLine } from "../ui/Report";
import { MemoryFacts, type FactsStorage, type Note } from "./notes";
import { addNoteHere, canUndo, finishJob, installNotes, relevantNotes, undoNote, useNotes } from "./notesStore";

const floor = { id: "F0", level: 0, name: "Ground floor", elevation_m: 0, height_m: 3 };
const space = (id: string, name: string, anchor: [number, number]) => ({ id, name, floor_id: "F0", ref: null, anchor });
const spaces = [space("S0", "Entrance", [0, 0]), space("S1", "Hall A", [10, 0]), space("S2", "Hall B", [20, 0]), space("S3", "Hall C", [30, 0])];
const asset = (id: string, spaceId: string, position: [number, number]) => ({ id, type: "fire_extinguisher", name: `Fire extinguisher ${id}`, space_id: spaceId, floor_id: "F0", position });
const assets = [asset("A1", "S1", [10, 1]), asset("A2", "S2", [20, 1]), asset("A2b", "S2", [24, 1]), asset("A3", "S3", [30, 1])];
const building = { key: "b", floors: [floor], spaces, assets, openings: [], connectors: [] } as unknown as Building;
const model = {
  building,
  spaceById: new Map(spaces.map((s) => [s.id, s])),
  assetById: new Map(assets.map((a) => [a.id, a])),
  floorById: new Map([["F0", floor]]),
  openingById: new Map(),
  connectorById: new Map(),
} as unknown as BuildingModel;

const plan: RoundPlan = {
  building: "b",
  type: "fire_extinguisher",
  area: "Ground floor",
  startId: "S0",
  startName: "Entrance",
  stops: [
    { spaceId: "S1", floorId: "F0", name: "Hall A", assetIds: ["A1"] },
    { spaceId: "S2", floorId: "F0", name: "Hall B", assetIds: ["A2", "A2b"] },
    { spaceId: "S3", floorId: "F0", name: "Hall C", assetIds: ["A3"] },
  ],
  lengthM: 100,
  measured: "route",
  unreachable: [],
  returnToStart: false,
};

const route = (start: string, destination: string, length_m: number): Route => ({ ok: true, start, destination, length_m, steps: [`Walk ${length_m} m to the stop.`, "You have arrived."] }) as Route;
const state = (r: Route | null) => ({ route: r, closed: [], added_doors: [], position: null }) as unknown as BuildingState;

function note(id: string, space_id: string, asset_id: string | null): Note {
  return { id, kind: "note", anchor: { space_id, asset_id, element_id: null, point: null, floor_id: "F0" }, text: id, valid_from: new Date().toISOString(), valid_to: null, status: "open", author: "Night shift", photo: null, created_at: new Date().toISOString() };
}

/** Go on to the next stop the way round.ts does: the leg's route first, then the index, then the step sheet. */
function leg(index: number, r: Route | null): void {
  useTwin.setState({ state: state(r), walkStep: null });
  useRound.setState({ index, guiding: true });
  if (r) useTwin.setState({ walkStep: 0 });
}

let uninstall = () => {};
beforeEach(() => {
  vi.spyOn(api, "clearRoute").mockResolvedValue({ state: state(null) } as never);
  useTwin.setState({ buildingKey: "b", building, model, selection: null, walkStep: null, state: state(null), voiceOut: false, handsFree: false });
  useRound.setState({ plan: { ...plan }, guiding: false, returning: false, index: 0, checked: [], finished: false });
  useNotes.setState({ buildingKey: "b", storage: new MemoryFacts(), notes: [], job: null, report: null, guide: null, dismissed: [] });
  uninstall = installNotes();
  useNotes.setState({ buildingKey: "b", storage: new MemoryFacts() });
});
afterEach(() => {
  uninstall();
  vi.restoreAllMocks();
});

describe("notes in an inspection round", () => {
  it("anchors a note said at a stop on the stop's device", async () => {
    leg(1, route("S1", "S2", 40));
    expect(await addNoteHere("Seal broken, replace next week")).toBe("Noted at Fire extinguisher A2 · Hall B.");
    const saved = useNotes.getState().notes[0];
    expect(saved.anchor).toMatchObject({ space_id: "S2", floor_id: "F0", asset_id: "A2" });
    // The next round keeps it at that stop.
    expect(relevantNotes([saved])).toEqual([saved]);
  });

  it("at a stop keeps notes on its devices and on its room without a device, nothing else", () => {
    leg(1, route("S1", "S2", 40));
    const onDevice = note("on-device", "S2", "A2b");
    const onRoom = note("on-room", "S2", null);
    const otherDevice = note("other-device", "S2", "X9");
    const otherStop = note("other-stop", "S1", "A1");
    expect(relevantNotes([onDevice, onRoom, otherDevice, otherStop]).map((n) => n.id)).toEqual(["on-device", "on-room"]);
  });
});

describe("the job report of a round", () => {
  it("covers the whole round: legs, checked stops, notes; a stop in the same room does not end it", async () => {
    leg(0, route("S0", "S1", 30));
    const startedAt = useNotes.getState().job?.startedAt;
    expect(useNotes.getState().job?.title).toBe("Inspection round · Fire extinguisher · 3 stops");
    useTwin.setState({ walkStep: 1 });
    useRound.setState({ checked: ["S1"] });
    leg(1, route("S1", "S2", 40));
    await addNoteHere("Pin missing");
    useRound.setState({ checked: ["S1", "S2"] });
    // Third stop: no route (already there), the step sheet closes; the job goes on.
    leg(2, null);
    expect(useNotes.getState().job?.startedAt).toBe(startedAt);
    expect(finishJob()).toBe("Round finished: 2 of 3 stops checked. 70 metres walked. 1 note saved.");
    const report = useNotes.getState().report!;
    expect(report).toMatchObject({ title: "Inspection round · Fire extinguisher · 3 stops", lengthM: 100, walkedM: 70, arrived: false, startedAt });
    expect(report.noteIds).toHaveLength(1);
    expect(report.endedAt).not.toBeNull();
    expect(stopsLine(report)).toEqual({ count: "2 of 3", checked: ["Hall A", "Hall B"], missed: ["Hall C"] });
    expect(useRound.getState().guiding).toBe(false);
  });

  it("walks back to the start as a final leg, then completes", async () => {
    useRound.setState({ plan: { ...plan, returnToStart: true, lengthM: 125 } });
    leg(0, route("S0", "S1", 30));
    useRound.setState({ checked: ["S1", "S2"] });
    leg(2, route("S2", "S3", 40));
    vi.spyOn(api, "route").mockResolvedValue({ route: route("S3", "S0", 25), state: state(route("S3", "S0", 25)) } as never);
    await roundDone();
    expect(useRound.getState()).toMatchObject({ guiding: true, returning: true, finished: false });
    expect(roundStatus().label).toBe("Back to the start · 25 m");
    expect(await roundDone()).toBe("Round complete: 3 of 3 stops checked.");
    const report = useNotes.getState().report!;
    expect(report).toMatchObject({ arrived: true, lengthM: 125, walkedM: 95 });
    expect(stopsLine(report)?.count).toBe("3 of 3");
  });
});

describe("round safety and answers", () => {
  it("ignores a second Done while the next leg is loading", async () => {
    leg(0, route("S0", "S1", 30));
    let release: (value: unknown) => void = () => {};
    const routeCall = vi.spyOn(api, "route").mockReturnValue(new Promise((resolve) => (release = resolve)) as never);
    const first = roundDone();
    expect(await roundDone()).toBe("One moment, the next stop is loading.");
    release({ route: route("S1", "S2", 40), state: state(route("S1", "S2", 40)) });
    await first;
    expect(routeCall).toHaveBeenCalledTimes(1);
    expect(useRound.getState()).toMatchObject({ index: 1, checked: ["S1"] });
  });

  it("answers how far: to the next stop and for the rest of the round", () => {
    useRound.setState({ plan: { ...plan, legsM: [30, 40, 30] } });
    leg(1, route("S1", "S2", 40));
    expect(roundHowFar(25)).toBe("25 metres to the next stop, 55 metres left in the round.");
    useRound.setState({ returning: true });
    expect(roundHowFar(20)).toBe("20 metres back to the start.");
  });

  it("adds a what-if door only after a yes", async () => {
    const addDoor = vi.spyOn(api, "addDoor").mockRejectedValue(new Error("not in this test"));
    proposeDoor("S1", "S2");
    expect(useRound.getState().pendingDoor).toEqual(["S1", "S2"]);
    cancelDoor();
    expect(addDoor).not.toHaveBeenCalled();
    proposeDoor("S1", "S2");
    await roundConfirmDoor();
    expect(addDoor).toHaveBeenCalledWith("b", "S1", "S2", true);
  });

  it("opens the panel without choosing a type for the person", async () => {
    useRound.setState({ type: "", plan: null });
    await openRound();
    expect(useRound.getState()).toMatchObject({ open: true, type: "", plan: null });
  });

  it("undoes only a note saved here, and warns when the server removed another one", async () => {
    const mine = note("mine", "S1", null);
    const other = note("other", "S1", null);
    const storage = { kind: "server", label: "", list: async () => [mine], add: async () => ({ fact: mine }), undo: async () => ({ undoneId: "other" }) } as unknown as FactsStorage;
    useNotes.setState({ storage, notes: [mine, other] });
    expect(canUndo(other)).toBe(false); // not saved from this page
    await undoNote("mine");
    expect(useNotes.getState().notes.map((n) => n.id)).toEqual(["mine"]);
    expect(useNotes.getState().error).toMatch(/removed a different note/);
  });
});
