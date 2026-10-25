import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api/client";
import type { Building, BuildingState, ChatReply } from "./api/types";
import type { BuildingModel } from "./model/model";
import { useTwin } from "./store";

const floors = [
  { id: "F0", level: 0, name: "Ground floor" },
  { id: "F1", level: 1, name: "Floor 1" },
];
const spaces = [
  { id: "S1", name: "Foyer", floor_id: "F0" },
  { id: "S2", name: "Kitchenette", floor_id: "F1" },
];
const emptyState = { closed: [], added_doors: [], route: null, position: null } as unknown as BuildingState;

function setup() {
  const building = { key: "b", floors, spaces, assets: [], openings: [], connectors: [] } as unknown as Building;
  const model = {
    building,
    floors,
    spaceById: new Map(spaces.map((s) => [s.id, s])),
    assetById: new Map(),
    openingById: new Map(),
    connectorById: new Map(),
  } as unknown as BuildingModel;
  useTwin.setState({ buildingKey: "b", building, model, state: emptyState, highlights: {}, focusedFloorId: "F0", chat: [] });
}

const reply = (extra: Partial<ChatReply>): ChatReply =>
  ({ reply: "The kitchen is the Kitchenette on Floor 1.", located: [], state: emptyState, ...extra }) as ChatReply;

describe("ask shows the rooms a reply names", () => {
  afterEach(() => vi.restoreAllMocks());

  it("highlights the named room and switches to its floor", async () => {
    setup();
    vi.spyOn(api, "chat").mockResolvedValue(
      reply({ located_spaces: [{ space_id: "S2", space_name: "Kitchenette", floor_id: "F1", floor_level: 1 }] }),
    );
    await useTwin.getState().ask("Where is the kitchen?");
    const s = useTwin.getState();
    expect(s.highlights.found?.ids).toEqual(["S2"]);
    expect(s.focusedFloorId).toBe("F1");
    expect(s.camera).toMatchObject({ kind: "object", ids: ["S2"] });
  });

  it("keeps an 'I'm here' tapped while the reply was on its way, and sends it with the next message", async () => {
    setup();
    let finish: (value: ChatReply) => void = () => {};
    const chat = vi.spyOn(api, "chat").mockImplementationOnce(() => new Promise((resolve) => (finish = resolve)));
    const first = useTwin.getState().ask("Where is the nearest toilet?");
    useTwin.getState().setHere({ space_id: "S1", floor_id: "F0" });
    finish(reply({ reply: "Where are you?" }));
    await first;
    expect(useTwin.getState().state?.position?.space_id).toBe("S1");
    chat.mockResolvedValueOnce(reply({}));
    await useTwin.getState().ask("Where is the nearest toilet?");
    expect(chat.mock.calls[1][2]?.here).toEqual({ space_id: "S1", floor_id: "F0" });
  });

  it("ignores rooms the model does not know and a reply without rooms", async () => {
    setup();
    vi.spyOn(api, "chat").mockResolvedValue(
      reply({ located_spaces: [{ space_id: "nope", space_name: "x", floor_id: "F1", floor_level: 1 }] }),
    );
    await useTwin.getState().ask("Where is x?");
    expect(useTwin.getState().highlights.found).toBeUndefined();
    expect(useTwin.getState().focusedFloorId).toBe("F0");
  });
});
