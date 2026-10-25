import { describe, expect, it } from "vitest";
import { thenLine } from "./FollowRoute";

describe("thenLine", () => {
  it("drops the distance so the badge never shows a second number next to the sheet's", () => {
    expect(thenLine("Walk about 16 m through the opening into Main aisle H-B2.")).toBe("Then: through the opening");
  });

  it("keeps lines that are not a walk", () => {
    expect(thenLine("Turn left at the stairs.")).toBe("Then: turn left at the stairs");
  });
});
