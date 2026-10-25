import { describe, expect, it } from "vitest";
import { DAY_MS, QUIET_SHOWN, egoGraph, factStateAt, localId, mainType, momentLabel, spreadOut, timeRange, wrapLabel, type LdNode } from "./egoGraph";

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

/** The same room without any note (facts dropped), plus lifts/stairs and extra doors. */
function quietGraph(extraAssets = 0, extraDoors = 0): LdNode[] {
  const doors: LdNode[] = Array.from({ length: extraDoors }, (_, i) => ({
    "@id": `${B}:opening:E${i}`,
    "@type": ["rec:Door", "brick:Door"],
    connects: [room, `${B}:space:S2`],
  }));
  const stairs: LdNode = { "@id": `${B}:connector:ST1`, "@type": ["rec:Stairs", "brick:Stairs"], name: "Stairs East", connects: [room, `${B}:space:S2`] };
  return [...graph(extraAssets).filter((n) => !(n["@type"] as string[]).includes("wanda:Fact")), ...doors, stairs];
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
  it("puts the room in the centre, what carries a note in ring 1 (rest collapsed), facts in ring 2 and reporters in ring 3", () => {
    const ego = egoGraph(graph(), "S1", { at: now });
    const ids = (ring: number) => ego.nodes.filter((n) => n.ring === ring).map((n) => (n.role === "more" ? "more" : localId(n.id)));
    expect(ids(0)).toEqual(["S1"]);
    expect(ids(1)).toEqual(["M1", "more"]); // the extinguisher and the door carry no note
    expect(ego.more).toBe(2);
    expect(ego.moreItems.map((i) => i.label).sort()).toEqual(["Door to Corridor", "Extinguisher"]);
    expect(ids(2).sort()).toEqual(["f-1", "f-2"]);
    expect(ids(3)).toEqual(["marta"]);
    const edge = (from: string, to: string) => ego.edges.some((e) => localId(e.from) === from && localId(e.to) === to);
    expect(edge("M1", "f-1")).toBe(true);
    expect(edge("S1", "f-2")).toBe(true);
    expect(edge("f-1", "marta")).toBe(true);
    expect(ego.nodes.find((n) => localId(n.id) === "M1")?.hasFacts).toBe(true);
    expect(ego.nodes.find((n) => n.role === "more")?.label).toBe("+2 more");
    expect(ego.nodes.find((n) => localId(n.id) === "f-1")).toMatchObject({ number: 1, person: "Marta", anchor: "CNC lathe", role: "note" });
    expect(ego.oldest).toBe(now - DAY_MS);
  });

  it("shows an event in ring 2 only once the time slider reaches its start (docs/specs/events.md)", () => {
    const event: LdNode = { "@id": `${B}:fact:f-7`, "@type": ["wanda:Fact", "wanda:Event"], kind: "event", text: "Pitches", validFrom: iso(4 * 3_600_000), validTo: iso(6 * 3_600_000), anchoredAt: [room], isLocatedIn: room };
    const ring2 = (at: number) => egoGraph([...graph(), event], "S1", { at }).nodes.filter((n) => n.ring === 2);
    expect(ring2(now).some((n) => localId(n.id) === "f-7")).toBe(false);
    expect(ring2(now + 5 * 3_600_000).find((n) => localId(n.id) === "f-7")).toMatchObject({ role: "event", state: "open", text: "Pitches" });
    expect(ring2(now + 7 * 3_600_000).some((n) => localId(n.id) === "f-7")).toBe(false); // ended and hidden by default
  });

  it("keeps lifts and stairs in ring 1 next to the noted things, and a note on a door brings the door out", () => {
    const withStairs = [...graph(), { "@id": `${B}:connector:ST1`, "@type": ["rec:Stairs", "brick:Stairs"], name: "Stairs East", connects: [room, `${B}:space:S2`] } as LdNode];
    const ring1 = egoGraph(withStairs, "S1", { at: now }).nodes.filter((n) => n.ring === 1 && n.role !== "more");
    expect(ring1.map((n) => n.label).sort()).toEqual(["CNC lathe", "Stairs East"]);
    const noteOnDoor: LdNode = { "@id": `${B}:fact:f-5`, "@type": ["wanda:Fact", "wanda:Note"], kind: "note", text: "Door sticks", validFrom: iso(-1000), anchoredAt: [`${B}:opening:D1`], isLocatedIn: room };
    const labels = egoGraph([...graph(), noteOnDoor], "S1", { at: now }).nodes.filter((n) => n.ring === 1).map((n) => n.label);
    expect(labels).toContain("Door to Corridor");
  });

  it("collapses everything else into one +N more node, however many things the room holds", () => {
    const ego = egoGraph(graph(30), "S1", { at: now });
    const ring1 = ego.nodes.filter((n) => n.ring === 1);
    expect(ring1.map((n) => n.role)).toEqual(["asset", "more"]);
    expect(ego.more).toBe(33 - 1);
    expect(ego.moreItems).toHaveLength(32);
    expect(ring1.at(-1)?.label).toBe("+32 more");
  });

  it("shows the 6 most relevant things with names when the room has no notes: lifts/stairs, doors, safety first", () => {
    const ego = egoGraph(quietGraph(10, 3), "S1", { at: now });
    const ring1 = ego.nodes.filter((n) => n.ring === 1 && n.role !== "more");
    expect(ring1).toHaveLength(QUIET_SHOWN);
    expect(ring1[0].label).toBe("Stairs East");
    expect(ring1.filter((n) => n.role === "door")).toHaveLength(4); // D1 and three more
    expect(ring1.map((n) => n.label)).toContain("Extinguisher");
    expect(ring1.every((n) => n.label.length > 0 && !n.hasFacts)).toBe(true);
    expect(ego.more).toBe(17 - QUIET_SHOWN); // 17 things around the room, 6 shown
    expect(ego.nodes.filter((n) => n.ring >= 2)).toEqual([]);
  });

  it("has no +N more node when everything fits", () => {
    const small = quietGraph().filter((n) => n["@id"] !== `${B}:asset:M1`);
    const ego = egoGraph(small, "S1", { at: now });
    expect(ego.more).toBe(0);
    expect(ego.nodes.some((n) => n.role === "more")).toBe(false);
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

  it("keeps every node inside the viewBox, which follows the node count", () => {
    for (const data of [graph(30), quietGraph(10, 12), graph()]) {
      const ego = egoGraph(data, "S1", { at: now, width: 360 });
      for (const node of ego.nodes) {
        expect(node.x).toBeGreaterThanOrEqual(0);
        expect(node.x).toBeLessThanOrEqual(360);
        expect(node.y).toBeGreaterThanOrEqual(ego.view.y);
        expect(node.y).toBeLessThanOrEqual(ego.view.y + ego.view.height);
      }
    }
    const small = egoGraph(graph(), "S1", { at: now, width: 360 });
    const big = egoGraph(quietGraph(10, 12), "S1", { at: now, width: 360 });
    expect(small.view.width).toBe(360);
    expect(small.view.height).toBeLessThan(big.view.height + 1);
    expect(small.view.height).toBeLessThan(300);
  });

  it("puts labels outside: left of nodes on the left half, right of nodes on the right half, never cut", () => {
    const ego = egoGraph(quietGraph(10, 12), "S1", { at: now, width: 360 });
    for (const node of ego.nodes.filter((n) => n.ring === 1)) {
      expect(node.side).toBe(node.x >= 180 ? "right" : "left");
      expect(node.lines?.length).toBeLessThanOrEqual(2);
      expect(node.lines?.join("").includes("…")).toBe(false);
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

describe("wrapLabel", () => {
  it("keeps short labels on one line and wraps long ones to two balanced lines without cutting", () => {
    expect(wrapLabel("Chair", 16)).toEqual(["Chair"]);
    expect(wrapLabel("Fire alarm call point 0.04", 16)).toEqual(["Fire alarm", "call point 0.04"]);
    expect(wrapLabel("Door to Flur Nord Ost", 12)).toEqual(["Door to Flur", "Nord Ost"]);
  });
  it("never uses an ellipsis, even for one long word", () => {
    const lines = wrapLabel("Extinguisher_0000000000000001", 12);
    expect(lines).toHaveLength(2);
    expect(lines.join("")).not.toContain("…");
    expect(lines.join("").replace("-", "")).toContain("Extinguisher");
  });
  it("splits after - _ and /", () => {
    expect(wrapLabel("plan-89323a15-A00007-extra", 10).length).toBe(2);
  });
});

describe("spreadOut", () => {
  it("puts flagged items on evenly spaced slots", () => {
    expect(spreadOut([1, 2, 3, 4, 5, 6], (n) => n <= 2)).toEqual([1, 3, 4, 2, 5, 6]);
    expect(spreadOut([1, 2], () => true)).toEqual([1, 2]);
  });
});
