// One card above the input, never two. Priority: directions (From/To panel at the top, summary + Start here), the
// tapped room/thing (Route / I'm here / close), then the guided step (Step k of n, back/next/stop), then the last reply (2-3 lines, "more"), then the route summary.
// Owner: the Card/Position session, see ARCHITECTURE.md. Every fact comes from `state` (the API); the card only
// shows it and sends the user's taps back as API calls or chat words ("next", "back", "stop").

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { Route } from "../api/types";
import { floorLabel, type BuildingModel } from "../model/model";
import { prettyType } from "../model/palette";
import { HERE, useTwin, type Selection } from "../store";
import { withoutAnswerLine } from "../voice";
import "./Card.css";
import { HereChip } from "./HereChip";
import { DirectionsPanel, DirectionsSummary } from "./Directions";
import { PhoneSheet } from "./PhoneSheet";

export function Card() {
  const model = useTwin((s) => s.model);
  const selection = useTwin((s) => s.selection);
  const guide = useTwin((s) => s.state?.guide ?? null);
  const route = useTwin((s) => s.state?.route ?? null);
  const replyShown = useTwin((s) => s.replyShown);
  const busy = useTwin((s) => s.chatBusy);
  const draft = useTwin((s) => s.draft);
  const directions = useTwin((s) => s.directions);
  if (!model || draft) return null; // a Level 4 draft has its own ids; Route/I'm here would hit the API with them

  let card: ReactNode = null;
  if (directions) card = <DirectionsCard model={model} />;
  else if (selection) card = <SelectionCard key={selection.id} model={model} />;
  else if (guide?.active) card = <GuideCard model={model} />;
  else if (busy) card = null; // the Omnibox shows "thinking" above the input
  else if (replyShown) card = <ReplyCard model={model} />;
  else if (route?.ok) card = <RouteCard model={model} route={route} />;

  return (
    <>
      <HereChip />
      {directions && <DirectionsPanel model={model} />}
      {card}
    </>
  );
}

/** Bottom card while the From/To panel is open. A room tapped meanwhile fills the field being edited (else To). */
function DirectionsCard({ model }: { model: BuildingModel }) {
  const selection = useTwin((s) => s.selection);
  const select = useTwin((s) => s.select);
  const close = useTwin((s) => s.closeDirections);
  useEffect(() => {
    if (!selection) return;
    const room = roomOf(model, selection);
    const { directions, setDirectionsFrom, setDirectionsTo } = useTwin.getState();
    select(null);
    if (!room || !directions) return;
    if (directions.editing === "from") setDirectionsFrom(room);
    else setDirectionsTo(room);
  }, [selection, model, select]);
  // Only a route for the current From/To (a stale one stays hidden while the new one is computed).
  const ready = useTwin((s) => {
    const d = s.directions;
    const route = s.state?.route;
    const from = d?.from === HERE ? s.state?.position?.space_id : d?.from;
    if (!route || !from || !d?.to) return false;
    return !route.ok || (route.start === from && route.destination === d.to); // a failed route says why
  });
  if (!ready) return null; // the panel at the top says what is missing
  return (
    <Sheet className="card-directions" label="Route" onClose={() => close()}>
      <DirectionsSummary model={model} />
    </Sheet>
  );
}

/** The card frame: a floating card on the laptop; on the phone the PhoneSheet (phone session) is the surface. */
function Sheet({ className = "", label, onClose, peek, children }: { className?: string; label: string; onClose?: () => void; peek?: boolean; children: ReactNode }) {
  return (
    <PhoneSheet open onClose={onClose ?? noop} label={label} peek={peek}>
      <section className={`card ${className}`} role="dialog" aria-label={label}>
        {children}
      </section>
    </PhoneSheet>
  );
}

const noop = () => {};

function CloseButton({ onClick, label = "Close" }: { onClick: () => void; label?: string }) {
  return (
    <button className="x" onClick={onClick} aria-label={label}>
      ×
    </button>
  );
}

function spaceName(model: BuildingModel, id: string | undefined): string {
  if (!id) return "";
  return model.spaceById.get(id)?.name || model.connectorBySpace.get(id)?.name || id;
}

function floorName(model: BuildingModel, floorId: string | undefined): string {
  const floor = floorId ? model.floorById.get(floorId) : undefined;
  return floor ? floorLabel(floor) : "";
}

/** The room a selection stands for: the room itself, a spot's or thing's room, or a stair/lift's space on that floor. */
function roomOf(model: BuildingModel, selection: Selection): string | undefined {
  const spaceId = selection.kind === "space" ? selection.id : selection.space_id;
  if (spaceId && model.spaceById.has(spaceId)) return spaceId;
  if (selection.kind === "asset") return model.assetById.get(selection.id)?.space_id;
  const connector = selection.kind === "connector" ? model.connectorById.get(selection.id) : undefined;
  return connector?.space_ids.find((id) => model.spaceById.get(id)?.floor_id === selection.floor_id);
}

// ---------------------------------------------------------------- selection

function SelectionCard({ model }: { model: BuildingModel }) {
  const selection = useTwin((s) => s.selection)!;
  const select = useTwin((s) => s.select);
  const position = useTwin((s) => s.state?.position ?? null);
  const ask = useTwin((s) => s.ask);
  const armHere = useTwin((s) => s.armHere);
  const openDirections = useTwin((s) => s.openDirections);
  const busy = useTwin((s) => s.chatBusy);

  const space = model.spaceById.get(selection.kind === "space" ? selection.id : (selection.space_id ?? ""));
  const asset = selection.kind === "asset" ? model.assetById.get(selection.id) : undefined;
  const connector = selection.kind === "connector" ? model.connectorById.get(selection.id) : space ? model.connectorBySpace.get(space.id) : undefined;
  const title = asset?.name ?? connector?.name ?? (space?.name || prettyType(space?.room_type ?? "Spot"));
  const floor = floorName(model, selection.floor_id);
  const context = asset
    ? `${prettyType(asset.type)} in ${space?.name || "this room"}`
    : connector
      ? `${connector.kind === "lift" ? "Lift" : "Stairs"} · ${connector.floor_ids.length} floors${connector.step_free ? " · step-free" : ""}`
      : space
        ? `${prettyType(space.room_type)} · ${Math.round(space.area_m2)} m²`
        : "";
  // Rooms (and spots in a room) can be a destination or "where I am"; a thing routes to its room.
  const roomId = roomOf(model, selection);
  const canBeHere = selection.kind === "space" || selection.kind === "point";
  const hereAlready = !!position && position.space_id === roomId;

  const imHere = () => {
    // context.here travels with this one message; the server validates it and sets the position (source "click").
    armHere(true);
    void ask("I'm here.");
  };

  return (
    <Sheet className="card-selection" label={title} onClose={() => select(null)}>
      <div className="card-head">
        <div className="card-title">
          <span className="sel-dot" aria-hidden />
          <strong>{title}</strong>
        </div>
        <CloseButton onClick={() => select(null)} />
      </div>
      <div className="card-line">
        {floor}
        {floor && context ? " · " : ""}
        {context}
      </div>
      {roomId && (
        <div className="card-actions">
          <button className="primary" onClick={() => openDirections(roomId)}>
            Route
          </button>
          {canBeHere && (
            <button disabled={busy || hereAlready} onClick={imHere}>
              {hereAlready ? "You're here" : "I'm here"}
            </button>
          )}
        </div>
      )}
    </Sheet>
  );
}

// ---------------------------------------------------------------- guided walking

function GuideCard({ model }: { model: BuildingModel }) {
  const guide = useTwin((s) => s.state!.guide!);
  const chat = useTwin((s) => s.chat);
  const ask = useTwin((s) => s.ask);
  const busy = useTwin((s) => s.chatBusy);
  const last = [...chat].reverse().find((message) => message.role === "agent");
  const step = guide.step_index + 1;
  const to = spaceName(model, guide.leg.to_space_id);
  const target = spaceName(model, guide.target_space_id);
  return (
    <Sheet className="card-guide" label={`Step ${step} of ${guide.step_count}`} peek>
      <div className="card-head">
        <span className="card-kicker">
          Step {step} of {guide.step_count}
          <span className="card-muted"> · to {target}</span>
        </span>
        <div className="steps" aria-hidden>
          {Array.from({ length: Math.min(guide.step_count, 12) }, (_, i) => (
            <i key={i} className={i < guide.step_index ? "done" : i === guide.step_index ? "now" : ""} />
          ))}
        </div>
      </div>
      {busy ? <div className="card-text card-muted">…</div> : <Clamped text={last ? withoutAnswerLine(last.text) : `Go to ${to}.`} />}
      <div className="card-actions">
        <button disabled={busy || guide.step_index === 0} onClick={() => void ask("back")}>
          Back
        </button>
        <button className="primary" disabled={busy} onClick={() => void ask("next")}>
          {step === guide.step_count ? "I'm there" : "Next"}
        </button>
        <button className="quiet" disabled={busy} onClick={() => void ask("stop")}>
          Stop
        </button>
      </div>
    </Sheet>
  );
}

// ---------------------------------------------------------------- reply

function ReplyCard({ model }: { model: BuildingModel }) {
  const chat = useTwin((s) => s.chat);
  const dismissReply = useTwin((s) => s.dismissReply);
  const route = useTwin((s) => s.state?.route ?? null);
  const last = chat[chat.length - 1];
  if (!last) return null;
  return (
    <Sheet className="card-reply" label="Reply" onClose={dismissReply}>
      <div className="card-reply-body">
        <Clamped text={withoutAnswerLine(last.text)} />
        <CloseButton onClick={dismissReply} label="Dismiss" />
      </div>
      {last.note && <div className="card-note">{last.note}</div>}
      {route?.ok && <RouteLine model={model} route={route} />}
    </Sheet>
  );
}

/** 3 lines, then "more". Only shows "more" when the text really is longer. */
function Clamped({ text }: { text: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [long, setLong] = useState(false);
  useLayoutEffect(() => {
    setOpen(false);
  }, [text]);
  useLayoutEffect(() => {
    const element = ref.current;
    if (element && !open) setLong(element.scrollHeight > element.clientHeight + 1);
  }, [text, open]);
  return (
    <div className="card-clamp">
      <div ref={ref} className={`card-text ${open ? "open" : ""}`}>
        {text}
      </div>
      {long && (
        <button className="link" onClick={() => setOpen(!open)}>
          {open ? "less" : "more"}
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- route summary

function routeFacts(model: BuildingModel, route: Route) {
  const changes = route.floor_changes ?? [];
  // Step-free when asked for, or when every floor change uses a step-free connector (a lift).
  const stepFree = !!route.step_free || changes.every((change) => model.connectorById.get(change.connector_id)?.step_free);
  return {
    length: route.length_m !== undefined ? `${Math.round(route.length_m)} m` : "",
    floors: route.floors?.length ?? 1,
    stepFree,
    destination: spaceName(model, route.destination),
  };
}

function RouteLine({ model, route }: { model: BuildingModel; route: Route }) {
  const clearRoute = useTwin((s) => s.clearRoute);
  const ask = useTwin((s) => s.ask);
  const facts = routeFacts(model, route);
  return (
    <div className="route-line">
      <span className="route-facts">
        {facts.length && <b>{facts.length}</b>}
        <span>
          {facts.floors} {facts.floors === 1 ? "floor" : "floors"}
        </span>
        <span className={facts.stepFree ? "ok" : "warn"}>{facts.stepFree ? "step-free" : "has stairs"}</span>
      </span>
      <span className="route-links">
        <button className="link" onClick={() => void ask("guide me")}>
          Guide me
        </button>
        <button className="link quiet-link" onClick={() => void clearRoute()}>
          Clear
        </button>
      </span>
    </div>
  );
}

function RouteCard({ model, route }: { model: BuildingModel; route: Route }) {
  const clearRoute = useTwin((s) => s.clearRoute);
  const ask = useTwin((s) => s.ask);
  const busy = useTwin((s) => s.chatBusy);
  const facts = routeFacts(model, route);
  return (
    <Sheet className="card-route" label={`Route to ${facts.destination}`} onClose={() => void clearRoute()}>
      <div className="card-head">
        <div className="card-title">
          <span className="route-dot" aria-hidden />
          <strong>To {facts.destination}</strong>
        </div>
        <CloseButton onClick={() => void clearRoute()} label="Clear route" />
      </div>
      <div className="card-line route-facts">
        {facts.length && <b>{facts.length}</b>}
        <span>
          {facts.floors} {facts.floors === 1 ? "floor" : "floors"}
        </span>
        <span className={facts.stepFree ? "ok" : "warn"}>{facts.stepFree ? "step-free" : "has stairs"}</span>
      </div>
      <div className="card-actions">
        <button className="primary" disabled={busy} onClick={() => void ask("guide me")}>
          Guide me
        </button>
      </div>
    </Sheet>
  );
}
