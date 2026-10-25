import { describe, expect, it } from "vitest";
import { buildingLabels } from "./buildingLabels";

describe("buildingLabels", () => {
  it("shows names only and numbers duplicates", () => {
    const labels = buildingLabels([
      { key: "dev/osm-way22744230", name: "N3" },
      { key: "user/plan-89323a15", name: "Munich Urban Colab" },
      { key: "train/osm-way1", name: "N3" },
      { key: "dev/x", name: "" },
    ]);
    expect([...labels.values()]).toEqual(["N3", "Munich Urban Colab", "N3 · 2", "Building"]);
    for (const label of labels.values()) expect(label).not.toMatch(/osm-way|plan-|\//);
  });
});
