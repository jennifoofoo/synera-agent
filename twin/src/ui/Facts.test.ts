import { beforeEach, describe, expect, it } from "vitest";
import type { BuildingState, Fact } from "../api/types";
import type { BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { onReply } from "./Facts";
import { useFacts } from "./factsStore";

const model = {
  spaceById: new Map([["S1", { id: "S1", floor_id: "F1", name: "Hall A2", anchor: [10, 5] }]]),
  assetById: new Map(),
  openingById: new Map(),
  connectorById: new Map(),
  connectorBySpace: new Map(),
  floorById: new Map(),
} as unknown as BuildingModel;

const fact: Fact = {
  id: "f-1",
  kind: "issue",
  anchor: { space_id: "S1", asset_id: null, element_id: null, point: null, floor_id: "F1" },
  text: "Valve drips",
  valid_from: "2026-10-25T08:10:00+01:00",
  valid_to: null,
  status: "open",
  author: "Technician A",
  photo: "/api/facts/photo?key=k&id=f-1",
  created_at: "2026-10-25T08:10:00+01:00",
};

describe("Wanda's reply names facts", () => {
  beforeEach(() => {
    useTwin.setState({ model, state: { closed: [], added_doors: [], route: null, position: null, guide: null, facts: [fact] } as BuildingState, focusedFloorId: "F0" });
    useFacts.setState({ highlighted: [], photo: null, layer: false });
  });

  it("highlights their pins (also with the layer off) and shows their floor", () => {
    onReply({ reply: "There is an open problem: Valve drips.", backend: "x", facts: ["f-1"] }, "what's here?");
    expect(useFacts.getState().highlighted).toEqual(["f-1"]);
    expect(useTwin.getState().focusedFloorId).toBe("F1");
    expect(useTwin.getState().camera.kind).toBe("point");
    expect(useFacts.getState().photo).toBeNull();
  });

  it("'show me the photo' opens the photo of the named fact, or a photo URL in the text", () => {
    onReply({ reply: "Here it is.", backend: "x", facts: [fact] }, "Show me the photo");
    expect(useFacts.getState().photo?.url).toBe(fact.photo);
    useFacts.setState({ photo: null });
    onReply({ reply: "Photo: /api/facts/photo?key=k&id=f-9 taken today.", backend: "x" }, "zeig mir das Foto");
    expect(useFacts.getState().photo?.url).toBe("/api/facts/photo?key=k&id=f-9");
  });

  it("open_photo from the server opens that photo", () => {
    onReply({ reply: "Here.", backend: "x", facts: [fact], open_photo: { fact_id: "f-1", photo_url: "/api/facts/photo?key=k&id=f-1" } }, "can I see it?");
    expect(useFacts.getState().photo).toEqual({ url: "/api/facts/photo?key=k&id=f-1", caption: "Valve drips" });
  });

  it("a reply without facts clears the highlight", () => {
    useFacts.setState({ highlighted: ["f-1"] });
    onReply({ reply: "ok", backend: "x" }, "next");
    expect(useFacts.getState().highlighted).toEqual([]);
  });
});
