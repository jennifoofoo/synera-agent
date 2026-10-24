import { useTwin } from "../store";

/** Left edge: one small number per floor. Tap = focus that floor (others become glass); tap the active one
 * again = only this floor; the ⇕ toggle pulls the floors apart. Floors on the route carry a dot. */
export function FloorRail() {
  const model = useTwin((s) => s.model);
  const focusedFloorId = useTwin((s) => s.focusedFloorId);
  const focusFloor = useTwin((s) => s.focusFloor);
  const floorMode = useTwin((s) => s.floorMode);
  const setFloorMode = useTwin((s) => s.setFloorMode);
  const requestCamera = useTwin((s) => s.requestCamera);
  const state = useTwin((s) => s.state);
  const viewMode = useTwin((s) => s.viewMode);
  const setViewMode = useTwin((s) => s.setViewMode);
  const profile = useTwin((s) => s.profile);
  const topInset = useTwin((s) => s.topInset);
  if (!model) return null;
  const flat = viewMode === "2d";
  const routeFloors = new Set(state?.route?.ok ? state.route.floors : []);
  return (
    <div
      className="floorrail"
      role="radiogroup"
      aria-label="Floor"
      // The phone's directions sheet covers the top of the screen: keep the rail below it (topInset = its bottom edge).
      style={topInset > 0 && profile === "worker" ? { top: topInset + 8, maxHeight: `calc(var(--vvh, 100dvh) - ${topInset + 8}px - var(--dock-h, 90px) - 16px)` } : undefined}
    >
      {profile !== "worker" && (
        <button className="rail-toggle rail-view" onClick={() => setViewMode(flat ? "3d" : "2d")} title={flat ? "Show the building in 3D" : "Show the floor plan"} aria-pressed={flat}>
          {flat ? "3D" : "2D"}
        </button>
      )}
      {!flat && model.floors.length > 1 && (
        <button
          className={`rail-toggle ${floorMode === "exploded" ? "active" : ""}`}
          onClick={() => setFloorMode(floorMode === "exploded" ? "stacked" : "exploded")}
          title={floorMode === "exploded" ? "Stack the floors" : "Pull the floors apart"}
          aria-pressed={floorMode === "exploded"}
        >
          ⇕
        </button>
      )}
      {model.floors.length > 1 && [...model.floors].reverse().map((floor) => {
        const active = floor.id === focusedFloorId;
        return (
          <button
            key={floor.id}
            role="radio"
            aria-checked={active}
            className={`rail-floor ${active ? "active" : ""} ${active && floorMode === "single" ? "single" : ""}`}
            onClick={() => {
              if (active) {
                if (!flat) setFloorMode(floorMode === "single" ? "stacked" : "single");
              } else {
                focusFloor(floor.id);
                if (floorMode === "exploded") requestCamera({ kind: "floor", floorId: floor.id });
              }
            }}
            title={active ? (floorMode === "single" ? `${floor.name}: show all floors` : `${floor.name}: only this floor`) : floor.name}
          >
            {floor.level}
            {routeFloors.has(floor.id) && <span className="dot" aria-hidden />}
          </button>
        );
      })}
      <button className="rail-toggle" onClick={() => requestCamera({ kind: "home" })} title="Home view" aria-label="Home view">
        ⌂
      </button>
    </div>
  );
}
