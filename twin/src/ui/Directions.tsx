// Directions, like a maps app: a compact From/To panel at the top (phone: top sheet; laptop: small panel top left)
// and the route summary with "Guide me" in the bottom card. "Route" on the room card opens it. From is "Your location"
// when the position is known, else empty and focused ("Choose start"). Both set = the route is computed at once.
// Owner: the Card/Position session. The fields are the Omnibox's PlaceInput (one grey ghost match, no list).

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Route } from "../api/types";
import type { BuildingModel } from "../model/model";
import { HERE, useTwin, walkLines, type Place } from "../store";
import { PlaceInput } from "./Autocomplete";
import { walkMinutes } from "./Walk";
import { AvoidsClosed } from "./AvoidsClosed";
import "./Directions.css";

export function placeName(model: BuildingModel, place: Place | null): string {
  if (!place) return "";
  if (place === HERE) {
    // Campus: "here" may be in another building (only when this building has no position of its own).
    const { state, campusHook } = useTwin.getState();
    const building = state?.position ? null : campusHook?.hereName();
    return building ? `Your location (${building})` : "Your location";
  }
  return model.spaceById.get(place)?.name || model.connectorBySpace.get(place)?.name || place;
}

function PlaceField({ model, field, value, placeholder }: { model: BuildingModel; field: "from" | "to"; value: Place | null; placeholder: string }) {
  const editing = useTwin((s) => s.directions?.editing === field);
  const editDirections = useTwin((s) => s.editDirections);
  const setFrom = useTwin((s) => s.setDirectionsFrom);
  const setTo = useTwin((s) => s.setDirectionsTo);
  const hasHere = useTwin((s) => !!s.state?.position || !!s.campusHook?.hereName());
  // Phone: focus (keyboard, iOS paste bubble) only after a tap on the field, never on its own; the plan tap is the
  // easier way to pick a room there.
  const worker = useTwin((s) => s.profile === "worker");
  const [tapped, setTapped] = useState(false);
  const dot = <span className={`dir-dot ${field}`} aria-hidden />;
  const label = field === "from" ? "From" : "To";
  if (!editing) {
    return (
      <button className={`dir-field ${value ? "" : "empty"}`} onClick={() => {
          setTapped(true);
          editDirections(field);
        }} aria-label={`${label}: ${placeName(model, value) || placeholder}`}>
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
        autoFocus={!worker || tapped}
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
  const worker = useTwin((s) => s.profile === "worker");
  const setTopInset = useTwin((s) => s.setTopInset);
  const panel = useRef<HTMLElement>(null);

  // Phone: the top sheet covers the plan, so the camera frames below it (scene reads topInset); 0 when closed.
  useEffect(() => {
    const element = panel.current;
    if (!worker || !element) return;
    const observer = new ResizeObserver(() => setTopInset(Math.round(element.getBoundingClientRect().bottom)));
    observer.observe(element);
    return () => {
      observer.disconnect();
      setTopInset(0);
    };
  }, [worker, setTopInset]);

  useEffect(() => {
    // Esc inside a field belongs to the field (PlaceInput: clear, then stop editing); elsewhere it closes the panel.
    const onKey = (event: globalThis.KeyboardEvent) =>
      event.key === "Escape" && !(event.target instanceof HTMLInputElement) && !useTwin.getState().directions?.editing && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const host = document.querySelector(".app") ?? document.body;
  return createPortal(
    <section ref={panel} className="directions" aria-label="Directions">
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
  const length = route.length_m !== undefined ? `${Math.round(route.length_m)} m · ${walkMinutes(route.length_m)} min` : "";
  return { length, floors: route.floors?.length ?? 1, stepFree };
}

/** The bottom card while directions are open: summary and "Guide me" (= step-by-step on the client, see Walk). */
export function DirectionsSummary({ model }: { model: BuildingModel }) {
  const directions = useTwin((s) => s.directions)!;
  const route = useTwin((s) => s.state?.route ?? null);
  const close = useTwin((s) => s.closeDirections);
  const startWalk = useTwin((s) => s.startWalk);
  if (!directions.from || !directions.to || !route) return null;
  if (!route.ok) {
    return <div className="card-note dir-error">{route.error ?? "No route between these two."}</div>;
  }
  const f = facts(model, route);
  const start = () => {
    close(true);
    startWalk();
  };
  // The same one line as the route card ("30 m · 1 min · 4 steps · step-free") and the same primary action.
  const steps = walkLines(route.steps).length;
  return (
    <>
      <div className="route-summary" data-testid="route-summary">
        <span className="route-dot" aria-hidden />
        <span className="route-sentence">
          {f.length && <b>{f.length}</b>}
          <span className="card-muted">
            {steps > 0 && ` · ${steps} ${steps === 1 ? "step" : "steps"}`}
            {f.floors > 1 && ` · ${f.floors} floors`}
            {" · "}
          </span>
          <span className={f.stepFree ? "ok" : "warn"}>{f.stepFree ? "step-free" : "has stairs"}</span>
        </span>
      </div>
      <AvoidsClosed model={model} route={route} />
      <div className="card-actions">
        <button className="primary" onClick={start} title="Step-by-step directions">
          Guide me
        </button>
      </div>
    </>
  );
}
