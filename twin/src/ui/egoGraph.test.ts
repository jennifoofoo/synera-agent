import { describe, expect, it } from "vitest";
import { DAY_MS, egoGraph, factStateAt, localId, mainType, momentLabel, spreadOut, timeRange, type LdNode } from "./egoGraph";

const B = "urn:synera:b1";
const room = `${B}:space:S1`;
const now = Date.parse("2026-10-25T10:00:00+01:00");
const iso = (offsetMs: number) => new Date(now + offsetMs).toISOString();

function graph(extraAssets = 0): LdNode[] {
  const assets: LdNode[] = Array.from({ length: extraAssets }, (_, i) => ({
    "@id": `${B}:asset:F${String(i).padStart(2, "0")}`,
    "@type": ["rec:Furniture"],
    name: `Chair ${i}`,
    category: "furniture",
    isLocatedIn: room,
  }));
  return [
    { "@id": `${B}:building:b1`, "@type": ["rec:Building", "brick:Building"], name: "B1" },
    { "@id": room, "@type": ["rec:ProductionRoom", "brick:Space"], name: "Hall A" },
    { "@id": `${B}:space:S2`, "@type": ["rec:Hallway", "brick:Hallway"], name: "Corridor" },
    { "@id": `${B}:asset:M1`, "@type": ["brick:Equipment"], name: "CNC lathe", category: "machine", isLocatedIn: room },
    { "@id": `${B}:asset:X1`, "@type": ["brick:Fire_Extinguisher", "brick:Equipment"], name: "Extinguisher", category: "equipment", isLocatedIn: room },
    { "@id": `${B}:asset:OTHER`, "@type": ["brick:Equipment"], name: "Elsewhere", category: "machine", isLocatedIn: `${B}:space:S2` },
    { "@id": `${B}:opening:D1`, "@type": ["rec:Door", "brick:Door"], kind: "door", connects: [room, `${B}:space:S2`] },
    ...assets,
    { "@id": `${B}:person:marta`, "@type": ["rec:Person", "wanda:Person"], name: "Marta" },
    {
      "@id": `${B}:fact:f-1`,
      "@type": ["wanda:Fact", "wanda:Note"],
      kind: "note",
      text: "Coolant leak",
      validFrom: iso(-DAY_MS),
      anchoredAt: [`${B}:asset:M1`],
      isLocatedIn: room,
      reportedBy: `${B}:person:marta`,
    },
    {
      "@id": `${B}:fact:f-2`,
      "@type": ["wanda:Fact", "wanda:Note"],
      kind: "note",
      text: "Forklift in the aisle until tomorrow",
      validFrom: iso(-60_000),
      validTo: iso(DAY_MS),
      anchoredAt: [room],
      isLocatedIn: room,
      reportedBy: `${B}:person:marta`,
    },
    { "@id": `${B}:fact:f-3`, "@type": ["wanda:Fact", "wanda:Issue"], kind: "issue", text: "resolved", validFrom: iso(-1000), validTo: iso(-1000), resolves: `${B}:fact:f-9`, anchoredAt: [room] },
    { "@id": `${B}:fact:f-4`, "@type": ["wanda:Fact", "wanda:Note"], kind: "note", text: "Other room", validFrom: iso(-1000), anchoredAt: [`${B}:asset:OTHER`], isLocatedIn: `${B}:space:S2` },
  ];
}

describe("factStateAt", () => {
  const fact: LdNode = { "@id": "f", validFrom: iso(0), validTo: iso(DAY_MS) };
  it("is future before validFrom, open in between, ended from validTo on", () => {
    expect(factStateAt(fact, now - 1)).toBe("future");
    expect(factStateAt(fact, now)).toBe("open");
    expect(factStateAt(fact, now + DAY_MS)).toBe("ended");
    expect(factStateAt({ "@id": "g", validFrom: iso(0) }, now + 100 * DAY_MS)).toBe("open");
  });
  it("never draws a resolving fact", () => {
    expect(factStateAt({ "@id": "r", resolves: "x", validFrom: iso(0) }, now)).toBe("resolving");
  });
});

describe("egoGraph", () => {
  it("puts the room in the centre, its assets and doors in ring 1, facts in ring 2 and reporters in ring 3", () => {
    const ego = egoGraph(graph(), "S1", { at: now });
    const ids = (ring: number) => ego.nodes.filter((n) => n.ring === ring).map((n) => localId(n.id));
    expect(ids(0)).toEqual(["S1"]);
    expect(ids(1).sort()).toEqual(["D1", "M1", "X1"]);
    expect(ids(2).sort()).toEqual(["f-1", "f-2"]);
    expect(ids(3)).toEqual(["marta"]);
    const edge = (from: string, to: string) => ego.edges.some((e) => localId(e.from) === from && localId(e.to) === to);
    expect(edge("M1", "f-1")).toBe(true);
    expect(edge("S1", "f-2")).toBe(true);
    expect(edge("f-1", "marta")).toBe(true);
    expect(ego.nodes.find((n) => localId(n.id) === "M1")?.hasFacts).toBe(true);
    expect(ego.nodes.find((n) => localId(n.id) === "D1")?.label).toBe("Door to Corridor");
    expect(ego.nodes.find((n) => localId(n.id) === "f-1")).toMatchObject({ number: 1, person: "Marta", anchor: "CNC lathe", role: "note" });
    expect(ego.oldest).toBe(now - DAY_MS);
  });

  it("hides a fact after its validTo, or fades it with showEnded, and hides facts not yet valid", () => {
    const later = egoGraph(graph(), "S1", { at: now + 2 * DAY_MS });
    expect(later.nodes.some((n) => localId(n.id) === "f-2")).toBe(false);
    expect(later.nodes.some((n) => localId(n.id) === "f-1")).toBe(true);
    const faded = egoGraph(graph(), "S1", { at: now + 2 * DAY_MS, showEnded: true });
    expect(faded.nodes.find((n) => localId(n.id) === "f-2")?.state).toBe("ended");
    expect(faded.edges.find((e) => localId(e.to) === "f-2")?.faded).toBe(true);
    const before = egoGraph(graph(), "S1", { at: now - 2 * DAY_MS });
    expect(before.nodes.filter((n) => n.ring >= 2)).toEqual([]);
  });

  it("caps ring 1 with a +N node and keeps the nodes that carry facts", () => {
    const ego = egoGraph(graph(30), "S1", { at: now, cap: 16 });
    const ring1 = ego.nodes.filter((n) => n.ring === 1);
    expect(ring1).toHaveLength(16);
    expect(ego.more).toBe(33 - 15);
    expect(ring1.at(-1)?.label).toBe(`+${33 - 15}`);
    expect(ring1.some((n) => localId(n.id) === "M1")).toBe(true);
  });

  it("keeps every node inside the drawing area", () => {
    const ego = egoGraph(graph(30), "S1", { at: now, width: 360, height: 300 });
    for (const node of ego.nodes) {
      expect(node.x).toBeGreaterThanOrEqual(0);
      expect(node.x).toBeLessThanOrEqual(360);
      expect(node.y).toBeGreaterThanOrEqual(0);
      expect(node.y).toBeLessThanOrEqual(300);
    }
  });

  it("returns an empty graph for an unknown room", () => {
    expect(egoGraph(graph(), "nope", { at: now }).nodes).toEqual([]);
  });
});

describe("labels and range", () => {
  it("picks the specific type for the tag", () => {
    expect(mainType(["brick:Fire_Extinguisher", "brick:Equipment"])).toBe("brick:Fire_Extinguisher");
    expect(mainType(["brick:Equipment"])).toBe("brick:Equipment");
    expect(mainType(["wanda:Fact", "wanda:Note"])).toBe("wanda:Note");
  });
  it("ranges from the oldest fact (at least a day back) to three days ahead", () => {
    const { min, max } = timeRange(now - 5 * DAY_MS, now);
    expect(min).toBeLessThanOrEqual(now - 5 * DAY_MS);
    expect(max).toBeGreaterThanOrEqual(now + 3 * DAY_MS);
    expect(timeRange(null, now).min).toBeLessThanOrEqual(now - DAY_MS);
  });
  it("says Now, Tomorrow or the date", () => {
    expect(momentLabel(now, now)).toBe("Now");
    expect(momentLabel(now + DAY_MS, now)).toMatch(/^Tomorrow /);
  });
});

describe("spreadOut", () => {
  it("puts flagged items on evenly spaced slots", () => {
    expect(spreadOut([1, 2, 3, 4, 5, 6], (n) => n <= 2)).toEqual([1, 3, 4, 2, 5, 6]);
    expect(spreadOut([1, 2], () => true)).toEqual([1, 2]);
  });
});
