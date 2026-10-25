// The stop header on the step sheet: one Done only. On a leg's last step the sheet's own Done checks the stop, so the
// header leaves its Done out (the video showed a grey Done in the header and a blue one below).
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { useNotes } from "../notes/notesStore";
import { useTwin } from "../store";
import { RoundBar, RoundCard } from "../ui/Round";
import { useRound, type RoundPlan } from "./round";

const plan: RoundPlan = {
  building: "b",
  type: "fire_extinguisher",
  area: "Floor 3",
  startId: "S0",
  startName: "Main Stairs",
  startPoint: null,
  stops: [{ key: "A1", spaceId: "S1", floorId: "F3", name: "Corridor", device: "Fire extinguisher 3.02", assetIds: ["A1"], position: null }],
  lengthM: 10,
  unreachable: [],
  returnToStart: false,
};

describe("RoundBar", () => {
  it("shows Done in the header only when the sheet has no Done of its own", () => {
    useRound.setState({ plan, guiding: true, index: 0, returning: false, busy: null });
    // a server render reads the store's initial state object: give it the walked round for this test, then put it back
    const initial = useRound.getInitialState();
    const kept = { ...initial };
    Object.assign(initial, useRound.getState());
    expect(renderToStaticMarkup(<RoundBar />)).toContain(">Done<");
    const lastStep = renderToStaticMarkup(<RoundBar done={false} />);
    expect(lastStep).not.toContain(">Done<");
    expect(lastStep).toContain("Fire extinguisher 3.02");
    Object.assign(initial, kept);
  });
});

/** Server render reads each store's initial state object: point it at the current state for one render. */
function rendered(node: JSX.Element, stores: { getInitialState: () => object; getState: () => object }[]): string {
  const kept = stores.map((store) => ({ ...store.getInitialState() }));
  stores.forEach((store) => Object.assign(store.getInitialState(), store.getState()));
  try {
    return renderToStaticMarkup(node);
  } finally {
    stores.forEach((store, i) => Object.assign(store.getInitialState(), kept[i]));
  }
}

describe("RoundCard", () => {
  it("steps aside while the job report is open (the report sheet would be hidden under it)", () => {
    const building = { key: "b", name: "B", floors: [], spaces: [], assets: [], openings: [], connectors: [] };
    useTwin.setState({ buildingKey: "b", building: building as never, model: { building, spaceById: new Map(), assetById: new Map() } as never, walkStep: null });
    useRound.setState({ open: true, plan, guiding: false, finished: true, busy: null, error: null });
    useNotes.setState({ report: null });
    expect(rendered(<RoundCard />, [useTwin, useRound, useNotes])).toContain("Inspection round");
    useNotes.setState({ report: { round: null } as never });
    expect(rendered(<RoundCard />, [useTwin, useRound, useNotes])).toBe("");
    useNotes.setState({ report: null });
  });
});
