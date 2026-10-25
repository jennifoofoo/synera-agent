import { useKeyHelp } from "../scene/controlsTable";
import { routeStackKey } from "../scene/floorVisibility";
import { useTwin } from "../store";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CompassIcon, resetNorth, tilt, TiltIcon } from "./Compass";

/** The floor rail: 2D/3D, one small number per floor, home (laptop) and "…" for the rarer view tools (all floors,
 * north up, tilt, help). Tap a floor = focus it (others become glass); tap the active one again = only this floor.
 * Floors on the route carry a dot. */
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
  // While walking the rail keeps only the floors: no view switch, no "all floors" (the walk frames the route).
  const walking = useTwin((s) => s.walkStep !== null);
  const routeStackOff = useTwin((s) => s.routeStackOff);
  const setRouteStackOff = useTwin((s) => s.setRouteStackOff);
  if (!model) return null;
  const flat = viewMode === "2d";
  // 3D, a route over several floors: its floors are stacked apart until a floor is picked here (only that floor then,
  // guidance still moves it along); "all floors" stacks the route again.
  const stackKey = flat ? "" : routeStackKey(state?.route);
  const routeStacked = !!stackKey && routeStackOff !== stackKey;
  const allFloors = floorMode === "exploded" || routeStacked;
  const toggleAllFloors = () => {
    if (routeStacked) setRouteStackOff(stackKey);
    else if (floorMode === "exploded") setFloorMode("single");
    else if (stackKey) setRouteStackOff(null);
    else setFloorMode("exploded");
  };
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
      {/* 2D/3D at every width; real phones start in 2D but may switch to 3D (no ambient occlusion there) */}
      {!walking && (
        <button className="rail-toggle rail-view" onClick={() => setViewMode(flat ? "3d" : "2d")} title={flat ? "Show the building in 3D" : "Show the floor plan"} aria-pressed={flat}>
          {flat ? "3D" : "2D"}
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
              if (routeStacked) {
                setRouteStackOff(stackKey); // only this floor, the route on the other floors is hidden
                focusFloor(floor.id);
              } else if (active) {
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
      <MoreMenu
        items={[
          ...(!flat && !walking && model.floors.length > 1
            ? [{ id: "all-floors", icon: <AllFloorsIcon />, label: allFloors ? "Only this floor" : "All floors", pressed: allFloors, run: toggleAllFloors }]
            : []),
          { id: "compass", icon: <CompassIcon />, label: "North up", run: resetNorth },
          ...(!flat
            ? [
                { id: "tilt-flatter", icon: <TiltIcon flatter />, label: "Tilt flatter", run: () => tilt(true) },
                { id: "tilt-steeper", icon: <TiltIcon />, label: "Tilt steeper", run: () => tilt(false) },
              ]
            : []),
          ...(profile !== "worker"
            ? [{ id: "help", icon: <HelpIcon />, label: "Help and map symbols", run: () => useKeyHelp.getState().setOpen(true) }]
            : []),
        ]}
      />
    </div>
  );
}

interface MoreItem {
  id: string;
  icon: ReactNode;
  label: string;
  pressed?: boolean;
  run: () => void;
}

/** "…" at the end of the rail: the rarely used view tools as labelled rows. Closes on pick, Esc or a click outside.
 * The popover lives in a portal (the rail clips its children) and opens away from the screen edge the rail sits on. */
function MoreMenu({ items }: { items: MoreItem[] }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<React.CSSProperties>({ visibility: "hidden" });
  useLayoutEffect(() => {
    if (!open || !button.current || !menu.current) return;
    const r = button.current.getBoundingClientRect();
    const h = menu.current.offsetHeight;
    const top = Math.max(8, Math.min(r.top, window.innerHeight - h - 8));
    setPlace(r.left > window.innerWidth / 2 ? { top, right: window.innerWidth - r.left + 8 } : { top, left: r.right + 8 });
  }, [open, items.length]);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      setOpen(false);
      button.current?.focus();
    };
    const onDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!menu.current?.contains(target) && !button.current?.contains(target)) setOpen(false);
    };
    window.addEventListener("keydown", onKey, { capture: true });
    window.addEventListener("pointerdown", onDown, { capture: true });
    return () => {
      window.removeEventListener("keydown", onKey, { capture: true });
      window.removeEventListener("pointerdown", onDown, { capture: true });
    };
  }, [open]);
  useEffect(() => {
    if (open) menu.current?.querySelector<HTMLButtonElement>("button")?.focus();
    else setPlace({ visibility: "hidden" });
  }, [open]);
  if (items.length === 1) {
    // A menu with one row is an extra tap for nothing: show that tool itself in the "…" slot (phone 2D: north up).
    const [only] = items;
    return (
      <button className="rail-toggle rail-more" data-testid={only.id} onClick={only.run} title={only.label} aria-label={only.label}>
        {only.icon}
      </button>
    );
  }
  return (
    <>
      <button
        ref={button}
        className={`rail-toggle rail-more ${open ? "active" : ""}`}
        data-testid="rail-more"
        onClick={() => setOpen(!open)}
        title="More view tools"
        aria-label="More view tools"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <MoreIcon />
      </button>
      {open &&
        createPortal(
          <div className="rail-menu" role="menu" aria-label="View tools" ref={menu} style={place}>
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                role="menuitem"
                data-testid={item.id}
                className={item.pressed ? "pressed" : undefined}
                onClick={() => {
                  setOpen(false);
                  item.run();
                }}
              >
                <span className="rail-menu-icon">{item.icon}</span>
                {item.label}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}

function MoreIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <circle cx="5" cy="12" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="19" cy="12" r="1.8" />
    </svg>
  );
}

function HelpIcon() {
  return (
    <svg {...railIcon}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.7M12 17h.01" />
    </svg>
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
