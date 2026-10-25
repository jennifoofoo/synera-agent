// The stop header on the step sheet: one Done only. On a leg's last step the sheet's own Done checks the stop, so the
// header leaves its Done out (the video showed a grey Done in the header and a blue one below).
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { RoundBar } from "../ui/Round";
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
