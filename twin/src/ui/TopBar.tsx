import { useEffect, useMemo } from "react";
import { CampusBack } from "../campus/CampusBack";
import { useCampus } from "../campus/campusStore";
import { useTwin } from "../store";
import { useNewBuilding } from "./newBuildingStore";
import { usePlannerList } from "./Planner";
import { buildingLabels } from "./buildingLabels";

/** Top left: the building's name; tapping it changes the building. Nothing else up here. */
export function TopBar() {
  const buildings = useTwin((s) => s.buildings);
  const buildingKey = useTwin((s) => s.buildingKey);
  const building = useTwin((s) => s.building);
  const openBuilding = useTwin((s) => s.openBuilding);
  const campuses = useCampus((s) => s.available);
  const campus = useCampus((s) => s.view);
  const campusMode = useCampus((s) => s.mode);
  // Laptop: the list of rooms and things lives in this menu (Planner.tsx); the phone has no list.
  const listable = useTwin((s) => s.profile === "planner" && !!s.model && !s.draft);
  const site = campusMode === "site" && campus?.loaded;
  const labels = useMemo(() => buildingLabels(buildings), [buildings]);
  // "new building" typed or spoken in the Omnibox (store.ask): the store cannot import newBuildingStore (cycle)
  useEffect(() => {
    const onNew = () => useNewBuilding.getState().open();
    window.addEventListener("twin:new-building", onNew);
    return () => window.removeEventListener("twin:new-building", onNew);
  }, []);
  const pick = (value: string) => {
    if (value === "__list") return void usePlannerList.getState().setOpen(true);
    if (value === "__new") return void useNewBuilding.getState().open();
    if (value.startsWith(CAMPUS)) return void useCampus.getState().open(value.slice(CAMPUS.length));
    useCampus.getState().exit();
    void openBuilding(value);
  };
  return (
    <div className="topbar">
      <label className="building-name">
        <span className="brand-mark" aria-hidden />
        <span className="building-title">{site ? campus.name : (building?.name ?? "Building")}</span>
        <select
          value={site ? CAMPUS + campus.key : (buildingKey ?? "")}
          onChange={(event) => pick(event.target.value)}
          aria-label="Building"
        >
          {buildings.map((entry) => (
            <option key={entry.key} value={entry.key}>
              {labels.get(entry.key) ?? entry.name}
            </option>
          ))}
          {campuses.map((entry) => (
            <option key={entry.key} value={CAMPUS + entry.key}>
              Campus: {campusLabel(entry, campus)}
            </option>
          ))}
          {listable && <option value="__list">All rooms and things</option>}
          <option value="__new">New building…</option>
        </select>
      </label>
      <CampusBack />
    </div>
  );
}

const CAMPUS = "__campus:";

/** "Example campus (3 buildings)" once loaded; before that the server's name (counting needs a load). */
function campusLabel(entry: { key: string; name: string }, loaded: ReturnType<typeof useCampus.getState>["view"]): string {
  if (loaded?.loaded && loaded.key === entry.key) return `${loaded.name} (${loaded.buildings.length} buildings)`;
  return entry.name;
}
