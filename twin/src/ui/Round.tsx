// Inspection round card (owner: round session). A "Round" button top left opens it; the card itself sits in the dock
// (App.tsx): in the chat column on the laptop like the route card, a bottom sheet on the phone. Voice first: what
// (chips with counts), where (segments), from (here, tap the map to change), end (switch). Every choice plans at once:
// "14 stops · 230 m · about 4 min", the stops in order, Start, and "What if a door here?".
// While walking, RoundBar sits on top of the step sheet (Walk.tsx): "Stop 3 of 14 · …" + Done.
// URL trigger: #round=fire%20extinguisher&area=Ground%20floor[&building=<key>][&door=<room id>,<room id>].
// All facts from round.ts (POST /api/round: the same plan_round the chat agent uses).

import { useEffect, useMemo, useState } from "react";
import { prettyType } from "../model/palette";
import { useTwin } from "../store";
import { walkMinutes } from "../walkInfo";
import { areaOptions, assetInArea, entranceRoom } from "../round/choices";
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
  useRound,
  whatIfLine,
} from "../round/round";
import { PhoneSheet } from "./PhoneSheet";
import "./Round.css";

/** The "Round" button over the map (and the #round= trigger). The card is RoundCard, in the dock. */
export function Round() {
  const model = useTwin((s) => s.model);
  const walking = useTwin((s) => s.walkStep !== null);
  const shown = useRound((s) => s.open || (s.guiding && !!s.plan));
  useHashTrigger();
  if (!model || walking || shown) return null;
  return (
    <button className="round-toggle" onClick={() => void openRound()} title="Plan an inspection round" aria-label="Inspection round">
      <RoundIcon /> Round
    </button>
  );
}

/** Chips shown before "More": the most common types (the list is sorted by count). */
const TOP_TYPES = 8;

/** "Fire extinguishers", "Defibrillator": the chip names. */
function plural(name: string, count: number): string {
  if (count === 1) return name;
  return /(s|x|ch|sh)$/i.test(name) ? `${name}es` : `${name}s`;
}

/** "7 stops · 82 m · about 2 min" */
function roundSummary(stops: number, metres: number): string {
  return `${stops} ${stops === 1 ? "stop" : "stops"} · ${Math.round(metres)} m · about ${walkMinutes(metres)} min`;
}

/** The inspection round card. Each change plans right away (setRoundChoice); the only primary button is Start. */
export function RoundCard() {
  const model = useTwin((s) => s.model);
  const walking = useTwin((s) => s.walkStep !== null);
  const hereId = useTwin((s) => s.state?.position?.space_id ?? null);
  const round = useRound();
  const [pickStart, setPickStart] = useState(false);
  const [moreTypes, setMoreTypes] = useState(false);

  const types = useMemo(() => {
    if (!model) return [];
    // The count is for the chosen area (a floor, Hall A), not the whole building; types with none there drop out,
    // except the one already chosen.
    const counts = new Map<string, number>();
    const spaceName = (id: string) => model.spaceById.get(id)?.name ?? "";
    for (const asset of model.building.assets) {
      if (!assetInArea(asset, round.area, model.building.floors, spaceName)) continue;
      counts.set(asset.type, (counts.get(asset.type) ?? 0) + 1);
    }
    for (const asset of model.building.assets) if (asset.type === round.type && !counts.has(asset.type)) counts.set(asset.type, 0);
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || prettyType(a[0]).localeCompare(prettyType(b[0])));
  }, [model, round.area, round.type]);

  const areas = useMemo(() => {
    if (!model) return [];
    const all = areaOptions(model.building.floors, model.building.spaces);
    // Halls only when the choices are few: the segments stay one row.
    const shown = all.length <= 4 ? all : all.filter((area) => !/^Hall [A-Z]$/.test(area));
    return shown.includes(round.area) ? shown : [...shown, round.area];
  }, [model, round.area]);

  // "Tap the map to change": the next room tapped becomes the start.
  useEffect(() => {
    if (!pickStart) return;
    return useTwin.subscribe((now, before) => {
      if (now.selection === before.selection || !now.selection) return;
      const spaceId = now.selection.kind === "space" ? now.selection.id : now.selection.kind === "point" ? now.selection.space_id : undefined;
      if (!spaceId) return;
      useTwin.getState().select(null);
      setPickStart(false);
      void setRoundChoice({ startId: spaceId });
    });
  }, [pickStart]);
  useEffect(() => {
    if (!round.open) setPickStart(false);
  }, [round.open]);

  if (!model || walking) return null;
  const name = (id: string) => model.spaceById.get(id)?.name ?? id;

  // Guiding without a step sheet: the stop is in the room you are already in (or there is no route to it).
  if (round.guiding && round.plan) {
    const stop = round.plan.stops[round.index];
    return (
      <PhoneSheet open onClose={endRound} label="Inspection round">
        <section className="card round-panel round-panel-here" aria-label="Inspection round">
          <RoundBar />
          <p className="round-note">You are in {stop.name}. Check it, then tap Done.</p>
        </section>
      </PhoneSheet>
    );
  }
  if (!round.open) return null;

  const { plan, whatIf, picking, busy, error, checked, finished, suggestion, pendingDoor } = round;
  const startId = plan?.startId ?? round.startId ?? hereId ?? entranceRoom(model.building.openings);
  const startKind = round.startId ? null : hereId ? "Here" : "Entrance";
  const hintType = round.type || types[0]?.[0] || "fire_extinguisher";
  const hintArea = round.area && round.area !== "Whole building" ? ` on the ${round.area.toLowerCase()}` : "";
  const resume = !!plan && checked.length > 0 && !finished;
  return (
    <PhoneSheet open onClose={closeRound} label="Inspection round">
      <section className="card round-panel" aria-label="Inspection round">
        <div className="round-head">
          <h2>
            <RoundIcon /> Inspection round
          </h2>
          <button className="x" onClick={closeRound} aria-label="Close" title="Close">
            ×
          </button>
        </div>

        <div className="round-field">
          <span className="tiny-label" id="round-what">
            What
          </span>
          <div className="round-chips" role="group" aria-labelledby="round-what">
            {(moreTypes ? types : types.filter(([type], index) => index < TOP_TYPES || type === round.type)).map(([type, count]) => (
              <button
                key={type}
                type="button"
                className={`round-chip${type === round.type ? " active" : ""}`}
                aria-pressed={type === round.type}
                onClick={() => type !== round.type && void setRoundChoice({ type })}
              >
                {plural(prettyType(type), count)} <span className="round-count">{count}</span>
              </button>
            ))}
            {types.length > TOP_TYPES && (
              <button type="button" className="round-chip round-more" aria-expanded={moreTypes} onClick={() => setMoreTypes(!moreTypes)}>
                {moreTypes ? "Fewer" : `More (${types.length - TOP_TYPES})`}
              </button>
            )}
          </div>
        </div>

        <div className="round-field">
          <span className="tiny-label" id="round-where">
            Where
          </span>
          <div className="round-seg" role="radiogroup" aria-labelledby="round-where">
            {areas.map((area) => (
              <button
                key={area}
                type="button"
                role="radio"
                aria-checked={area === round.area}
                className={area === round.area ? "on" : ""}
                onClick={() => area !== round.area && void setRoundChoice({ area })}
              >
                {area}
              </button>
            ))}
          </div>
        </div>

        <div className="round-row">
          <div className="round-from">
            <span className="tiny-label">From</span>
            <span className="round-from-name">
              {startKind && <b>{startKind}</b>}
              {startKind && startId && " · "}
              {startId ? name(startId) : ""}
            </span>
            {pickStart ? (
              <span className="round-from-hint" role="status">
                Tap a room on the map ·{" "}
                <button className="link" onClick={() => setPickStart(false)}>
                  Cancel
                </button>
              </span>
            ) : (
              <span className="round-from-hint">
                <button
                  className="link"
                  onClick={() => {
                    pickDoorRooms(false);
                    setPickStart(true);
                  }}
                >
                  Tap the map to change
                </button>
                {round.startId && hereId && (
                  <>
                    {" · "}
                    <button className="link" onClick={() => void setRoundChoice({ startId: null })}>
                      Start here
                    </button>
                  </>
                )}
              </span>
            )}
          </div>
          <div className="round-switch">
            <span id="round-back">Back to start</span>
            <button
              type="button"
              role="switch"
              aria-checked={round.returnToStart}
              aria-labelledby="round-back"
              className={round.returnToStart ? "on" : ""}
              onClick={() => void setRoundChoice({ returnToStart: !round.returnToStart })}
            >
              <i aria-hidden />
            </button>
          </div>
        </div>

        {error && (
          <p className="round-note round-error" role="alert">
            {error}
          </p>
        )}
        {!plan && !error && (
          <p className={`round-note${busy ? "" : " round-choose"}`} role="status">
            {busy ?? (round.type ? "" : "Choose what to check.")}
          </p>
        )}

        {plan && (
          <>
            <p className="round-summary" role="status">
              <strong>{roundSummary(plan.stops.length, plan.lengthM)}</strong>
              {busy && <span className="round-muted"> · {busy}</span>}
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
            {finished && (
              <p className="round-done-note">
                Round complete · {checked.length} of {plan.stops.length} stops checked
              </p>
            )}
            {plan.unreachable.length > 0 && <p className="round-note">Not reachable, left out: {plan.unreachable.join(", ")}</p>}
            <ol className="round-stops">
              <li className="round-start">
                <span className="round-num">●</span>
                <span>Start: {plan.startName}</span>
              </li>
              {plan.stops.map((stop, index) => {
                const done = checked.includes(stop.spaceId);
                return (
                  <li key={stop.spaceId} className={done ? "done" : ""}>
                    <button className="round-stop" onClick={() => useTwin.getState().flyTo(stop.assetIds[0] ?? stop.spaceId)}>
                      <span className="round-num">{done ? "✓" : index + 1}</span>
                      <span className="round-stop-name">{stop.name}</span>
                      <span className="round-muted">{assetLabel(plan.type, stop.assetIds.length)}</span>
                    </button>
                  </li>
                );
              })}
              {plan.returnToStart && (
                <li className="round-start">
                  <span className="round-num">●</span>
                  <span>Back to {plan.startName}</span>
                </li>
              )}
            </ol>
          </>
        )}

        <button className="primary round-go" onClick={() => void startRound()} disabled={!plan || !!busy}>
          {resume && plan ? `Resume (${checked.length} of ${plan.stops.length} done)` : !plan && !busy && !round.type ? "Pick what to check" : "Start round"}
        </button>

        {plan && picking && (
          <p className="round-note" role="status">
            {picking.first ? `${name(picking.first)}: now tap the room next to it.` : "Tap the first room on the map."}{" "}
            <button className="link" onClick={() => pickDoorRooms(false)}>
              Cancel
            </button>
          </p>
        )}
        {plan && !picking && !pendingDoor && (
          <div className="round-links">
            <button
              className="link"
              onClick={() => {
                setPickStart(false);
                pickDoorRooms(true);
              }}
              disabled={!!busy}
              title="Tap two neighbouring rooms on the map"
            >
              What if a door here?
            </button>
            {suggestion && !whatIf && (
              <button className="link" onClick={() => proposeDoor(suggestion[0], suggestion[1])} disabled={!!busy}>
                Try a door: {name(suggestion[0])} ↔ {name(suggestion[1])}
              </button>
            )}
          </div>
        )}
        {plan && pendingDoor && (
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

        <p className="round-hint">
          <MicIcon />
          <span>
            Say “Wanda, check all {plural(prettyType(hintType), 2).toLowerCase()}
            {hintArea}”
          </span>
        </p>
      </section>
    </PhoneSheet>
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

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}

/** #round=<type>&area=<area>[&building=<key>][&door=<id>,<id>] opens the card and plans at once. */
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
