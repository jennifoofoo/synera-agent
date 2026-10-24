import { useTwin } from "../store";

/** Appears only when the building differs from disk: "2 closed · 1 route · reset". */
export function ChangesPill() {
  const state = useTwin((s) => s.state);
  const reset = useTwin((s) => s.reset);
  const clearRoute = useTwin((s) => s.clearRoute);
  const worker = useTwin((s) => s.profile === "worker");
  if (!state) return null;
  const parts: string[] = [];
  if (state.closed.length) parts.push(`${state.closed.length} closed`);
  const edits =
    Object.keys(state.added_assets ?? {}).length +
    Object.keys(state.moved_assets ?? {}).length +
    (state.removed_assets?.length ?? 0) +
    (state.removed_openings?.length ?? 0) +
    Object.keys(state.widened_openings ?? {}).length +
    state.added_doors.length;
  if (edits) parts.push(`${edits} edit${edits > 1 ? "s" : ""}`);
  // A drawn route has its length and its clear (×) in the route card (and on the phone in the sheet), so the
  // pill no longer repeats it; it only offers to clear a route that failed.
  const hasRoute = !!state.route && !state.route.ok && !worker;
  if (!parts.length && !hasRoute) return null;
  return (
    <div className="pill">
      {parts.length > 0 && <span>{parts.join(" · ")}</span>}
      {hasRoute && (
        <button onClick={() => void clearRoute()} title="Remove the route">
          no route ×
        </button>
      )}
      {parts.length > 0 && (
        <button onClick={() => void reset()} title="Reload the building from disk">
          reset
        </button>
      )}
    </div>
  );
}
