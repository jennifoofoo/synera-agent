import { describe, expect, it } from "vitest";
import type { Route } from "../api/types";
import type { BuildingModel } from "../model/model";
import { durationLabel, isCurrent, MemoryFacts, pickFactsStorage, ServerFacts, sinceLabel, whenLabel, type Fact } from "./notes";
import { notesCommand, spacesNamed } from "./notesStore";

const model = {
  spaceById: new Map([
    ["S20", { name: "Meeting room 0.20" }],
    ["S16", { name: "Office corridor 0.16" }],
    ["S25", { name: "Office 0.25" }],
    ["S2", { name: "Office 0.2" }],
  ]),
} as unknown as BuildingModel;

const route = { ok: true, start: "S20", destination: "S25", space_path: ["S20", "S16", "S25"] } as Route;

describe("spacesNamed", () => {
  it("finds the rooms a step line names, by name or by [id]", () => {
    expect(spacesNamed("Walk about 25 m via Office corridor 0.16 into Office 0.25.", route, model)).toEqual(["S16", "S25"]);
    expect(spacesNamed("You have arrived at Office 0.25 [S25] on Ground floor.", route, model)).toEqual(["S25"]);
  });

  it("does not take Office 0.2 for Office 0.25", () => {
    const withShort = { ...route, space_path: ["S20", "S2", "S25"] };
    expect(spacesNamed("Walk into Office 0.25.", withShort, model)).toEqual(["S25"]);
    expect(spacesNamed("Walk into Office 0.2.", withShort, model)).toEqual(["S2"]);
  });
});

describe("labels", () => {
  const now = new Date(2026, 9, 25, 10, 0).getTime();
  it("says today, yesterday or the day", () => {
    expect(whenLabel(new Date(2026, 9, 25, 8, 5).getTime(), now)).toBe("today 08:05");
    expect(whenLabel(new Date(2026, 9, 24, 14, 12).getTime(), now)).toBe("yesterday 14:12");
  });
  it("gives durations in minutes and hours", () => {
    expect(durationLabel(4 * 60_000)).toBe("4 min");
    expect(durationLabel(65 * 60_000)).toBe("1 h 05 min");
  });
});

describe("notesCommand", () => {
  it("leaves everything else to the agent", () => {
    expect(notesCommand("where is the kitchen")).toBeNull();
    expect(notesCommand("next")).toBeNull();
    expect(notesCommand("notebook on the desk?")).toBeNull();
  });
  it("takes note, what's here and finished (English and German)", () => {
    for (const said of ["note: always release the left lever first", "Merk dir: Halterung locker", "what's here?", "Was gibt's hier", "finished", "Fertig"]) {
      expect(notesCommand(said)).not.toBeNull();
    }
  });
});

describe("facts", () => {
  const base: Fact = {
    id: "f-1",
    kind: "issue",
    anchor: { space_id: "S25", asset_id: null, element_id: null, point: null, floor_id: "F0" },
    text: "Valve drips",
    valid_from: new Date(2026, 9, 25, 8, 10).toISOString(),
    valid_to: null,
    status: "open",
    author: "Klaus",
    photo: null,
    created_at: new Date(2026, 9, 25, 8, 10).toISOString(),
  };
  const now = new Date(2026, 9, 25, 10, 0).getTime();

  it("is current while open and inside its time", () => {
    expect(isCurrent(base, now)).toBe(true);
    expect(isCurrent({ ...base, status: "resolved" }, now)).toBe(false);
    expect(isCurrent({ ...base, valid_to: new Date(2026, 9, 25, 9, 0).toISOString() }, now)).toBe(false);
    expect(isCurrent({ ...base, valid_to: new Date(2026, 9, 25, 10, 0).toISOString() }, now)).toBe(false); // exactly valid_to
    expect(isCurrent({ ...base, valid_from: new Date(2026, 9, 25, 11, 0).toISOString() }, now)).toBe(false);
  });

  it("names age and author", () => {
    expect(sinceLabel(base, true, now)).toBe("since today 08:10, by Klaus");
    expect(sinceLabel({ ...base, valid_to: new Date(2026, 9, 26, 18, 0).toISOString() }, false, now)).toBe("since today 08:10 · until tomorrow 18:00");
  });

  it("uses the server when GET /api/facts answers with a list, else this device", async () => {
    const original = globalThis.fetch;
    globalThis.fetch = (async () => new Response(JSON.stringify({ facts: [] }), { status: 200 })) as typeof fetch;
    expect((await pickFactsStorage("b")).kind).toBe("server");
    globalThis.fetch = (async () => new Response("nope", { status: 404 })) as typeof fetch;
    expect((await pickFactsStorage("b")).kind).toBe("local");
    globalThis.fetch = original;
  });

  it("keeps undo and resolve local; history stays", async () => {
    const local = new MemoryFacts();
    const { fact } = await local.add("b", { kind: "note", anchor: base.anchor, text: "Lever left first", author: "Klaus" });
    const resolved = await local.resolve("b", fact.id);
    expect(resolved.status).toBe("resolved");
    expect(resolved.valid_to).not.toBeNull();
    expect((await local.list("b")).length).toBe(1);
  });

  it("saves on the server with {fact, state} and undoes only the newest note", async () => {
    const original = globalThis.fetch;
    const saved = { ...base, id: "f-1", photo: "/api/facts/photo?key=b&id=f-1", author: "Klaus", person_id: "klaus" };
    const calls: string[] = [];
    globalThis.fetch = (async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url === "/api/facts") return new Response(JSON.stringify({ fact: saved, state: { facts: [saved] } }));
      if (url === "/api/facts/undo") return new Response(JSON.stringify({ undone: saved, state: { facts: [] } }));
      return new Response(JSON.stringify({ facts: [saved], persons: [] }));
    }) as typeof fetch;
    const server = new ServerFacts();
    const reply = await server.add("b", { kind: "note", anchor: base.anchor, text: "Lever", author: "Klaus" });
    expect(reply.fact.photo).toBe("/api/facts/photo?key=b&id=f-1");
    expect(reply.state).toEqual({ facts: [saved] });
    expect(await server.undo("b", "f-1")).toEqual({ state: { facts: [] } });
    await expect(server.undo("b", "f-other")).rejects.toThrow();
    expect(calls.filter((c) => c.startsWith("POST"))).toEqual(["POST /api/facts", "POST /api/facts/undo"]);
    expect("resolve" in server).toBe(false);
    globalThis.fetch = original;
  });

  it("takes a spoken problem as an issue", () => {
    expect(notesCommand("problem: valve drips")).not.toBeNull();
    expect(notesCommand("Störung hier: Ventil tropft")).not.toBeNull();
  });
});
