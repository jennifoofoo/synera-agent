import { describe, expect, it } from "vitest";
import { classifyTwoFinger, distanceToOrthoZoom, type FingerPair, HANDOVER_POLAR, orthoZoomToDistance, tiltForSwipe } from "./twoFinger";

const start: FingerPair = [
  [150, 400],
  [250, 400],
];
const move = (dA: [number, number], dB: [number, number]): FingerPair => [
  [start[0][0] + dA[0], start[0][1] + dA[1]],
  [start[1][0] + dB[0], start[1][1] + dB[1]],
];

describe("classifyTwoFinger", () => {
  it("pure pinch out and in is a pinch", () => {
    expect(classifyTwoFinger(start, move([-20, 0], [20, 0]))).toBe("pinch");
    expect(classifyTwoFinger(start, move([15, 0], [-15, 0]))).toBe("pinch");
  });

  it("pinch while sliding slightly up is a pinch, never a tilt", () => {
    expect(classifyTwoFinger(start, move([-15, -30], [15, -30]))).toBe("pinch");
    expect(classifyTwoFinger(start, move([-8, -60], [8, -60]))).toBe("pinch");
  });

  it("one finger up, the other still (a pinch on a diagonal) is not a tilt", () => {
    expect(classifyTwoFinger(start, move([0, -60], [0, 0]))).not.toMatch(/tilt/);
  });

  it("both fingers parallel up is tilt-up, down is tilt-down", () => {
    expect(classifyTwoFinger(start, move([0, -40], [0, -40]))).toBe("tilt-up");
    expect(classifyTwoFinger(start, move([3, -120], [2, -118]))).toBe("tilt-up");
    expect(classifyTwoFinger(start, move([0, 40], [0, 40]))).toBe("tilt-down");
  });

  it("both fingers parallel sideways or diagonal is a pan", () => {
    expect(classifyTwoFinger(start, move([60, 0], [60, 0]))).toBe("pan");
    expect(classifyTwoFinger(start, move([-40, 0], [-40, 0]))).toBe("pan");
    expect(classifyTwoFinger(start, move([30, -40], [30, -40]))).toBe("pan");
  });

  it("turning the fingers is a pinch (rotate), never a tilt", () => {
    // Turn about 20 degrees around the midpoint while drifting up.
    const c = 200;
    const r = 50;
    const a = (20 * Math.PI) / 180;
    const turned: FingerPair = [
      [c - r * Math.cos(a), 370 - r * Math.sin(a)],
      [c + r * Math.cos(a), 370 + r * Math.sin(a)],
    ];
    expect(classifyTwoFinger(start, turned)).toBe("pinch");
  });

  it("too short a way is undecided", () => {
    expect(classifyTwoFinger(start, move([0, -10], [0, -10]))).toBe("undecided");
    expect(classifyTwoFinger(start, move([0, -23], [0, -23]))).toBe("undecided");
    expect(classifyTwoFinger(start, start)).toBe("undecided");
  });

  it("fingers on top of each other are treated as a pinch", () => {
    expect(
      classifyTwoFinger(
        [
          [200, 400],
          [200, 400],
        ],
        [
          [200, 300],
          [200, 300],
        ],
      ),
    ).toBe("pinch");
  });
});

describe("zoom and distance", () => {
  it("round trips", () => {
    for (const fov of [32, 38]) {
      for (const zoom of [0.5, 4, 17.3, 120]) {
        const d = orthoZoomToDistance(zoom, 915, fov);
        expect(distanceToOrthoZoom(d, 915, fov)).toBeCloseTo(zoom, 9);
      }
    }
  });

  it("keeps the metres per pixel in the image centre", () => {
    const zoom = 10; // 10 px per metre
    const frame = 800;
    const d = orthoZoomToDistance(zoom, frame, 38);
    const visibleMetres = 2 * d * Math.tan((19 * Math.PI) / 180);
    expect(visibleMetres).toBeCloseTo(frame / zoom, 9);
  });

  it("zooming in brings the 3D camera closer", () => {
    expect(orthoZoomToDistance(20, 800, 32)).toBeLessThan(orthoZoomToDistance(10, 800, 32));
  });
});

describe("tiltForSwipe", () => {
  it("starts at the handover angle, grows with the swipe and stops at the limit", () => {
    expect(tiltForSwipe(0, 1)).toBe(HANDOVER_POLAR);
    expect(tiltForSwipe(-50, 1)).toBe(HANDOVER_POLAR);
    expect(tiltForSwipe(50, 1)).toBeCloseTo(HANDOVER_POLAR + 0.3, 9);
    expect(tiltForSwipe(10000, 1)).toBe(1);
  });
});
