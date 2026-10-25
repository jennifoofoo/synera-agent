// Label rules (docs/specs/label-rules.md): run with `npm test` in twin/ (vitest).
import { describe, expect, test } from "vitest";
import { LABEL_PRIORITY, blocked, byPriority, capped, decide, densityBudget, densityCap, overlapPx, rankOfClass, zoomStepChanged, type Box, type LabelClass } from "./labelRules";

const box = (x: number, y: number, w = 40, h = 16): Box => ({ x0: x, y0: y, x1: x + w, y1: y + h });
const H = { hold: 2, reveal: 3 };

describe("priority", () => {
  test("the spec's order, destination first, furniture last of the names", () => {
    const spec: LabelClass[] = ["destination", "here", "selected", "roundStop", "landmark", "zone", "poi", "room", "machine", "furniture"];
    const ranks = spec.map(rankOfClass);
    expect([...ranks].sort((a, b) => a - b)).toEqual(ranks);
    expect(rankOfClass("marker")).toBeLessThan(rankOfClass("destination"));
    expect(rankOfClass("detail")).toBe(LABEL_PRIORITY.length - 1);
  });

  test("unknown classes rank as room names", () => {
    expect(rankOfClass(undefined)).toBe(rankOfClass("room"));
    expect(rankOfClass("whatever")).toBe(rankOfClass("room"));
  });

  test("sort is by rank, then by id, whatever the input order", () => {
    const items: [LabelClass, string][] = [["room", "b"], ["furniture", "a"], ["destination", "z"], ["room", "a"], ["zone", "c"]];
    const sorted = byPriority(items, (i) => i[0], (i) => i[1]);
    expect(sorted.map((i) => i.join(":"))).toEqual(["destination:z", "zone:c", "room:a", "room:b", "furniture:a"]);
    expect(byPriority([...items].reverse(), (i) => i[0], (i) => i[1])).toEqual(sorted);
  });

  test("the cap never drops what the task names", () => {
    for (const c of ["destination", "here", "selected", "roundStop", "landmark", "found", "closure", "marker"] as const) expect(capped(c)).toBe(false);
    for (const c of ["zone", "poi", "room", "machine", "furniture", "detail"] as const) expect(capped(c)).toBe(true);
  });
});

describe("overlap hysteresis", () => {
  test("overlap is the smaller axis, negative for a gap", () => {
    expect(overlapPx(box(0, 0), box(30, 10))).toBe(6);
    expect(overlapPx(box(0, 0), box(45, 0))).toBe(-5);
  });

  test("a shown label stays until clearly covered", () => {
    expect(blocked(box(0, 0), box(38, 0), true, H)).toBe(false); // 2 px: held
    expect(blocked(box(0, 0), box(37, 0), true, H)).toBe(true); // 3 px: gone
  });

  test("a hidden label needs a clear margin to come back", () => {
    expect(blocked(box(0, 0), box(42, 0), false, H)).toBe(true); // only 2 px apart
    expect(blocked(box(0, 0), box(43, 0), false, H)).toBe(false); // 3 px apart
  });

  test("between the two thresholds the last state stays: no flicker", () => {
    const a = box(0, 0);
    const b = box(41, 0); // 1 px apart
    expect(blocked(a, b, true, H)).toBe(false);
    expect(blocked(a, b, false, H)).toBe(true);
  });
});

describe("zoom step", () => {
  test("only a zoom of more than 15 % counts; the first decision always counts", () => {
    expect(zoomStepChanged(0.2, null)).toBe(true);
    expect(zoomStepChanged(0.2, 0.2)).toBe(false);
    expect(zoomStepChanged(0.2 * 1.14, 0.2)).toBe(false);
    expect(zoomStepChanged(0.2 / 1.14, 0.2)).toBe(false);
    expect(zoomStepChanged(0.2 * 1.16, 0.2)).toBe(true);
    expect(zoomStepChanged(0.2 / 1.16, 0.2)).toBe(true);
  });
});

describe("Töpfer density cap", () => {
  test("labels grow with the square root of the zoom", () => {
    expect(densityCap(0.3)).toBe(6);
    const ratio = densityCap(0.3 / 4) / densityCap(0.3); // four times closer: twice as many
    expect(ratio).toBe(2);
    expect(densityCap(0.15) / densityCap(0.3)).toBeCloseTo(Math.SQRT2, 0);
    expect(densityCap(100)).toBe(1);
  });

  test("the budget counts per fixed cell", () => {
    const budget = densityBudget(0.3, 100);
    for (let i = 0; i < 6; i++) expect(budget.take(box(10 + i, 10, 4, 4))).toBe(true);
    expect(budget.take(box(20, 20, 4, 4))).toBe(false); // the cell is full
    expect(budget.take(box(120, 20, 4, 4))).toBe(true); // the next cell is not
  });
});

describe("decide", () => {
  const item = (id: string, x: number, shown = false) => ({ item: id, box: box(x, 0), shown });

  test("the higher ranked label wins, whatever was drawn first", () => {
    const kept = decide([item("dest", 0), item("room", 10, true)], { hysteresis: H });
    expect([...kept]).toEqual(["dest"]);
  });

  test("markers are never covered", () => {
    expect(decide([item("room", 0)], { fixed: [box(10, 0)], hysteresis: H }).size).toBe(0);
  });

  test("the cap drops the lowest ranked first", () => {
    const budget = densityBudget(100); // cap 1 per cell
    const kept = decide([item("zone", 0), item("room", 60), item("machine", 120)], { hysteresis: H, budget, isCapped: () => true });
    expect([...kept]).toEqual(["zone"]);
  });

  test("same input, same decision (stable)", () => {
    const items = [item("a", 0), item("b", 30), item("c", 60), item("d", 90)];
    const once = [...decide(items, { hysteresis: H })];
    expect([...decide(items, { hysteresis: H })]).toEqual(once);
  });
});
