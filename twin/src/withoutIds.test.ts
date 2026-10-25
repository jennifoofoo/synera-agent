import { describe, expect, it } from "vitest";
import { withoutIds } from "./voice";

describe("withoutIds", () => {
  it("drops a bracketed raw id from a room name", () => {
    expect(withoutIds("Go to Project Room [plan-89323a15-F0-S002].")).toBe("Go to Project Room.");
  });
  it("keeps ordinary words and numbers", () => {
    expect(withoutIds("Take the stairs up to floor 2, then turn left.")).toBe("Take the stairs up to floor 2, then turn left.");
    expect(withoutIds("Walk 12 m past the e-bike stand")).toBe("Walk 12 m past the e-bike stand");
  });
});
