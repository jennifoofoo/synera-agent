import { useTwin } from "../store";

/** A round white button bottom right. Phone: "Show my location", only while a position is known (no home view).
 * Laptop 2D: recenter, shown once the plan was panned away from the floor. */
export function Recenter() {
  const worker = useTwin((s) => s.profile === "worker");
  const position = useTwin((s) => s.state?.position ?? null);
  const offCentre = useTwin((s) => s.offCentre);
  const flat = useTwin((s) => s.viewMode === "2d");
  const requestCamera = useTwin((s) => s.requestCamera);
  const focusFloor = useTwin((s) => s.focusFloor);
  const walking = useTwin((s) => s.walkStep !== null);
  const route = useTwin((s) => s.state?.route ?? null);

  // Walking the steps (phone and laptop): one tap brings the current leg back into view.
  if (walking && route?.ok) {
    const toLeg = () => {
      const { focusedFloorId, model } = useTwin.getState();
      const onFloor = (route.space_path ?? []).filter((id) => model?.spaceById.get(id)?.floor_id === focusedFloorId);
      const ids = onFloor.length ? onFloor : [route.destination ?? ""].filter(Boolean);
      if (ids.length) requestCamera({ kind: "object", ids });
    };
    return (
      <button className="recenter" onClick={toLeg} aria-label="Back to the route" title="Back to the route">
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
          <circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
          <circle cx="12" cy="12" r="3" fill="currentColor" />
          <path d="M12 2v3M12 19v3M2 12h3M19 12h3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
    );
  }

  if (worker) {
    if (!position) return null;
    const locate = () => {
      focusFloor(position.floor_id);
      if (position.point) requestCamera({ kind: "point", floorId: position.floor_id, point: position.point });
      else requestCamera({ kind: "object", ids: [position.space_id] });
    };
    return (
      <button className="recenter" onClick={locate} aria-label="Show my location" title="Show my location">
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
          <circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
          <circle cx="12" cy="12" r="3" fill="currentColor" />
          <path d="M12 2v3M12 19v3M2 12h3M19 12h3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
    );
  }
  if (!flat || !offCentre) return null;
  return (
    <button className="recenter" onClick={() => requestCamera({ kind: "home" })} aria-label="Recenter" title="Recenter">
      ◎
    </button>
  );
}
