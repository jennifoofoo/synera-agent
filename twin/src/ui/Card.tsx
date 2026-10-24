// One card above the input, never two. Priority: the tapped room/thing (Route here / I'm here / close), then the
// guided step (Step k of n, back/next/stop), then the last reply (2-3 lines, "more"), then the route summary.
// Owner: the Card/Position session, see ARCHITECTURE.md. Every fact comes from `state` (the API); the card only
// shows it and sends the user's taps back as API calls or chat words ("next", "back", "stop").

import { useLayoutEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";
import type { Route } from "../api/types";
import { floorLabel, type BuildingModel } from "../model/model";
import { prettyType } from "../model/palette";
import { useTwin } from "../store";
import "./Card.css";
import { HereChip } from "./HereChip";

export function Card() {
  const model = useTwin((s) => s.model);
  const selection = useTwin((s) => s.selection);
  const guide = useTwin((s) => s.state?.guide ?? null);
  const route = useTwin((s) => s.state?.route ?? null);
  const replyShown = useTwin((s) => s.replyShown);
  const busy = useTwin((s) => s.chatBusy);
  if (!model) return null;

  let card: ReactNode = null;
  if (selection) card = <SelectionCard key={selection.id} model={model} />;
  else if (guide?.active) card = <GuideCard model={model} />;
  else if (busy) card = <ThinkingCard />;
  else if (replyShown) card = <ReplyCard model={model} />;
  else if (route?.ok) card = <RouteCard model={model} route={route} />;

  return (
    <>
      <HereChip />
      {card}
    </>
  );
}

/** The card frame: a floating card on the laptop, a bottom sheet with a grabber on the phone (swipe down = close). */
function Sheet({ className = "", label, onClose, children }: { className?: string; label: string; onClose?: () => void; children: ReactNode }) {
  const profile = useTwin((s) => s.profile);
  const start = useRef<number | null>(null);
  const [drag, setDrag] = useState(0);
  const phone = profile === "worker";
  const down = (event: PointerEvent) => {
    if (!phone || !onClose) return;
    start.current = event.clientY;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  };
  const move = (event: PointerEvent) => {
    if (start.current !== null) setDrag(Math.max(0, event.clientY - start.current));
  };
  const up = () => {
    if (start.current === null) return;
    start.current = null;
    if (drag > 60) onClose?.();
    setDrag(0);
  };
  return (
    <section className={`card ${className}`} role="dialog" aria-label={label} style={drag ? { transform: `translateY(${drag}px)`, transition: "none" } : undefined}>
      {phone && onClose && <div className="card-grab" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} aria-hidden />}
      {children}
    </section>
  );
}

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

// ---------------------------------------------------------------- selection

function SelectionCard({ model }: { model: BuildingModel }) {
  const selection = useTwin((s) => s.selection)!;
  const select = useTwin((s) => s.select);
  const position = useTwin((s) => s.state?.position ?? null);
  const routeTo = useTwin((s) => s.route);
  const ask = useTwin((s) => s.ask);
  const armHere = useTwin((s) => s.armHere);
  const dismissReply = useTwin((s) => s.dismissReply);
  const busy = useTwin((s) => s.chatBusy);
  const [error, setError] = useState<string | null>(null);

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
  const roomId = space?.id ?? connector?.space_ids.find((id) => model.spaceById.get(id)?.floor_id === selection.floor_id);
  const canBeHere = selection.kind === "space" || selection.kind === "point";
  const hereAlready = !!position && position.space_id === roomId;

  const goHere = async () => {
    if (!roomId) return;
    setError(null);
    if (position && position.space_id !== roomId) {
      // Known start: the route comes straight from the routing API, no language model involved.
      try {
        await routeTo(position.space_id, roomId);
        dismissReply(); // the route summary replaces an older reply
        select(null);
      } catch (e) {
        setError((e as Error).message);
      }
    } else {
      // No start yet: the agent asks "Where are you?" (or uses what it knows).
      void ask(`How do I get to ${title}${floor ? ` (${floor})` : ""}?`);
    }
  };
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
      {error && <div className="card-note">{error}</div>}
      {roomId && (
        <div className="card-actions">
          <button className="primary" disabled={busy || hereAlready} onClick={() => void goHere()} title={position ? `From ${spaceName(model, position.space_id)}` : "I'll ask where you are"}>
            Route here
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
    <Sheet className="card-guide" label={`Step ${step} of ${guide.step_count}`}>
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
      {busy ? <div className="card-text card-muted">…</div> : <Clamped text={last?.text ?? `Go to ${to}.`} />}
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

function ThinkingCard() {
  return (
    <Sheet className="card-reply card-thinking" label="Thinking">
      <div className="thinking" aria-live="polite">
        <i />
        <i />
        <i />
      </div>
    </Sheet>
  );
}

function ReplyCard({ model }: { model: BuildingModel }) {
  const chat = useTwin((s) => s.chat);
  const dismissReply = useTwin((s) => s.dismissReply);
  const route = useTwin((s) => s.state?.route ?? null);
  const last = chat[chat.length - 1];
  if (!last) return null;
  return (
    <Sheet className="card-reply" label="Reply" onClose={dismissReply}>
      <div className="card-reply-body">
        <Clamped text={last.text} />
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
