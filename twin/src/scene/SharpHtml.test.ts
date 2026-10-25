import { describe, expect, it } from "vitest";
import { Object3D, OrthographicCamera } from "three";
import { snapPosition } from "./SharpHtml";

describe("snapPosition", () => {
  it("places a label on whole pixels", () => {
    const camera = new OrthographicCamera(-10, 10, 10, -10, 0.1, 100);
    camera.position.set(0, 50, 0);
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld();
    const el = new Object3D();
    el.position.set(1.2345, 0, -3.21);
    el.updateMatrixWorld();
    const [x, y] = snapPosition(el, camera, { width: 1251, height: 803 });
    expect(Number.isInteger(x)).toBe(true);
    expect(Number.isInteger(y)).toBe(true);
    expect(Math.abs(x - (1.2345 / 10) * 625.5 - 625.5)).toBeLessThanOrEqual(0.5);
  });
});
