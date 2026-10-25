// "Note here" in the room card (docs/specs/place-knowledge-page.md, items 4 and 5): one line of text, optionally a
// photo (phone: the camera), "Problem" for something broken. Sending counts as the confirmation (no chat card); the
// pin appears at once (the layer switches on) and "Undo" stays for 2 minutes (SavedChip in Facts.tsx).
// The author's name is asked once, with the first note, and remembered in the browser ("Technician" if left empty).

import { useRef, useState } from "react";
import { factsApi, photoAsBase64, type NewFact } from "../api/facts";
import type { Selection } from "../store";
import { useTwin } from "../store";
import { authorName, setAuthorName, useFacts } from "./factsStore";
import type { BuildingModel } from "../model/model";

/** The anchor of a note for what is selected: a thing, a door/lift/stairs, a spot in a room, or the room. */
export function anchorOf(model: BuildingModel, selection: Selection): NewFact["anchor"] | null {
  const floor_id = selection.floor_id;
  if (selection.kind === "asset") return { asset_id: selection.id, floor_id };
  if (selection.kind === "opening") return { element_id: selection.id, floor_id };
  if (selection.kind === "connector") return { element_id: selection.id, floor_id };
  const space_id = selection.kind === "space" ? selection.id : selection.space_id;
  if (!space_id || !model.spaceById.has(space_id)) return null;
  return { space_id, floor_id, ...(selection.point ? { point: selection.point } : {}) };
}

export function NoteHere({ model, selection }: { model: BuildingModel; selection: Selection }) {
  const key = useTwin((s) => s.buildingKey);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [issue, setIssue] = useState(false);
  const [photo, setPhoto] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const anchor = anchorOf(model, selection);
  const askName = authorName() === null;
  if (!anchor || !key) return null;

  if (!open) {
    return (
      <button className="link note-here-open" onClick={() => setOpen(true)} data-testid="note-here">
        Note here
      </button>
    );
  }

  const send = async () => {
    const clean = text.trim();
    if (!clean || busy) return;
    setBusy(true);
    setError("");
    try {
      const author = askName ? setAuthorName(name) : (authorName() ?? "Technician");
      const photo_base64 = photo ? await photoAsBase64(photo) : undefined;
      const result = await factsApi.create(key, { kind: issue ? "issue" : "note", anchor, text: clean, author, ...(photo_base64 ? { photo_base64 } : {}) });
      useTwin.getState().applyState(result.state);
      const facts = useFacts.getState();
      facts.setLayer(true); // the new pin shows right away
      facts.setSaved({ fact: result.fact, at: Date.now() });
      useTwin.getState().select(null);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <form
      className="note-here"
      data-testid="note-form"
      onSubmit={(event) => {
        event.preventDefault();
        void send();
      }}
    >
      <input
        className="note-text"
        type="text"
        value={text}
        maxLength={500}
        autoFocus
        placeholder={issue ? "What is wrong here?" : "What should the next person know?"}
        aria-label="Note"
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.stopPropagation();
            setOpen(false);
          }
        }}
        data-testid="note-text"
      />
      {askName && (
        <label className="note-name-label">
          <span>Your name for notes (asked once, others see who wrote it)</span>
          <input className="note-name" type="text" value={name} maxLength={60} placeholder="Technician" onChange={(event) => setName(event.target.value)} data-testid="note-name" />
        </label>
      )}
      <div className="note-row">
        <label className="note-issue">
          <input type="checkbox" role="switch" checked={issue} onChange={(event) => setIssue(event.target.checked)} data-testid="note-issue" />
          Problem
        </label>
        <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden onChange={(event) => setPhoto(event.target.files?.[0] ?? null)} data-testid="note-photo-input" />
        {photo ? (
          <button type="button" className="link" onClick={() => setPhoto(null)} title="Remove the photo">
            Photo added ×
          </button>
        ) : (
          <button type="button" className="link" onClick={() => fileRef.current?.click()} data-testid="note-photo">
            Add photo
          </button>
        )}
        <span className="note-spacer" />
        <button type="button" className="quiet" onClick={() => setOpen(false)}>
          Cancel
        </button>
        <button type="submit" className="primary note-send" disabled={busy || !text.trim()} data-testid="note-send">
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
      {error && <div className="card-note">{error}</div>}
    </form>
  );
}
