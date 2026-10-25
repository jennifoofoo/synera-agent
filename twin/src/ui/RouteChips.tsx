// The route facts as pill chips: "35 m", "1 min", "2 floors", "step-free" / "has stairs".
// Shared by the route card and the directions summary; keeps the data-testid the tests read.

import { walkMinutes } from "../walkInfo";

export function RouteChips({ length, lengthM, floors, stepFree }: { length: string; lengthM?: number; floors: number; stepFree: boolean }) {
  return (
    <div className="route-chips" data-testid="route-summary">
      {length && <span className="route-chip"><b>{length}</b></span>}
      {lengthM !== undefined && <span className="route-chip">{walkMinutes(lengthM)} min</span>}
      {floors > 1 && <span className="route-chip">{floors} floors</span>}
      <span className={`route-chip ${stepFree ? "ok" : "warn"}`}>{stepFree ? "step-free" : "has stairs"}</span>
    </div>
  );
}
