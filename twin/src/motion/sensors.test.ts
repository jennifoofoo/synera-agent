import { afterEach, describe, expect, it, vi } from "vitest";
import { motionSupport, needsPermissionPrompt, requestMotionPermission, resetPermissionMemory } from "./sensors";

function fakeBrowser(userAgent: string, permission: "granted" | "denied") {
  const requestPermission = vi.fn(async () => permission);
  vi.stubGlobal("window", { DeviceMotionEvent: { requestPermission }, DeviceOrientationEvent: { requestPermission }, isSecureContext: true });
  vi.stubGlobal("navigator", { userAgent });
  return requestPermission;
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetPermissionMemory();
});

describe("motion permission", () => {
  it("Android: no permission call, ready even if a requestPermission says denied", async () => {
    const ask = fakeBrowser("Mozilla/5.0 (Linux; Android 14; Pixel 7) Chrome/120 Mobile", "denied");
    expect(needsPermissionPrompt()).toBe(false);
    expect(await requestMotionPermission()).toBe("ready");
    expect(ask).not.toHaveBeenCalled();
    expect(motionSupport()).toBe("ready");
  });

  it("iOS: asks, and a refusal is denied", async () => {
    const ask = fakeBrowser("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1", "denied");
    expect(needsPermissionPrompt()).toBe(true);
    expect(await requestMotionPermission()).toBe("denied");
    expect(ask).toHaveBeenCalled();
    expect(motionSupport()).toBe("denied");
  });
});
