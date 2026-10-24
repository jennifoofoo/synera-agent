import { useTwin } from "../store";

/** Top left: the building's name; tapping it changes the building. Nothing else up here. */
export function TopBar() {
  const buildings = useTwin((s) => s.buildings);
  const buildingKey = useTwin((s) => s.buildingKey);
  const building = useTwin((s) => s.building);
  const openBuilding = useTwin((s) => s.openBuilding);
  return (
    <div className="topbar">
      <label className="building-name">
        <span className="brand-mark" aria-hidden />
        <span className="building-title">{building?.name ?? "Building"}</span>
        <select value={buildingKey ?? ""} onChange={(event) => void openBuilding(event.target.value)} aria-label="Building">
          {buildings.map((entry) => (
            <option key={entry.key} value={entry.key}>
              {entry.name} ({entry.key})
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
