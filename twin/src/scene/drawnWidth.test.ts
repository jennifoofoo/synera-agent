// Drawing-only clamp of opening widths: absurd data must not produce absurd gaps in the 3D plan.
import { describe, expect, test } from "vitest";
import type { Opening } from "../api/types";
import { drawnWidth } from "./geometry";

const open = (kind: string, width_m: number | undefined): Opening => ({ id: "o", floor_id: "f", space_ids: ["a", "b"], kind, position: [0, 0], width_m, step_free: true }) as unknown as Opening;

describe("drawnWidth", () => {
  test("clamps doors to 0.5 to 5 m", () => {
    expect(drawnWidth(open("door", 500))).toBe(5);
    expect(drawnWidth(open("door", 0.1))).toBe(0.5);
    expect(drawnWidth(open("entrance", 1.8))).toBe(1.8);
  });
  test("missing, zero, negative and NaN fall back to 0.9", () => {
    for (const w of [undefined, 0, -3, Number.NaN]) expect(drawnWidth(open("door", w))).toBe(0.9);
  });
  test("open passages keep kit widths up to 25 m", () => {
    expect(drawnWidth(open("opening", 20))).toBe(20);
    expect(drawnWidth(open("opening", 500))).toBe(25);
  });
});
