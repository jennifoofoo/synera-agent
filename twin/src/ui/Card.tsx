// One card above the input, never two. Priority: directions (From/To panel at the top, summary + Guide me), the
// tapped room/thing (Route / I'm here / close), then the guided step (Step k of n, back/next/stop), then the last reply
// (2-3 lines, "more"; a reply that drew a route is the one-line route card), then the route card.
// Owner: the Card/Position session, see ARCHITECTURE.md. Every fact comes from `state` (the API); the card only
// shows it and sends the user's taps back as API calls or chat words ("next", "back", "stop").

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Asset, Route } from "../api/types";
import { formatPoint } from "../model/format";
import { floorLabel, type BuildingModel } from "../model/model";
import { prettyType } from "../model/palette";
import { HERE, useTwin, walkLines, type Selection } from "../store";
import { withoutAnswerLine } from "../voice";
import "./Card.css";
import { HereChip, StepFreeChip } from "./HereChip";
import { DirectionsPanel, DirectionsSummary } from "./Directions";
import { PhoneSheet } from "./PhoneSheet";
import { readable } from "../walkInfo";
import { AvoidsClosed } from "./AvoidsClosed";
import { RouteChips } from "./RouteChips";
import { TurnIcon, rideUp } from "./Walk";
import { useRound } from "../round/round";
import { KnowledgeButton } from "./KnowledgeGraph";
import { NoteGlyph } from "./Facts";
import { notesIn, openNotes, useNotes } from "../notes/notesStore";

export function Card() {
  const model = useTwin((s) => s.model);
  const selection = useTwin((s) => s.selection);
  const guide = useTwin((s) => s.state?.guide ?? null);
  const route = useTwin((s) => s.state?.route ?? null);
  const replyShown = useTwin((s) => s.replyShown);
  const busy = useTwin((s) => s.chatBusy);
  const draft = useTwin((s) => s.draft);
  const campusRoute = useTwin((s) => s.campusRoute);
  const directions = useTwin((s) => s.directions);
  // Decision A (docs/specs/inspection-round.md): while a round is planned or walked, the round panel owns the drawn
  // route, so the normal route card (a second "Guide me") stays hidden.
  const roundActive = useRound((s) => !!s.plan && (s.guiding || s.open));
  if (!model || draft) return null; // a Level 4 draft has its own ids; Route/I'm here would hit the API with them

  let card: ReactNode = null;
  const placeCard = !directions && !!selection;
  if (directions) card = <DirectionsCard model={model} />;
  else if (selection) card = <SelectionCard key={selection.id} model={model} />;
  else if (guide?.active) card = <GuideCard model={model} />;
  else if (busy) card = null; // the Omnibox shows "thinking" above the input
  else if (replyShown) card = <ReplyCard model={model} />;
  else if (route?.ok && !campusRoute && !roundActive) card = <RouteCard model={model} route={route} />;

  return (
    <>
      {/* A place card names the position itself ("From: …"), so the pill does not cover the plan meanwhile. */}
      {!placeCard && <HereChip />}
      <StepFreeChip />
      <TapWhereHint />
      {directions && <DirectionsPanel model={model} />}
      {card}
    </>
  );
}

/** Wanda asked "Where are you?": one calm line, the next tap on the map answers it (tapAnswer.ts). × keeps taps normal. */
function TapWhereHint() {
  const awaiting = useTwin((s) => !!s.awaitingPlace && !s.directions);
  const dismiss = useTwin((s) => s.dismissAwaitingPlace);
  if (!awaiting) return null;
  return (
    <div className="here-chip tap-where" role="status" data-testid="tap-where">
      <span className="here-name">
        <span className="here-dot" aria-hidden />
        <span>Tap where you are</span>
      </span>
      <button className="x" onClick={dismiss} aria-label="Not now">
        ×
      </button>
    </div>
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
  const setHere = useTwin((s) => s.setHere);
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
  // A tap on the floor leaves a pin; its exact spot (model metres) is kept as a data attribute only.
  const pointText = selection.point && (selection.kind === "space" || selection.kind === "point") ? formatPoint(selection.point) : "";
  // Rooms (and spots in a room) can be a destination or "where I am"; a thing routes to its room.
  const roomId = roomOf(model, selection);
  const canBeHere = selection.kind === "space" || selection.kind === "point";
  const hereAlready = !!position && position.space_id === roomId;
  // Details on demand (semantic zoom, level 4): the equipment in a tapped room, not for a thing or a stair/lift.
  const equipmentRoom = !asset && !connector ? space?.id : undefined;
  const equipment = useMemo(() => (equipmentRoom ? equipmentOf(model.assetById.values(), equipmentRoom) : null), [model, equipmentRoom]);
  // Notes already left here (one quiet line that opens them), and "Note" adds one for exactly this room or thing
  // (openNotes freezes the tapped place: room, device or door, see notesStore.currentPlace).
  const allNotes = useNotes((s) => s.notes);
  const notesHere = useMemo(() => (roomId ? notesIn([roomId]) : []), [roomId, allNotes]); // eslint-disable-line react-hooks/exhaustive-deps

  const imHere = () => {
    // No agent call: the position is set on screen now and travels as context.here with the next chat message.
    if (!roomId) return;
    const floorId = selection.floor_id ?? model.spaceById.get(roomId)?.floor_id;
    if (!floorId) return;
    setHere({ space_id: roomId, floor_id: floorId, point: selection.kind === "point" || selection.kind === "space" ? (selection.point ?? null) : null });
    select(null);
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
      {/* Coordinates are not for people: only a data attribute for tests and debugging. */}
      <div className="card-line" data-testid={pointText ? "card-point" : undefined} data-point={pointText || undefined}>
        {floor}
        {floor && context ? " · " : ""}
        {context}
      </div>
      {equipment && equipment.items.length > 0 && (
        <div className="card-line card-equipment" data-testid="card-equipment">
          {equipment.items.join(", ")}
          {equipment.more > 0 ? `, +${equipment.more} more` : ""}
        </div>
      )}
      {position && !hereAlready && (
        <div className="card-line card-from" data-testid="card-from">
          <span className="here-dot" aria-hidden />
          From: {spaceName(model, position.space_id)}
        </div>
      )}
      {notesHere.length > 0 && (
        <button className="link card-notes-line" data-testid="card-notes" onClick={() => openNotes("here")}>
          <NoteGlyph size={14} />
          <span>
            {notesHere.length} {notesHere.length === 1 ? "note" : "notes"} · {notesHere[0].text || "Photo"}
          </span>
        </button>
      )}
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
          <button className="card-note-add" onClick={() => openNotes("add")} aria-label="Add a note here" title="Add a note or photo for this place">
            <NoteGlyph size={16} />
            Note
          </button>
          <KnowledgeButton roomId={roomId} />
        </div>
      )}
    </Sheet>
  );
}

const EQUIPMENT_SHOWN = 6;
const EQUIPMENT_RANK: Record<string, number> = { machine: 0, equipment: 1, fixture: 2 };

/** The equipment in a room for its card: machines, then equipment, then fixtures (no furniture), one entry per type
 * with a count ("Cnc lathe ×2"), the most frequent first; at most EQUIPMENT_SHOWN entries and how many more. */
export function equipmentOf(assets: Iterable<Asset>, spaceId: string): { items: string[]; more: number } {
  const byType = new Map<string, { rank: number; count: number }>();
  for (const asset of assets) {
    const rank = EQUIPMENT_RANK[asset.category ?? ""];
    if (asset.space_id !== spaceId || rank === undefined) continue;
    const entry = byType.get(asset.type);
    if (entry) entry.count += 1;
    else byType.set(asset.type, { rank, count: 1 });
  }
  const sorted = [...byType].sort(([ta, a], [tb, b]) => a.rank - b.rank || b.count - a.count || ta.localeCompare(tb));
  const items = sorted.slice(0, EQUIPMENT_SHOWN).map(([type, { count }]) => `${prettyType(type)}${count > 1 ? ` ×${count}` : ""}`);
  return { items, more: Math.max(0, sorted.length - EQUIPMENT_SHOWN) };
}

// ---------------------------------------------------------------- guided walking

function GuideCard({ model }: { model: BuildingModel }) {
  const guide = useTwin((s) => s.state!.guide!);
  const chat = useTwin((s) => s.chat);
  const ask = useTwin((s) => s.ask);
  const busy = useTwin((s) => s.chatBusy);
  const end = useEndRoute();
  useEscape(end);
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
        <button className="quiet" disabled={busy} onClick={end} title="End the route (Esc)">
          End route
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
  // A reply that drew the route is the route card: one line and "Guide me", the reply text behind "Steps".
  if (last.route && route?.ok) return <RouteCard model={model} route={route} details={withoutAnswerLine(last.text)} note={last.note} />;
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
        <button className="link" aria-expanded={open} onClick={() => setOpen(!open)}>
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
    steps: walkLines(route.steps).length,
    stepFree,
    destination: spaceName(model, route.destination),
  };
}

/** One action ends the route: the agent's guide (if one runs) and the drawn route. */
export function useEndRoute() {
  const clearRoute = useTwin((s) => s.clearRoute);
  const ask = useTwin((s) => s.ask);
  const guiding = useTwin((s) => !!s.state?.guide?.active);
  return () => {
    // The guide's reply carries the server state, so the route is cleared after it (else the reply redraws it).
    void (async () => {
      if (guiding) await ask("stop");
      await clearRoute();
    })();
  };
}

/** Esc runs the action, unless the key belongs to a text field. */
export function useEscape(action: () => void) {
  const ref = useRef(action);
  ref.current = action;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      ref.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

/** The route in one line under a reply about something else: facts, "Guide me", "End route". */
function RouteLine({ model, route }: { model: BuildingModel; route: Route }) {
  const ask = useTwin((s) => s.ask);
  const end = useEndRoute();
  const facts = routeFacts(model, route);
  return (
    <div className="route-line">
      <span className="route-facts">
        {facts.length && <b>{facts.length}</b>}
        {facts.floors > 1 && <span>{facts.floors} floors</span>}
        <span className={facts.stepFree ? "ok" : "warn"}>{facts.stepFree ? "step-free" : "has stairs"}</span>
      </span>
      <span className="route-links">
        <button className="link" onClick={() => void ask("guide me")}>
          Guide me
        </button>
        <button className="link quiet-link" onClick={end}>
          End route
        </button>
      </span>
    </div>
  );
}

/** The route card: destination, fact chips, the numbered steps (the reply that drew the route, else the route's own
 * steps), then "Guide me" and "End route". Guiding speaks the steps one by one. */
function RouteCard({ model, route, details, note }: { model: BuildingModel; route: Route; details?: string; note?: string }) {
  const ask = useTwin((s) => s.ask);
  const busy = useTwin((s) => s.chatBusy);
  const end = useEndRoute();
  useEscape(end);
  const facts = routeFacts(model, route);
  const steps = walkLines(route.steps).map(readable);
  const [stepsOpen, setStepsOpen] = useState(false);
  const toggleText = details ? "Details" : `${steps.length} ${steps.length === 1 ? "step" : "steps"}`;
  const hasList = details ? true : steps.length > 0;
  return (
    <Sheet className="card-route" label={`Route to ${facts.destination}`} onClose={end}>
      <div className="route-head">
        <span className="route-dot" aria-hidden />
        <strong className="route-dest">{facts.destination}</strong>
      </div>
      <div className="route-summary-row">
        <RouteChips length={facts.length} lengthM={route.length_m} floors={facts.floors} stepFree={facts.stepFree} />
        {hasList && (
          <button type="button" className="link route-steps-toggle" aria-expanded={stepsOpen} onClick={() => setStepsOpen((v) => !v)}>
            {toggleText}
          </button>
        )}
      </div>
      <AvoidsClosed model={model} route={route} />
      {note && <div className="card-note">{note}</div>}
      {details ? (
        stepsOpen && <div className="card-text open route-details">{details}</div>
      ) : (
        stepsOpen &&
        steps.length > 0 && (
          <ol className="route-steps">
            {steps.map((line, index) => (
              <li key={index}>
                <TurnIcon line={line} up={rideUp(route.floor_changes, steps, index)} />
                <span>{line}</span>
              </li>
            ))}
          </ol>
        )
      )}
      <div className="card-actions card-actions-stack">
        <button className="primary" disabled={busy} onClick={() => void ask("guide me")}>
          Guide me
        </button>
        <button className="ghost" onClick={end} title="End the route (Esc)">
          End route
        </button>
      </div>
    </Sheet>
  );
}

