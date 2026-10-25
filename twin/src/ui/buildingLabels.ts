// The building picker shows names only, never the raw keys ("dev/osm-way22744230"). Two buildings with the same
// name get a short number so they can still be told apart: "N3", "N3 · 2".

export function buildingLabels(entries: { key: string; name: string }[]): Map<string, string> {
  const total = new Map<string, number>();
  for (const entry of entries) {
    const name = entry.name.trim() || "Building";
    total.set(name, (total.get(name) ?? 0) + 1);
  }
  const seen = new Map<string, number>();
  const labels = new Map<string, string>();
  for (const entry of entries) {
    const name = entry.name.trim() || "Building";
    const n = (seen.get(name) ?? 0) + 1;
    seen.set(name, n);
    labels.set(entry.key, (total.get(name) ?? 1) > 1 && n > 1 ? `${name} · ${n}` : name);
  }
  return labels;
}
