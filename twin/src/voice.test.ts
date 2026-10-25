import { describe, expect, it } from "vitest";
import { spokenText } from "./voice";

describe("spokenText", () => {
  it("strips bracketed ids from the caption", () => {
    expect(spokenText("Go to Project Room [plan-89323a15-F0-S002].")).toBe("Go to Project Room.");
    expect(spokenText("Project Room [plan-89323a15-F0-S002]")).toBe("Project Room");
    expect(spokenText("Project Room [space plan-89323a15-F0-S002] on Ground floor")).toBe("Project Room on Ground floor");
    expect(spokenText("WC [F0-S020, F0-S021] is close")).toBe("WC is close");
  });
  it("leaves the Answer line out", () => {
    expect(spokenText("The toilet is 12 m away.\nAnswer: S020")).toBe("The toilet is 12 m away.");
  });
});
