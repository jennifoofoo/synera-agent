import { describe, expect, it } from "vitest";
import type { Route } from "../api/types";
import type { BuildingModel } from "../model/model";
import { durationLabel, whenLabel } from "./notes";
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
