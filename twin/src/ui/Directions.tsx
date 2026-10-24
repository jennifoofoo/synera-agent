// Directions, like a maps app: a compact From/To panel at the top (phone: top sheet; laptop: small panel top left)
// and the route summary with "Start" in the bottom card. "Route" on the room card opens it. From is "Your location"
// when the position is known, else empty and focused ("Choose start"). Both set = the route is computed at once.
// Owner: the Card/Position session. The fields are the Omnibox's PlaceInput (one grey ghost match, no list).

import { useEffect } from "react";
import { createPortal } from "react-dom";
import type { Route } from "../api/types";
import type { BuildingModel } from "../model/model";
import { HERE, useTwin, type Place } from "../store";
import { PlaceInput } from "./Autocomplete";
import "./Directions.css";

export function placeName(model: BuildingModel, place: Place | null): string {
  if (!place) return "";
  if (place === HERE) return "Your location";
  return model.spaceById.get(place)?.name || model.connectorBySpace.get(place)?.name || place;
}

function PlaceField({ model, field, value, placeholder }: { model: BuildingModel; field: "from" | "to"; value: Place | null; placeholder: string }) {
  const editing = useTwin((s) => s.directions?.editing === field);
  const editDirections = useTwin((s) => s.editDirections);
  const setFrom = useTwin((s) => s.setDirectionsFrom);
  const setTo = useTwin((s) => s.setDirectionsTo);
  const hasHere = useTwin((s) => !!s.state?.position);
  const dot = <span className={`dir-dot ${field}`} aria-hidden />;
  const label = field === "from" ? "From" : "To";
  if (!editing) {
    return (
      <button className={`dir-field ${value ? "" : "empty"}`} onClick={() => editDirections(field)} aria-label={`${label}: ${placeName(model, value) || placeholder}`}>
        {dot}
        <span className="dir-value">{placeName(model, value) || placeholder}</span>
      </button>
    );
  }
  return (
    <div className="dir-field editing">
      {dot}
      <PlaceInput
        placeholder={value ? placeName(model, value) : placeholder}
        autoFocus
        includeHere={hasHere}
        ariaLabel={label}
        onPick={(place) => (field === "from" ? setFrom(place) : setTo(place))}
        onCancel={() => editDirections(null)}
      />
      {value && (
        <button className="dir-accept" onClick={() => editDirections(null)} aria-label="Keep">
          ✓
        </button>
      )}
    </div>
  );
}

/** The From/To panel at the top. Rendered into .app so it can sit outside the bottom dock. */
export function DirectionsPanel({ model }: { model: BuildingModel }) {
  const directions = useTwin((s) => s.directions)!;
  const swap = useTwin((s) => s.swapDirections);
  const setStepFree = useTwin((s) => s.setDirectionsStepFree);
  const close = useTwin((s) => s.closeDirections);
  const editing = directions.editing;

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => event.key === "Escape" && !useTwin.getState().directions?.editing && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const host = document.querySelector(".app") ?? document.body;
  return createPortal(
    <section className="directions" aria-label="Directions">
      <div className="dir-fields">
        <PlaceField model={model} field="from" value={directions.from} placeholder="Choose start" />
        <PlaceField model={model} field="to" value={directions.to} placeholder="Choose destination" />
      </div>
      <div className="dir-side">
        <button className="x" onClick={() => close()} aria-label="Close directions">
          ×
        </button>
        <button className="dir-swap" onClick={swap} aria-label="Swap start and destination" disabled={!directions.from && !directions.to}>
          ⇅
        </button>
      </div>
      <div className="dir-foot">
        <label className="dir-toggle">
          <input type="checkbox" checked={directions.stepFree} onChange={(event) => setStepFree(event.target.checked)} />
          Step-free
        </label>
        {editing && <span className="dir-hint">or tap a room on the plan</span>}
      </div>
    </section>,
    host,
  );
}

function facts(model: BuildingModel, route: Route) {
  const changes = route.floor_changes ?? [];
  const stepFree = !!route.step_free || changes.every((change) => model.connectorById.get(change.connector_id)?.step_free);
  return { length: route.length_m !== undefined ? `${Math.round(route.length_m)} m` : "", floors: route.floors?.length ?? 1, stepFree };
}

/** The bottom card while directions are open: summary and "Start" (= guided walking via the agent). */
export function DirectionsSummary({ model }: { model: BuildingModel }) {
  const directions = useTwin((s) => s.directions)!;
  const route = useTwin((s) => s.state?.route ?? null);
  const position = useTwin((s) => s.state?.position ?? null);
  const ask = useTwin((s) => s.ask);
  const close = useTwin((s) => s.closeDirections);
  const busy = useTwin((s) => s.chatBusy);
  const chatAvailable = useTwin((s) => s.chatAvailable);
  if (!directions.from || !directions.to || !route) return null;
  if (!route.ok) {
    return <div className="card-note dir-error">{route.error ?? "No route between these two."}</div>;
  }
  const f = facts(model, route);
  const from = directions.from === HERE ? position?.space_id : directions.from;
  const start = () => {
    const toName = placeName(model, directions.to);
    const stepFree = directions.stepFree ? ", step-free" : "";
    const message = directions.from === HERE ? `Guide me to ${toName}${stepFree}.` : `Guide me from ${placeName(model, directions.from)} to ${toName}${stepFree}.`;
    // A start room picked here is where the person stands now: it travels as context.here (position, source click).
    const here = directions.from !== HERE && from ? { space_id: from, floor_id: model.spaceById.get(from)?.floor_id } : undefined;
    close(true);
    void ask(message, false, here ? { here } : undefined);
  };
  return (
    <>
      <div className="card-line route-facts">
        {f.length && <b>{f.length}</b>}
        <span>
          {f.floors} {f.floors === 1 ? "floor" : "floors"}
        </span>
        <span className={f.stepFree ? "ok" : "warn"}>{f.stepFree ? "step-free" : "has stairs"}</span>
      </div>
      <div className="card-actions">
        <button className="primary" disabled={busy || !chatAvailable} onClick={start} title={chatAvailable ? "Step-by-step guidance" : "Guidance needs the agent (no API key on the server)"}>
          Start
        </button>
      </div>
    </>
  );
}
