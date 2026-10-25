import { describe, expect, it } from "vitest";
import { playWithRetry, spokenText } from "./voice";

describe("playWithRetry", () => {
  it("plays at once when allowed", async () => {
    let calls = 0;
    expect(await playWithRetry(() => (calls++, Promise.resolve()), 1)).toBe(true);
    expect(calls).toBe(1);
  });
  it("retries once after a refused play", async () => {
    let calls = 0;
    const play = () => (calls++ === 0 ? Promise.reject(new Error("NotAllowedError")) : Promise.resolve());
    expect(await playWithRetry(play, 1)).toBe(true);
    expect(calls).toBe(2);
  });
  it("gives up after the second refusal (the page then shows Tap to hear Wanda)", async () => {
    let calls = 0;
    expect(await playWithRetry(() => (calls++, Promise.reject(new Error("NotAllowedError"))), 1)).toBe(false);
    expect(calls).toBe(2);
  });
});

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
