import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Building, BuildingState, Route } from "../api/types";
import type { BuildingModel } from "../model/model";
import { useRound, type RoundPlan } from "../round/round";
import { useTwin } from "../store";
import { isSpeaking, speak } from "../voice";
import { MemoryFacts, type Note } from "./notes";
import { installNotes, useNotes } from "./notesStore";

vi.mock("../voice", async (original) => ({
  ...(await original<typeof import("../voice")>()),
  speak: vi.fn(async () => {}),
  isSpeaking: vi.fn(() => false),
  speechPending: vi.fn(() => false),
}));

const floor = { id: "F0", level: 0, name: "Ground floor", elevation_m: 0, height_m: 3 };
const space = (id: string, name: string) => ({ id, name, floor_id: "F0", ref: null, anchor: [0, 0] });
const spaces = [space("S0", "Entrance"), space("S1", "Project Room"), space("S2", "Foyer")];
const asset = (id: string, spaceId: string) => ({ id, type: "fire_extinguisher", name: `Fire extinguisher ${id}`, space_id: spaceId, floor_id: "F0", position: [0, 0] });
const assets = [asset("A1", "S1"), asset("A2", "S2")];
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
  startPoint: null,
  stops: [
    { key: "S1", spaceId: "S1", floorId: "F0", name: "Project Room", device: "", assetIds: ["A1"], position: null },
    { key: "S2", spaceId: "S2", floorId: "F0", name: "Foyer", device: "", assetIds: ["A2"], position: null },
  ],
  lengthM: 60,
  unreachable: [],
  returnToStart: false,
};
const route = (start: string, destination: string): Route => ({ ok: true, start, destination, length_m: 30, steps: ["Walk 30 m to the stop.", "You have arrived."] }) as Route;
const state = (r: Route | null) => ({ route: r, closed: [], added_doors: [], position: null }) as unknown as BuildingState;
const nightShift: Note = {
  id: "n1",
  kind: "issue",
  anchor: { space_id: "S1", asset_id: "A1", element_id: null, point: null, floor_id: "F0" },
  text: "Bracket is loose, always check it first.",
  valid_from: new Date().toISOString(),
  valid_to: null,
  status: "open",
  author: "Night shift",
  photo: null,
  created_at: new Date().toISOString(),
};

let uninstall = () => {};
beforeEach(async () => {
  vi.useFakeTimers();
  vi.mocked(speak).mockClear();
  useTwin.setState({ buildingKey: "b", building, model, selection: null, walkStep: null, state: state(null), voiceOut: true, handsFree: false });
  useRound.setState({ plan: { ...plan }, guiding: true, returning: false, index: 0, checked: [], finished: false });
  useNotes.setState({ buildingKey: "b", storage: new MemoryFacts(), notes: [], job: null, report: null, guide: null, dismissed: [] });
  uninstall = installNotes();
  await vi.advanceTimersByTimeAsync(0); // the first load (empty store) is in
  useNotes.setState({ notes: [nightShift] });
});
afterEach(() => {
  uninstall();
  vi.mocked(isSpeaking).mockReturnValue(false);
  vi.useRealTimers();
});

/** Arrive at stop 1 (the last step of the leg to Project Room), with the step line still being read. */
function arriveAtFirstStop(): void {
  vi.mocked(isSpeaking).mockReturnValue(true);
  useTwin.setState({ state: state(route("S0", "S1")), walkStep: 0 });
  useTwin.setState({ walkStep: 1 });
}

describe("a note read at a stop", () => {
  it("is spoken once the step line is done", async () => {
    arriveAtFirstStop();
    expect(useNotes.getState().guide?.notes.map((note) => note.id)).toEqual(["n1"]);
    vi.mocked(isSpeaking).mockReturnValue(false);
    await vi.advanceTimersByTimeAsync(1000);
    expect(vi.mocked(speak).mock.calls.map(([text]) => text)).toEqual([expect.stringContaining("Bracket is loose")]);
  });

  it("is not spoken late at the next stop when the walker went on while the step line was read", async () => {
    arriveAtFirstStop();
    useTwin.setState({ state: state(route("S1", "S2")), walkStep: null });
    useRound.setState({ index: 1 });
    useTwin.setState({ walkStep: 0 });
    await vi.advanceTimersByTimeAsync(20_000); // past the 15 s wait for the step line
    expect(vi.mocked(speak)).not.toHaveBeenCalled();
  });
});
