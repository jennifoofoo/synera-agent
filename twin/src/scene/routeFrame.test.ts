// Framing a route inside the free part of the map (routeFrame.ts).
import * as THREE from "three";
import { describe, expect, test } from "vitest";
import type { RouteSegment } from "../api/types";
import { fitPointsInRect, framePad, freeRect, routeFramePoints, withEndMarkers, type Rect } from "./routeFrame";

const phone: Rect = { left: 0, top: 0, right: 390, bottom: 844 };

describe("freeRect", () => {
  test("phone: top bar, rail on the right and the dock with its sheet cut their own sides, plus 24 px", () => {
    const topBar = { left: 8, top: 8, right: 382, bottom: 52 };
    const rail = { left: 334, top: 64, right: 378, bottom: 240 };
    const dock = { left: 0, top: 365, right: 390, bottom: 844 };
    expect(freeRect(phone, [topBar, rail, dock])).toEqual({ left: 24, top: 76, right: 310, bottom: 341 });
  });
  test("laptop: the chat column on the left cuts the left side; hidden or off-canvas UI is ignored", () => {
    const laptop: Rect = { left: 0, top: 0, right: 1440, bottom: 900 };
    const chat = { left: 0, top: 0, right: 400, bottom: 900 };
    const hidden = { left: 10, top: 10, right: 10, bottom: 10 };
    const outside = { left: 1500, top: 0, right: 1600, bottom: 900 };
    expect(freeRect(laptop, [chat, hidden, outside])).toEqual({ left: 424, top: 24, right: 1416, bottom: 876 });
  });
  test("a sheet covering nearly everything falls back to the whole canvas", () => {
    const free = freeRect(phone, [{ left: 0, top: 60, right: 390, bottom: 844 }]);
    expect(free).toEqual({ left: 24, top: 24, right: 366, bottom: 820 });
  });
});

describe("framePad and withEndMarkers", () => {
  test("24 px on a phone, more on a laptop map", () => {
    expect(framePad(390, 664)).toBe(27);
    expect(framePad(320, 500)).toBe(24);
    expect(framePad(1020, 900)).toBe(63);
  });
  test("room for the pin above the route, unless the area would get too small", () => {
    expect(withEndMarkers({ left: 0, top: 76, right: 300, bottom: 341 })).toEqual({ left: 0, top: 120, right: 300, bottom: 341 });
    expect(withEndMarkers({ left: 0, top: 76, right: 300, bottom: 200 })).toEqual({ left: 0, top: 76, right: 300, bottom: 200 });
  });
});

describe("routeFramePoints", () => {
  const segments = [
    { floor_id: "F0", kind: "walk", points: [[0, 0], [20, 0]] },
    { floor_id: "F1", kind: "walk", points: [[20, 0], [20, 30]] },
  ] as unknown as RouteSegment[];
  test("only the shown floor's part, at its height", () => {
    const points = routeFramePoints(segments, "F0", (id) => (id === "F1" ? 4 : 0));
    const box = new THREE.Box3().setFromPoints(points);
    expect(box.max.x).toBe(20);
    expect(box.max.y).toBe(0);
  });
  test("a short route is padded to the minimum span", () => {
    const points = routeFramePoints([{ floor_id: "F0", kind: "walk", points: [[0, 0], [2, 0]] }] as unknown as RouteSegment[], "F0", () => 0);
    const size = new THREE.Box3().setFromPoints(points).getSize(new THREE.Vector3());
    expect(size.x).toBeCloseTo(10);
    expect(size.z).toBeCloseTo(10);
  });
  test("nothing on that floor: no points", () => {
    expect(routeFramePoints(segments, "F9", () => 0)).toEqual([]);
  });
});

/** Where the points land on screen (px) for a camera placed by fitPointsInRect. */
function screenBox(camera: THREE.Camera, points: THREE.Vector3[], size: { width: number; height: number }): Rect {
  const r = { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity };
  for (const point of points) {
    const p = point.clone().project(camera);
    const x = ((p.x + 1) / 2) * size.width;
    const y = ((1 - p.y) / 2) * size.height;
    r.left = Math.min(r.left, x);
    r.right = Math.max(r.right, x);
    r.top = Math.min(r.top, y);
    r.bottom = Math.max(r.bottom, y);
  }
  return r;
}

function apply(camera: THREE.OrthographicCamera | THREE.PerspectiveCamera, fit: NonNullable<ReturnType<typeof fitPointsInRect>>) {
  camera.position.copy(fit.position);
  if (fit.zoom !== undefined) (camera as THREE.OrthographicCamera).zoom = fit.zoom;
  camera.up.set(0, 1, 0);
  camera.lookAt(fit.target);
  camera.updateMatrixWorld(true);
  camera.updateProjectionMatrix();
}

describe("fitPointsInRect", () => {
  const size = { width: 390, height: 844 };
  const free: Rect = { left: 24, top: 76, right: 310, bottom: 341 };
  const route = [new THREE.Vector3(0, 0, -2.7), new THREE.Vector3(5.5, 0, -2.7), new THREE.Vector3(5.5, 0, -17), new THREE.Vector3(2.5, 0, -17)];

  test("2D plan (orthographic): the route fills the free area, start and end inside it", () => {
    const camera = new THREE.OrthographicCamera(-195, 195, 422, -422, 0.1, 1000);
    const fit = fitPointsInRect(camera, route, free, size, 0, 0.004);
    expect(fit?.zoom).toBeGreaterThan(0);
    apply(camera, fit!);
    const box = screenBox(camera, route, size);
    expect(box.left).toBeGreaterThanOrEqual(free.left - 1);
    expect(box.right).toBeLessThanOrEqual(free.right + 1);
    expect(box.top).toBeGreaterThanOrEqual(free.top - 1);
    expect(box.bottom).toBeLessThanOrEqual(free.bottom + 1);
    // tight: the long side (height) is used fully
    expect(box.bottom - box.top).toBeGreaterThan((free.bottom - free.top) * 0.97);
  });

  test("3D (perspective, tilted): inside the free area too", () => {
    const camera = new THREE.PerspectiveCamera(40, size.width / size.height, 0.1, 2000);
    const fit = fitPointsInRect(camera, route, free, size, -Math.PI / 4, Math.PI / 4);
    apply(camera, fit!);
    const box = screenBox(camera, route, size);
    expect(box.left).toBeGreaterThanOrEqual(free.left - 1);
    expect(box.right).toBeLessThanOrEqual(free.right + 1);
    expect(box.top).toBeGreaterThanOrEqual(free.top - 1);
    expect(box.bottom).toBeLessThanOrEqual(free.bottom + 1);
  });

  test("no points: nothing to frame", () => {
    expect(fitPointsInRect(new THREE.PerspectiveCamera(), [], free, size, 0, 1)).toBeNull();
  });
});
