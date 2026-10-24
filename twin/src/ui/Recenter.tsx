import { useTwin } from "../store";

/** 2D only: a round white button bottom right, shown once the plan was panned away from the floor. */
export function Recenter() {
  const offCentre = useTwin((s) => s.offCentre);
  const flat = useTwin((s) => s.viewMode === "2d");
  const requestCamera = useTwin((s) => s.requestCamera);
  if (!flat || !offCentre) return null;
  return (
    <button className="recenter" onClick={() => requestCamera({ kind: "home" })} aria-label="Recenter" title="Recenter">
      ◎
    </button>
  );
}
