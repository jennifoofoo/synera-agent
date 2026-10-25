import { describe, expect, it } from "vitest";
import { isForgetHere } from "./forgetHere";

describe("isForgetHere", () => {
  it("matches the plain command, typed or spoken", () => {
    for (const m of ["Forget where I am", "forget where I am.", "Forget my position", "please forget my location", "Vergiss wo ich bin", "clear the blue dot"]) {
      expect(isForgetHere(m), m).toBe(true);
    }
  });
  it("leaves other messages to the agent", () => {
    for (const m of ["I'm not there any more", "Forget where I am, I'm in Kitchen 1.30", "Where am I?", "forget it"]) {
      expect(isForgetHere(m), m).toBe(false);
    }
  });
});
