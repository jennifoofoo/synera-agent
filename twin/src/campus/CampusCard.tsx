// The campus card above the input: the route's legs ("1/3 Research building · 2/3 Covered walkway 85 m · ..."),
// or the tapped link (length, step-free, close / reopen), or a campus message. Never next to another card: the
// selection, a guide step or a reply win.

import { useEffect, useRef } from "react";
import type { CampusLink } from "../api/campus";
import { PhoneSheet } from "../ui/PhoneSheet";
import { useTwin } from "../store";
import { buildingOf, linkOf, stepLabel, steps, useCampus } from "./campusStore";

export function CampusCard() {
  const mode = useCampus((s) => s.mode);
  const route = useCampus((s) => s.route);
  const selectedLink = useCampus((s) => s.selectedLink);
  const view = useCampus((s) => s.view);
  const error = useCampus((s) => s.error);
  const note = useCampus((s) => s.note);
  const selection = useTwin((s) => s.selection);
  const guide = useTwin((s) => s.state?.guide?.active);
  const replyShown = useTwin((s) => s.replyShown);
  const busy = useTwin((s) => s.chatBusy);
  if (mode === "off" || !view?.loaded) return null;
  if (selection || guide || replyShown || busy) return null;

  const link = mode === "site" ? linkOf(view, selectedLink) : null;
  if (link) return <LinkCard link={link} />;
  if (route?.ok) return <LegsCard />;
  if (error || note) return <MessageCard />;
  return null;
}

function Frame({ label, onClose, className = "", children }: { label: string; onClose: () => void; className?: string; children: React.ReactNode }) {
  return (
    <PhoneSheet open onClose={onClose} label={label}>
      <section className={`card campus-card ${className}`} role="dialog" aria-label={label}>
        {children}
      </section>
    </PhoneSheet>
  );
}

function LegsCard() {
  const route = useCampus((s) => s.route)!;
  const step = useCampus((s) => s.step);
  const goStep = useCampus((s) => s.goStep);
  const clearRoute = useCampus((s) => s.clearRoute);
  const view = useCampus((s) => s.view);
  const legs = steps(route);
  const last = [...legs].reverse().find((leg) => leg.kind === "building");
  const destination = last?.kind === "building" ? (last.rooms[last.rooms.length - 1]?.name ?? last.building_name) : "";
  const now = step ?? 0;
  const stepFree = route.step_free;
  const list = useRef<HTMLOListElement>(null);
  useEffect(() => {
    const chip = list.current?.querySelector<HTMLElement>(".campus-step.now");
    if (chip && list.current) list.current.scrollTo({ left: chip.offsetLeft - 14, behavior: "smooth" }); // phones: one sideways row
  }, [now]);
  return (
    <Frame label={`Route to ${destination}`} onClose={clearRoute} className="card-route campus-legs">
      <div className="card-head">
        <div className="card-title">
          <span className="route-dot" aria-hidden />
          <strong>To {destination}</strong>
        </div>
        <button className="x" onClick={clearRoute} aria-label="Clear route">
          ×
        </button>
      </div>
      <div className="card-line route-facts">
        <b>{Math.round(route.length_m ?? 0)} m</b>
        <span>{(route.buildings ?? []).length} buildings</span>
        {stepFree && <span className="ok">step-free</span>}
      </div>
      <ol className="campus-steps" aria-label="Legs" ref={list}>
        {legs.map((leg, index) => (
          <li key={index}>
            <button className={`campus-step ${index === now ? "now" : ""} ${index < now ? "done" : ""} leg-${leg.kind}`} onClick={() => void goStep(index)} aria-current={index === now ? "step" : undefined}>
              <span className="n">
                {index + 1}/{legs.length}
              </span>{" "}
              {stepLabel(leg)}
            </button>
          </li>
        ))}
      </ol>
      <div className="card-actions">
        <button disabled={now <= 0} onClick={() => void goStep(now - 1)}>
          Back
        </button>
        {now < legs.length - 1 ? (
          <button className="primary" onClick={() => void goStep(now + 1)}>
            Next: {shortLabel(legs[now + 1], view)}
          </button>
        ) : (
          <button className="primary" onClick={clearRoute}>
            Done
          </button>
        )}
      </div>
    </Frame>
  );
}

function shortLabel(leg: ReturnType<typeof steps>[number], view: ReturnType<typeof useCampus.getState>["view"]): string {
  if (leg.kind === "link") return leg.name;
  return buildingOf(view, leg.building_id)?.name ?? leg.building_name;
}

function LinkCard({ link }: { link: CampusLink }) {
  const selectLink = useCampus((s) => s.selectLink);
  const setLinkClosed = useCampus((s) => s.setLinkClosed);
  const view = useCampus((s) => s.view);
  const busy = useCampus((s) => s.busy);
  const note = useCampus((s) => s.note);
  const from = buildingOf(view, link.from.building_id)?.name ?? link.from.building_id;
  const to = buildingOf(view, link.to.building_id)?.name ?? link.to.building_id;
  const kind = link.kind.charAt(0).toUpperCase() + link.kind.slice(1);
  return (
    <Frame label={link.name} onClose={() => selectLink(null)} className={`campus-link-card ${link.closed ? "closed" : ""}`}>
      <div className="card-head">
        <div className="card-title">
          <span className={`campus-link-dot ${link.closed ? "closed" : ""}`} aria-hidden />
          <strong>{link.name}</strong>
        </div>
        <button className="x" onClick={() => selectLink(null)} aria-label="Close">
          ×
        </button>
      </div>
      <div className="card-line">
        {kind} · {Math.round(link.length_m)} m{link.length_estimated ? " (estimated)" : ""}
        {link.level_delta ? ` · ${Math.abs(link.level_delta)} floor${Math.abs(link.level_delta) > 1 ? "s" : ""} up` : ""}
        {link.step_free ? " · step-free" : " · with steps"}
      </div>
      <div className="card-line">
        {from} ↔ {to}
      </div>
      {link.closed && <div className="card-note campus-closed">Closed</div>}
      {note && <div className="card-line campus-effect">{note}</div>}
      <div className="card-actions">
        <button className={link.closed ? "primary" : "danger"} disabled={busy} onClick={() => void setLinkClosed(link.id, !link.closed)}>
          {link.closed ? "Reopen" : "Close"} {link.kind}
        </button>
      </div>
    </Frame>
  );
}

function MessageCard() {
  const error = useCampus((s) => s.error);
  const note = useCampus((s) => s.note);
  const clear = () => useCampus.setState({ error: null, note: null });
  return (
    <Frame label="Campus" onClose={clear} className="campus-message">
      <div className="card-head">
        <div className="card-line">{error ?? note}</div>
        <button className="x" onClick={clear} aria-label="Close">
          ×
        </button>
      </div>
    </Frame>
  );
}
