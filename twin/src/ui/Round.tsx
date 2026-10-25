// Inspection round panel (owner: round session). A "Round" button top left opens it: what (asset type), where
// (floor, hall or the whole building), from where; then "14 stops · 230 m · ~4 min", the stops in order, Start, and
// "What if a door here?". While walking, RoundBar sits on top of the step sheet (Walk.tsx): "Stop 3 of 14 · …" + Done.
// URL trigger: #round=fire%20extinguisher&area=Ground%20floor[&building=<key>][&door=<room id>,<room id>].
// All facts from round.ts (POST /api/round: the same plan_round the chat agent uses).

import { useEffect, useMemo, useRef } from "react";
import { prettyType } from "../model/palette";
import { useTwin } from "../store";
import { areaOptions, assetInArea } from "../round/choices";
import {
  assetLabel,
  cancelDoor,
  closeRound,
  endRound,
  openRound,
  pickDoorRooms,
  proposeDoor,
  roundConfirmDoor,
  roundDone,
  roundStatus,
  roundUndoDoor,
  setRoundChoice,
  startRound,
  summary,
  useRound,
  whatIfLine,
} from "../round/round";
import "./Round.css";

export function Round() {
  const model = useTwin((s) => s.model);
  const walking = useTwin((s) => s.walkStep !== null);
  const hasPosition = useTwin((s) => !!s.state?.position);
  const round = useRound();
  useHashTrigger();
  const panelRef = usePhoneTopInset(round.open && !walking, round.guiding);

  const types = useMemo(() => {
    if (!model) return [];
    // The count in brackets is for the chosen area (Hall A, a floor), not the whole building; types with none there
    // drop out of the list, except the one already chosen.
    const counts = new Map<string, number>();
    const spaceName = (id: string) => model.spaceById.get(id)?.name ?? "";
    for (const asset of model.building.assets) {
      if (!assetInArea(asset, round.area, model.building.floors, spaceName)) continue;
      counts.set(asset.type, (counts.get(asset.type) ?? 0) + 1);
    }
    for (const asset of model.building.assets) if (asset.type === round.type && !counts.has(asset.type)) counts.set(asset.type, 0);
    return [...counts.entries()].sort((a, b) => prettyType(a[0]).localeCompare(prettyType(b[0])));
  }, [model, round.area, round.type]);
  const areas = useMemo(() => (model ? areaOptions(model.building.floors, model.building.spaces) : []), [model]);

  if (!model || walking) return null;
  // Guiding without a step sheet: the stop is in the room you are already in (or no route to it).
  if (round.guiding && round.plan) {
    const stop = round.plan.stops[round.index];
    return (
      <section className="round-panel round-panel-here" aria-label="Inspection round" ref={panelRef}>
        <RoundBar />
        <p className="round-note">
          {stop.device ? `${stop.device} is here in ${stop.name}.` : `You are in ${stop.name}.`} Check it, then tap Done.
        </p>
      </section>
    );
  }
  if (!round.open) {
    return (
      <button className="round-toggle" onClick={() => void openRound()} title="Plan an inspection round" aria-label="Inspection round">
        <RoundIcon /> Round
      </button>
    );
  }
  const { plan, whatIf, picking, busy, error, checked, finished, suggestion, pendingDoor } = round;
  const name = (id: string) => model.spaceById.get(id)?.name ?? id;
  return (
    <section className="round-panel" aria-label="Inspection round" ref={panelRef}>
      <div className="round-head">
        <h2>Inspection round</h2>
        <button className="x" onClick={closeRound} aria-label="Close" title="Close">
          ×
        </button>
      </div>
      <div className="round-fields">
        <label>
          <span className="tiny-label">What</span>
          <select value={round.type} onChange={(event) => void setRoundChoice({ type: event.target.value })}>
            {!round.type && <option value="">Choose what to check…</option>}
            {types.map(([type, count]) => (
              <option key={type} value={type}>
                {prettyType(type)} ({count})
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="tiny-label">Where</span>
          <select value={areas.includes(round.area) ? round.area : ""} onChange={(event) => void setRoundChoice({ area: event.target.value })}>
            {!areas.includes(round.area) && <option value="">{round.area}</option>}
            {areas.map((area) => (
              <option key={area} value={area}>
                {area}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="tiny-label">From</span>
          <select value={round.startId ?? ""} onChange={(event) => void setRoundChoice({ startId: event.target.value || null })}>
            <option value="">{hasPosition ? "My location" : "Entrance"}</option>
            {plan &&
              [...new Map(plan.stops.map((stop) => [stop.spaceId, stop.name])).entries()].map(([spaceId, name]) => (
                <option key={spaceId} value={spaceId}>
                  {name}
                </option>
              ))}
          </select>
        </label>
        <label>
          <span className="tiny-label">End</span>
          <select value={round.returnToStart ? "start" : "last"} onChange={(event) => void setRoundChoice({ returnToStart: event.target.value === "start" })}>
            <option value="last">At the last stop</option>
            <option value="start">Back at the start</option>
          </select>
        </label>
      </div>

      {!plan && !busy && !error && (
        <button className="primary round-wide" onClick={() => void setRoundChoice({})} disabled={!round.type}>
          Plan round
        </button>
      )}
      {busy && <p className="round-note" role="status">{busy}</p>}
      {error && <p className="round-note round-error" role="alert">{error}</p>}

      {plan && (
        <>
          <p className="round-summary">
            <strong>{summary(plan)}</strong>
          </p>
          {whatIf && (
            <div className="round-whatif" role="status">
              <strong>{whatIfLine(whatIf)}</strong>
              <span>
                New door: {whatIf.firstName} ↔ {whatIf.secondName}
              </span>
              <button className="link" onClick={() => void roundUndoDoor()} disabled={!!busy}>
                Undo
              </button>
            </div>
          )}
          {finished && <p className="round-done-note">Round complete · {checked.length} of {plan.stops.length} stops checked</p>}
          {plan.unreachable.length > 0 && <p className="round-note">Not reachable, left out: {plan.unreachable.join(", ")}</p>}
          <ol className="round-stops">
            <li className="round-start">
              <span className="round-num">●</span>
              <span>Start: {plan.startName}</span>
            </li>
            {plan.stops.map((stop, index) => {
              const done = checked.includes(stop.key);
              return (
                <li key={stop.key} className={done ? "done" : ""}>
                  <button className="round-stop" onClick={() => useTwin.getState().flyTo(stop.assetIds[0] ?? stop.spaceId)}>
                    <span className="round-num">{done ? "✓" : index + 1}</span>
                    <span className="round-stop-name">{stop.device || stop.name}</span>
                    <span className="round-muted">{stop.device ? stop.name : assetLabel(plan.type, stop.assetIds.length)}</span>
                  </button>
                </li>
              );
            })}
          </ol>
          <div className="round-actions">
            <button className="primary" onClick={() => void startRound()} disabled={!!busy}>
              {checked.length && !finished ? `Resume (${checked.length} of ${plan.stops.length} done)` : "Start round"}
            </button>
            {picking ? (
              <button onClick={() => pickDoorRooms(false)}>Cancel</button>
            ) : (
              <button onClick={() => pickDoorRooms(true)} disabled={!!busy} title="Tap two neighbouring rooms on the map">
                What if a door here?
              </button>
            )}
          </div>
          {picking && (
            <p className="round-note" role="status">
              {picking.first ? `${name(picking.first)} — now tap the room next to it.` : "Tap the first room on the map."}
            </p>
          )}
          {pendingDoor && (
            <div className="round-whatif" role="alertdialog" aria-label="Add a door?">
              <strong>
                Add a door between {name(pendingDoor[0])} and {name(pendingDoor[1])}?
              </strong>
              <span>This changes the building.</span>
              <div>
                <button className="link" onClick={() => void roundConfirmDoor()} disabled={!!busy}>
                  Yes
                </button>
                <button className="link" onClick={cancelDoor}>
                  Cancel
                </button>
              </div>
            </div>
          )}
          {suggestion && !whatIf && !picking && !pendingDoor && (
            <button className="link round-suggest" onClick={() => proposeDoor(suggestion[0], suggestion[1])} disabled={!!busy}>
              Try a door: {name(suggestion[0])} ↔ {name(suggestion[1])}
            </button>
          )}
        </>
      )}
    </section>
  );
}

/** On top of the step sheet while a round is walked: which stop, and Done. */
export function RoundBar() {
  const round = useRound();
  if (!round.guiding || !round.plan) return null;
  const status = roundStatus();
  return (
    <div className="round-bar">
      <span className="round-bar-text">
        {status.returning ? (
          <strong>{status.label}</strong>
        ) : (
          <>
            <strong>
              Stop {status.stop} of {status.total}
            </strong>{" "}
            · {status.label}
          </>
        )}
      </span>
      <button className="round-bar-done" onClick={() => void roundDone()} disabled={!!round.busy} title={status.returning ? "Back at the start: finish the round" : "Checked: go to the next stop"}>
        Done
      </button>
      <button className="link round-bar-exit" onClick={endRound} title="Leave the round (checks are kept)">
        Pause
      </button>
    </div>
  );
}

function RoundIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M9 11l3 3 8-8" />
      <path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9" />
    </svg>
  );
}

/** Phone: the panel covers the top of the map, so the camera frames below it (like the directions sheet). */
function usePhoneTopInset(open: boolean, variant: boolean) {
  const ref = useRef<HTMLElement>(null);
  const worker = useTwin((s) => s.profile === "worker");
  useEffect(() => {
    const element = ref.current;
    if (!open || !worker || !element) return;
    const { setTopInset } = useTwin.getState();
    const observer = new ResizeObserver(() => setTopInset(Math.round(element.getBoundingClientRect().bottom)));
    observer.observe(element);
    return () => {
      observer.disconnect();
      useTwin.getState().setTopInset(0);
    };
  }, [open, worker, variant]);
  return ref;
}

/** #round=<type>&area=<area>[&building=<key>][&door=<id>,<id>] opens the panel and plans at once. */
function useHashTrigger() {
  const model = useTwin((s) => s.model);
  const buildingKey = useTwin((s) => s.buildingKey);
  useEffect(() => {
    const run = () => {
      const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
      const type = params.get("round");
      if (type === null) return;
      const building = params.get("building");
      if (building && building !== useTwin.getState().buildingKey) {
        void useTwin.getState().openBuilding(building); // the effect runs again once the model is in
        return;
      }
      if (!useTwin.getState().model) return;
      const door = params.get("door")?.split(",");
      useRound.setState({ suggestion: door?.length === 2 ? [door[0], door[1]] : null });
      history.replaceState(null, "", window.location.pathname + window.location.search);
      void openRound(type || undefined, params.get("area") ?? undefined);
    };
    run();
    window.addEventListener("hashchange", run);
    return () => window.removeEventListener("hashchange", run);
  }, [model, buildingKey]);
}
