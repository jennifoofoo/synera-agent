// Typed (or push-to-talk) "note: …" and "finished" in an inspection round go through store.ask: answered on the
// device, never sent to the agent (the video flow: note at extinguisher 3.02, "finished" after the last stop).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { Building, BuildingState, Route } from "../api/types";
import type { BuildingModel } from "../model/model";
import { useRound, type RoundPlan } from "../round/round";
import { useTwin } from "../store";
import { MemoryFacts } from "./notes";
import { closeReport, installNotes, useNotes } from "./notesStore";

const floor = { id: "F3", level: 3, name: "Floor 3", elevation_m: 9, height_m: 3 };
const space = (id: string, name: string, anchor: [number, number]) => ({ id, name, floor_id: "F3", ref: null, anchor });
const spaces = [space("S0", "Main Stairs", [0, 0]), space("S1", "Open Office East", [10, 0]), space("S2", "Third Floor Corridor", [20, 0])];
const asset = (id: string, spaceId: string, position: [number, number]) => ({ id, type: "fire_extinguisher", name: `Fire extinguisher ${id}`, space_id: spaceId, floor_id: "F3", position });
const assets = [asset("3.01", "S1", [10, 1]), asset("3.02", "S2", [20, 1])];
const building = { key: "b", floors: [floor], spaces, assets, openings: [], connectors: [] } as unknown as Building;
const model = {
  building,
  spaceById: new Map(spaces.map((s) => [s.id, s])),
  assetById: new Map(assets.map((a) => [a.id, a])),
  floorById: new Map([["F3", floor]]),
  openingById: new Map(),
  connectorById: new Map(),
} as unknown as BuildingModel;
const plan: RoundPlan = {
  building: "b",
  type: "fire_extinguisher",
  area: "Floor 3",
  startId: "S0",
  startName: "Main Stairs",
  startPoint: null,
  stops: [
    { key: "3.01", spaceId: "S1", floorId: "F3", name: "Open Office East", device: "Fire extinguisher 3.01", assetIds: ["3.01"], position: [10, 1] },
    { key: "3.02", spaceId: "S2", floorId: "F3", name: "Third Floor Corridor", device: "Fire extinguisher 3.02", assetIds: ["3.02"], position: [20, 1] },
  ],
  lengthM: 40,
  unreachable: [],
  returnToStart: false,
};
const route = (start: string, destination: string): Route => ({ ok: true, start, destination, length_m: 12, steps: ["Walk 12 m.", "You have arrived."] }) as Route;
const state = (r: Route | null) => ({ route: r, closed: [], added_doors: [], position: null }) as unknown as BuildingState;

let uninstall = () => {};
let chat: { mock: { calls: unknown[] } };
beforeEach(() => {
  vi.spyOn(api, "clearRoute").mockResolvedValue({ state: state(null) } as never);
  chat = vi.spyOn(api, "chat").mockResolvedValue({ reply: "agent", backend: "x" } as never);
  useTwin.setState({ buildingKey: "b", building, model, selection: null, walkStep: null, state: state(null), voiceOut: false, handsFree: false, chat: [], chatBusy: false });
  useRound.setState({ plan: { ...plan }, guiding: false, returning: false, index: 0, checked: [], finished: false });
  useNotes.setState({ buildingKey: "b", storage: new MemoryFacts(), notes: [], job: null, report: null, guide: null, dismissed: [] });
  uninstall = installNotes();
  useNotes.setState({ buildingKey: "b", storage: new MemoryFacts() });
});
afterEach(() => {
  uninstall();
  vi.restoreAllMocks();
});

describe("typed commands in an inspection round", () => {
  it("saves 'note: …' at stop 2 on its device, without the agent", async () => {
    useTwin.setState({ state: state(route("S1", "S2")) });
    useRound.setState({ index: 1, guiding: true });
    useTwin.setState({ walkStep: 0 });
    const reply = await useTwin.getState().ask("note: hose cracked");
    expect(chat).not.toHaveBeenCalled();
    expect(reply?.reply).toBe("Noted at Fire extinguisher 3.02 · Third Floor Corridor.");
    expect(useNotes.getState().notes[0].anchor).toMatchObject({ space_id: "S2", asset_id: "3.02", floor_id: "F3" });
    expect(useNotes.getState().notes[0].text).toBe("hose cracked");
    expect(useTwin.getState().chat.map((m) => m.text)).toEqual(["note: hose cracked", "Noted at Fire extinguisher 3.02 · Third Floor Corridor."]);
  });

  it("'Wanda, note: …' with the wake word works too", async () => {
    useRound.setState({ index: 1, guiding: true });
    const reply = await useTwin.getState().ask("Wanda, note: hose cracked");
    expect(chat).not.toHaveBeenCalled();
    expect(reply?.reply).toContain("Fire extinguisher 3.02");
  });

  it("'finished' after the last stop shows the round's job report, also after the sheet was closed", async () => {
    useRound.setState({ index: 0, guiding: true });
    useRound.setState({ checked: ["3.01", "3.02"], index: 1 });
    useRound.setState({ finished: true });
    useRound.setState({ guiding: false }); // round complete: the report opens by itself
    expect(useNotes.getState().report?.round).toBeTruthy();
    closeReport();
    for (const said of ["finished", "done with the round", "fertig"]) {
      closeReport();
      const reply = await useTwin.getState().ask(said);
      expect(reply?.reply).toContain("Round finished: 2 of 2 stops checked.");
      expect(useNotes.getState().report?.round?.checked).toEqual(["3.01", "3.02"]);
    }
    expect(chat).not.toHaveBeenCalled();
  });

  it("'finished' during the round ends it and shows the report", async () => {
    useRound.setState({ index: 0, guiding: true });
    const reply = await useTwin.getState().ask("finished");
    expect(chat).not.toHaveBeenCalled();
    expect(reply?.reply).toContain("Round finished: 0 of 2 stops checked.");
    expect(useNotes.getState().report?.round).toBeTruthy();
  });

  it("a plain route's arrival opens no job report (only rounds do)", () => {
    vi.useFakeTimers();
    try {
      useTwin.setState({ state: state(route("S0", "S2")) });
      useTwin.setState({ walkStep: 0 });
      vi.advanceTimersByTime(60_000); // long enough that the old code showed a report
      useTwin.setState({ walkStep: 1 });
      useTwin.setState({ walkStep: null });
      expect(useNotes.getState().job).toBeNull();
      expect(useNotes.getState().report).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("outside a round 'note: …' still goes to Wanda", async () => {
    await useTwin.getState().ask("note: hose cracked");
    expect(chat).toHaveBeenCalledOnce();
  });
});
