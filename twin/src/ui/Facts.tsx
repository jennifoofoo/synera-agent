// Place knowledge on the page (docs/specs/place-knowledge-page.md, items 1, 2, 4-7): the "Notes & photos" switch,
// the pin card (text, age, author, photo, history, "Resolved"), the photo viewer, the "Saved · Undo" chip, the facts
// line while walking, and what happens when Wanda's reply names facts. Facts come from state.facts (the API);
// "Resolved" goes through the chat ("Fixed: …" with the place as context), so Wanda's card and "yes" still apply.

import { useEffect, useMemo, useState } from "react";
import { factsApi } from "../api/facts";
import type { ChatReply, Fact } from "../api/types";
import { factPlace, factPlaceName, factsForStep, pinFacts, sinceText, untilText, whenText } from "../model/facts";
import type { BuildingModel } from "../model/model";
import { IssueGlyph, NoteGlyph } from "../scene/FactPins";
import { replyHooks, useTwin } from "../store";
import { UNDO_MS, useFacts } from "./factsStore";
import "./Facts.css";

// ---------------------------------------------------------------- layer switch

/** "Notes & photos" beside the floor numbers (laptop and phone): pins for every note and problem on the floor. */
export function NotesToggle() {
  const layer = useFacts((s) => s.layer);
  const setLayer = useFacts((s) => s.setLayer);
  const count = useTwin((s) => pinFacts(s.state?.facts).length);
  const title = layer ? "Hide notes & photos" : `Show notes & photos${count ? ` (${count})` : ""}`;
  return (
    <button className={`rail-toggle rail-notes ${layer ? "active" : ""}`} onClick={() => setLayer(!layer)} title={title} aria-label="Notes & photos" aria-pressed={layer} data-testid="notes-toggle">
      <NoteGlyph />
      {!layer && count > 0 && <span className="rail-notes-count" aria-hidden>{count > 9 ? "9+" : count}</span>}
    </button>
  );
}

// ---------------------------------------------------------------- pin card

/** The card of a tapped pin: per fact its text, since when, who, the photo, and "Resolved" for an open problem;
 * "History" lists the place's earlier facts (resolved and expired ones too). Card.tsx frames it. */
export function FactCard({ model }: { model: BuildingModel }) {
  const pin = useFacts((s) => s.pin)!;
  const close = useFacts((s) => s.openPin);
  const all = useTwin((s) => s.state?.facts);
  const ids = pin.facts.map((fact) => fact.id);
  // Re-read from the state: a fact resolved meanwhile leaves the card.
  const facts = useMemo(() => pinFacts(all).filter((fact) => ids.includes(fact.id)), [all, ids.join(" ")]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!facts.length) close(null);
  }, [facts.length, close]);
  if (!facts.length) return null;
  const issue = facts.some((fact) => fact.kind === "issue");
  return (
    <>
      <div className="card-head">
        <div className="card-title">
          <span className={`fact-mark ${issue ? "fact-issue" : "fact-note"}`} aria-hidden>
            {issue ? <IssueGlyph /> : <NoteGlyph />}
          </span>
          <strong>{factPlaceName(model, facts[0])}</strong>
        </div>
        <button className="x" onClick={() => close(null)} aria-label="Close">
          ×
        </button>
      </div>
      {facts.map((fact) => (
        <FactEntry key={fact.id} fact={fact} />
      ))}
      <History spaceId={facts[0].anchor.space_id} />
    </>
  );
}

function FactEntry({ fact }: { fact: Fact }) {
  const ask = useTwin((s) => s.ask);
  const busy = useTwin((s) => s.chatBusy);
  const showPhoto = useFacts((s) => s.showPhoto);
  const close = useFacts((s) => s.openPin);
  const meta = [sinceText(fact.valid_from), fact.author || "Technician", fact.valid_to ? untilText(fact.valid_to) : ""].filter(Boolean).join(" · ");
  const resolve = () => {
    // Through Wanda: she shows the card ("Resolve: …?") and waits for "yes", like every change.
    close(null);
    const anchor = fact.anchor;
    void ask(`Fixed: ${fact.text}`, false, {
      context: { space_id: anchor.space_id, floor_id: anchor.floor_id, ...(anchor.asset_id ? { asset_id: anchor.asset_id } : {}), ...(anchor.point ? { point: anchor.point } : {}) },
    });
  };
  return (
    <div className="fact-entry" data-testid="fact-entry" data-fact-id={fact.id}>
      <div className="fact-text">
        {fact.kind === "issue" && <span className="fact-kind">Problem</span>}
        <span data-testid="fact-text">{fact.text}</span>
      </div>
      <div className="card-line fact-meta" data-testid="fact-meta">
        {meta}
      </div>
      {fact.photo && (
        <button className="fact-thumb" onClick={() => showPhoto({ url: fact.photo!, caption: fact.text })} aria-label="Show the photo" data-testid="fact-photo">
          <img src={fact.photo} alt={`Photo: ${fact.text}`} loading="lazy" />
        </button>
      )}
      {fact.kind === "issue" && (
        <div className="card-actions">
          <button className="primary" disabled={busy} onClick={resolve} data-testid="fact-resolve" title="Tell Wanda it is fixed (she asks you to confirm)">
            Resolved
          </button>
        </div>
      )}
    </div>
  );
}

function History({ spaceId }: { spaceId: string }) {
  const key = useTwin((s) => s.buildingKey);
  const [open, setOpen] = useState(false);
  const [facts, setFacts] = useState<Fact[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open || !key) return;
    let live = true;
    setError("");
    factsApi
      .list(key, spaceId, true)
      .then((list) => live && setFacts(list.filter((fact) => fact.kind !== "closure" || fact.status !== "open")))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [open, key, spaceId]);
  return (
    <div className="fact-history">
      <button className="link" aria-expanded={open} onClick={() => setOpen(!open)} data-testid="fact-history-toggle">
        {open ? "Hide history" : "History"}
      </button>
      {open && (
        <ol className="fact-history-list" data-testid="fact-history">
          {error && <li className="card-note">{error}</li>}
          {!error && facts === null && <li className="card-muted">…</li>}
          {facts?.length === 0 && <li className="card-muted">Nothing earlier here.</li>}
          {facts?.map((fact) => (
            <li key={fact.id} className={`fact-history-${fact.status}`}>
              <span className="fact-when">{whenText(fact.created_at || fact.valid_from)}</span>
              <span>
                {fact.resolves ? "Resolved" : fact.kind === "issue" ? "Problem" : fact.kind === "closure" ? "Closed" : "Note"}: {fact.text}
                <span className="card-muted">
                  {" "}
                  · {fact.author || "Technician"}
                  {fact.status !== "open" && !fact.resolves ? ` · ${fact.status}` : ""}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- photo viewer

/** The photo full size over everything; tap anywhere or Esc closes it. */
export function PhotoViewer() {
  const photo = useFacts((s) => s.photo);
  const showPhoto = useFacts((s) => s.showPhoto);
  useEffect(() => {
    if (!photo) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // Esc closes only the photo, not the card or sheet under it
        event.preventDefault();
        event.stopImmediatePropagation();
        showPhoto(null);
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [photo, showPhoto]);
  if (!photo) return null;
  return (
    <div className="photo-viewer" role="dialog" aria-label="Photo" onClick={() => showPhoto(null)} data-testid="photo-viewer">
      <figure>
        <img src={photo.url} alt={photo.caption} />
        <figcaption>{photo.caption}</figcaption>
      </figure>
      <button className="x" aria-label="Close the photo">
        ×
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- saved / undo

/** "Note saved · Undo" for as long as the server can still undo it (2 minutes). */
export function SavedChip() {
  const saved = useFacts((s) => s.saved);
  const setSaved = useFacts((s) => s.setSaved);
  const key = useTwin((s) => s.buildingKey);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!saved) return;
    setError("");
    const timer = window.setTimeout(() => setSaved(null), Math.max(0, saved.at + UNDO_MS - Date.now()));
    return () => window.clearTimeout(timer);
  }, [saved, setSaved]);
  if (!saved || !key) return null;
  const undo = async () => {
    try {
      const result = await factsApi.undo(key);
      if (result.state) useTwin.getState().applyState(result.state);
      setSaved(null);
      if (!result.undone) setError("Too late to undo.");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="here-chip saved-chip" role="status" data-testid="fact-saved">
      <span className="here-name">
        <span>{error || (saved.fact.kind === "issue" ? "Problem saved" : "Note saved")}</span>
      </span>
      {!error && (
        <button className="link saved-undo" onClick={() => void undo()} data-testid="fact-undo">
          Undo
        </button>
      )}
      <button className="x" onClick={() => setSaved(null)} aria-label="Dismiss">
        ×
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- while walking

/** While walking: one quiet line with the notes of the room the current step enters (Wanda reads them out). */
export function WalkFactsLine({ line, last }: { line: string; last: boolean }) {
  const model = useTwin((s) => s.model);
  const facts = useTwin((s) => s.state?.facts);
  const destination = useTwin((s) => s.state?.route?.destination ?? null);
  const here = useMemo(() => (model && facts ? factsForStep(model, facts, line, destination, last) : []), [model, facts, line, destination, last]);
  return <FactsLine facts={here} />;
}

/** The same line for the agent's guide: the notes of the room the leg goes to. */
export function GuideFactsLine({ spaceId }: { spaceId: string }) {
  const facts = useTwin((s) => s.state?.facts);
  const here = useMemo(() => pinFacts(facts).filter((fact) => fact.anchor.space_id === spaceId), [facts, spaceId]);
  return <FactsLine facts={here} />;
}

function FactsLine({ facts }: { facts: Fact[] }) {
  const showPhoto = useFacts((s) => s.showPhoto);
  if (!facts.length) return null;
  const first = facts[0];
  return (
    <div className="walk-facts" role="note" data-testid="walk-facts">
      <span className={`fact-mark small ${first.kind === "issue" ? "fact-issue" : "fact-note"}`} aria-hidden>
        {first.kind === "issue" ? <IssueGlyph /> : <NoteGlyph />}
      </span>
      <span className="walk-facts-text">
        {first.text}
        <span className="card-muted"> · {first.author || "Technician"}</span>
        {facts.length > 1 && <span className="card-muted"> · +{facts.length - 1} more</span>}
      </span>
      {first.photo && (
        <button className="link" onClick={() => showPhoto({ url: first.photo!, caption: first.text })}>
          Photo
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- Wanda's replies

const PHOTO_WORDS = /\b(photo|picture|foto|bild|image)\b/i;
const PHOTO_URL = /\/api\/facts\/photo\?[^\s)"'<>]+/;

/** A reply that names facts highlights their pins (also with the layer off) and flies to the first, like `located`;
 * "show me the photo" opens the photo when the reply carries one. */
export function onReply(reply: ChatReply, message: string): void {
  const { model, state } = useTwin.getState();
  const known = new Map((state?.facts ?? []).map((fact) => [fact.id, fact]));
  const named: Fact[] = (reply.facts ?? []).flatMap((entry) => {
    const fact = typeof entry === "string" ? known.get(entry) : (known.get(entry.id) ?? entry);
    return fact ? [fact] : [];
  });
  const facts = useFacts.getState();
  facts.setHighlighted(named.map((fact) => fact.id));
  if (named.length && model) {
    const place = factPlace(model, named[0]);
    if (place) useTwin.getState().requestCamera({ kind: "point", point: place.point, floorId: place.floor_id, radius: 12 });
    if (place) useTwin.setState({ focusedFloorId: place.floor_id });
  }
  if (PHOTO_WORDS.test(message)) {
    const withPhoto = named.find((fact) => fact.photo);
    const url = withPhoto?.photo ?? reply.reply.match(PHOTO_URL)?.[0];
    if (url) facts.showPhoto({ url, caption: withPhoto?.text ?? "Photo" });
  }
}

let installed = false;
/** Wire the page's knowledge into the store once: replies highlight facts; a tapped room closes the pin card. */
export function installFacts(): void {
  if (installed) return;
  installed = true;
  replyHooks.push(onReply);
  useTwin.subscribe((state, previous) => {
    if (state.selection && state.selection !== previous.selection) useFacts.getState().openPin(null);
    if (state.buildingKey !== previous.buildingKey) useFacts.setState({ pin: null, highlighted: [], saved: null, photo: null });
  });
}
