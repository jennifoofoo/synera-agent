import { useKeyHelp } from "../scene/controlsTable";
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
  const directionsOpen = useTwin((s) => s.directions !== null);
  if (!model) return null;
  const flat = viewMode === "2d";
  const routeFloors = new Set(state?.route?.ok ? state.route.floors : []);
  return (
    <div
      className="floorrail"
      role="radiogroup"
      aria-label="Floor"
      // The phone's directions sheet covers the top of the screen: keep the rail below it (topInset = its bottom edge).
      // Phone.css places the rail from --rail-top (portrait: right edge above the dock; landscape: left edge).
      style={directionsOpen && topInset > 0 && profile === "worker" ? ({ "--rail-top": `${topInset + 8}px` } as React.CSSProperties) : undefined}
    >
      {profile !== "worker" && (
        <button className="rail-toggle rail-view" onClick={() => setViewMode(flat ? "3d" : "2d")} title={flat ? "Show the building in 3D" : "Show the floor plan"} aria-pressed={flat}>
          {flat ? "3D" : "2D"}
        </button>
      )}
      {!flat && model.floors.length > 1 && (
        <button
          className={`rail-toggle ${floorMode === "exploded" ? "active" : ""}`}
          onClick={() => setFloorMode(floorMode === "exploded" ? "single" : "exploded")}
          title={floorMode === "exploded" ? "Show only this floor" : "Show all floors"}
          aria-label="All floors"
          aria-pressed={floorMode === "exploded"}
        >
          <AllFloorsIcon />
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
      {profile !== "worker" && (
        <button className="rail-toggle" onClick={() => requestCamera({ kind: "home" })} title="Reset view: the whole building" aria-label="Reset view">
          <ResetViewIcon />
        </button>
      )}
      {profile !== "worker" && (
        <button className="rail-toggle rail-help" onClick={() => useKeyHelp.getState().setOpen(true)} title="Help: controls and map symbols (?)" aria-label="Help: controls and map symbols">
          ?
        </button>
      )}
    </div>
  );
}

const railIcon = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

/** Three stacked floor plates (Tabler "stack-2" style): show all floors apart. */
export function AllFloorsIcon() {
  return (
    <svg {...railIcon}>
      <path d="M12 4 4 8l8 4 8-4z" />
      <path d="m4 12 8 4 8-4" />
      <path d="m4 16 8 4 8-4" />
    </svg>
  );
}

/** Four frame corners (Tabler "maximize" style): back to the view of the whole building. */
export function ResetViewIcon() {
  return (
    <svg {...railIcon}>
      <path d="M4 8V6a2 2 0 0 1 2-2h2M4 16v2a2 2 0 0 0 2 2h2M16 4h2a2 2 0 0 1 2 2v2M16 20h2a2 2 0 0 0 2-2v-2" />
    </svg>
  );
}
