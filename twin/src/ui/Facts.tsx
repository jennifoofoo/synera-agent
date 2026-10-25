// Place knowledge on screen (owner: notes session; spec docs/specs/place-knowledge.md "Seite"): the Notes button and
// the map layer switch "Notes & photos", the sheet ("What's here?" with history, and the add form), the note card
// during guidance and the photo viewer. State and rules live in notes/notesStore.ts, storage in notes/notes.ts.

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { downscalePhoto, endedLabel, eventLabel, sinceLabel, type Note } from "../notes/notes";
import {
  DEFAULT_AUTHOR,
  addNote,
  authorRemembered,
  canResolve,
  canUndo,
  closeNotes,
  dismissGuide,
  finishJob,
  historyIn,
  installNotes,
  noteHeadline,
  notesIn,
  openNotes,
  resolveNote,
  setAuthor,
  setLayer,
  undoNote,
  useNotes,
} from "../notes/notesStore";
import { useTwin } from "../store";
import { listenOnce, speechInputAvailable } from "../voice";
import { PhoneSheet } from "./PhoneSheet";
import { Report } from "./Report";
import "./Facts.css";

/** An object URL for a local photo blob (the add form's preview), revoked when the component goes away. */
export function useBlobUrl(photo: Blob | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!photo) return setUrl(null);
    const next = URL.createObjectURL(photo);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [photo]);
  return url;
}

// ---- photo viewer ----

let showPhoto: (url: string | null) => void = () => {};

/** Open a fact's photo full screen (also for voice: "show me the photo"). */
export function openPhoto(url: string): void {
  showPhoto(url);
}

function PhotoViewer() {
  const [url, setUrl] = useState<string | null>(null);
  showPhoto = setUrl;
  useEffect(() => {
    if (!url) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setUrl(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [url]);
  if (!url) return null;
  // On the body: the dock is transformed, so a fixed overlay inside it would only cover the dock.
  return createPortal(
    <div className="note-viewer" role="dialog" aria-label="Photo" onClick={() => setUrl(null)}>
      <img src={url} alt="Note photo" />
      <button className="note-viewer-close" aria-label="Close photo">
        ×
      </button>
    </div>,
    document.body,
  );
}

export function NoteThumb({ photo, size = 56 }: { photo: string | null; size?: number }) {
  if (!photo) return null;
  return (
    <button className="note-thumb" style={{ width: size, height: size }} onClick={() => openPhoto(photo)} aria-label="Show photo">
      <img src={photo} alt="" />
    </button>
  );
}

export function NoteGlyph({ size = 18, issue = false }: { size?: number; issue?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {issue ? (
        <>
          <path d="M12 4 21 20H3z" />
          <path d="M12 10v4.5M12 17.5v.01" />
        </>
      ) : (
        <>
          <path d="M5 4h14v11l-5 5H5z" />
          <path d="M14 20v-5h5M8.5 9h7M8.5 12.5h4" />
        </>
      )}
    </svg>
  );
}

function NoteRow({ note, past = false }: { note: Note; past?: boolean }) {
  const model = useTwin((s) => s.model);
  const asset = note.anchor.asset_id ? model?.assetById.get(note.anchor.asset_id)?.name : null;
  const undo = !past && canUndo(note);
  const event = note.kind === "event";
  const resolve = !past && !undo && !event && canResolve(note);
  return (
    <li className={`note-row ${past ? "past" : ""}`}>
      <NoteThumb photo={note.photo} />
      <div className="note-row-body">
        <div className="note-meta">
          {note.kind === "issue" && <span className="note-kind">Problem</span>}
          {event && <span className="note-kind event">Event</span>}
          {event ? (
            eventLabel(note)
          ) : (
            <>
              <strong>{note.author || "Someone"}</strong> · {sinceLabel(note, false)}
            </>
          )}
          {event && note.author ? ` · by ${note.author}` : ""}
          {past && !event ? ` · ${endedLabel(note)}` : ""}
          {asset && <span> · {asset}</span>}
        </div>
        {note.text && <p className="note-text">{note.text}</p>}
      </div>
      {undo && (
        // Undo only right after creating (typos): a note is someone's knowledge, later it is resolved, not deleted.
        <button className="link note-action" onClick={() => void undoNote(note.id)}>
          Undo
        </button>
      )}
      {resolve && (
        <button className="link note-action" onClick={() => void resolveNote(note.id)} title={note.kind === "issue" ? "Mark as fixed" : "No longer true"}>
          {note.kind === "issue" ? "Fixed" : "Done"}
        </button>
      )}
    </li>
  );
}

// ---- the button and the layer switch ----

/** Bottom left: "Notes" (opens "What's here?" for the tapped room, the guidance step's room or "You are here") and
 * the map layer "Notes & photos" (spec: off by default). Installs the notes store. */
export function NotesButton() {
  const sheet = useNotes((s) => s.sheet);
  const notes = useNotes((s) => s.notes);
  const layer = useNotes((s) => s.layer);
  const model = useTwin((s) => s.model);
  const draft = useTwin((s) => s.draft);
  const selection = useTwin((s) => s.selection);
  const position = useTwin((s) => s.state?.position ?? null);
  // While walking the map stays free: notes surface on their own at the destination or a round stop.
  const walking = useTwin((s) => s.walkStep !== null);
  useEffect(installNotes, []);
  if (!model || draft || walking || sheet !== "closed") return null;
  void notes; // re-render on changes
  const spaceId = selection?.kind === "asset" ? model.assetById.get(selection.id)?.space_id : selection?.kind === "space" ? selection.id : (selection?.space_id ?? position?.space_id);
  const here = spaceId ? notesIn([spaceId]).length : 0;
  return (
    <div className="notes-fab-row">
      <button className="notes-fab" onClick={() => openNotes("here")} aria-label={here ? `Notes, ${here} here` : "Notes"}>
        <NoteGlyph />
        <span>Notes</span>
        {here > 0 && <span className="notes-count">{here}</span>}
      </button>
      <button
        className={`notes-layer ${layer ? "on" : ""}`}
        onClick={() => setLayer(!layer)}
        aria-pressed={layer}
        aria-label="Notes and photos on the map"
        title={layer ? "Hide notes & photos on the map" : "Show notes & photos on the map"}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden>
          <path d="M12 3 21 8l-9 5-9-5z" />
          <path d="m3 12.5 9 5 9-5M3 16.5l9 5 9-5" />
        </svg>
        <span>On map</span>
      </button>
    </div>
  );
}

// ---- the sheet ----

function AddForm() {
  const place = useNotes((s) => s.place);
  const draft = useNotes((s) => s.draft);
  const storageLabel = useNotes((s) => s.storageLabel);
  const author = useNotes((s) => s.author);
  // The name is asked once, with the first note saved by tap; after that it is remembered on this device.
  const [askName] = useState(() => !authorRemembered());
  const [name, setName] = useState(author);
  const [text, setText] = useState(draft);
  const [issue, setIssue] = useState(false);
  const [photo, setPhoto] = useState<Blob | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const stopListening = useRef<(() => void) | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const photoUrl = useBlobUrl(photo);
  useEffect(() => () => stopListening.current?.(), []);

  const pick = async (input: File | undefined) => {
    if (!input) return;
    setBusy(true);
    setProblem(null);
    try {
      setPhoto(await downscalePhoto(input));
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "That photo could not be read.");
    } finally {
      setBusy(false);
    }
  };
  const dictate = () => {
    if (listening) {
      stopListening.current?.();
      return;
    }
    setListening(true);
    stopListening.current = listenOnce(
      "en-US",
      (heard) => setText((now) => (now ? `${now} ${heard}` : heard)),
      () => {
        setListening(false);
        stopListening.current = null;
      },
    );
  };
  const save = async () => {
    setBusy(true);
    if (askName) setAuthor(name);
    const note = await addNote({ text, photo, place, kind: issue ? "issue" : "note", source: "tap" });
    setBusy(false);
    if (note) openNotes("here");
    else setProblem(useNotes.getState().error ?? "Write something or add a photo.");
  };

  return (
    <div className="note-form">
      <div className="note-field">
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={issue ? "What is wrong here?" : "What should the next person know here?"}
          rows={3}
          maxLength={500}
          aria-label="Note"
          autoFocus={!draft}
        />
        {speechInputAvailable() && (
          <button className={`note-mic ${listening ? "on" : ""}`} onClick={dictate} aria-label={listening ? "Stop dictation" : "Dictate"} title="Dictate">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
              <rect x="9" y="3" width="6" height="11" rx="3" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            </svg>
          </button>
        )}
      </div>
      <div className="note-photo-row">
        {photoUrl ? (
          <span className="note-photo-preview">
            <img src={photoUrl} alt="Photo for the note" />
            <button className="x" onClick={() => setPhoto(null)} aria-label="Remove photo">
              ×
            </button>
          </span>
        ) : (
          <button className="note-photo-add" onClick={() => file.current?.click()} disabled={busy}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden>
              <path d="M4 8h3l2-3h6l2 3h3v11H4z" />
              <circle cx="12" cy="13" r="3.5" />
            </svg>
            Add photo
          </button>
        )}
        <input ref={file} type="file" accept="image/*" capture="environment" hidden onChange={(event) => void pick(event.target.files?.[0])} />
        <label className="note-issue">
          <input type="checkbox" checked={issue} onChange={() => setIssue(!issue)} />
          It's a problem
        </label>
      </div>
      {askName && (
        <label className="note-name">
          <span>Your name, optional (remembered here)</span>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder={DEFAULT_AUTHOR} aria-label="Your name" autoComplete="name" maxLength={40} />
        </label>
      )}
      {problem && <p className="note-problem">{problem}</p>}
      <div className="card-actions">
        <button onClick={() => openNotes("here")}>Cancel</button>
        <button className="primary" onClick={() => void save()} disabled={busy || (!text.trim() && !photo)}>
          Save note
        </button>
      </div>
      <p className="note-storage">{storageLabel}</p>
    </div>
  );
}

function HereList() {
  const place = useNotes((s) => s.place);
  const all = useNotes((s) => s.notes);
  const job = useNotes((s) => s.job);
  const walking = useTwin((s) => s.walkStep !== null);
  const [history, setHistory] = useState(false);
  void all; // re-render on changes
  const notes = place ? notesIn([place.spaceId]) : [];
  const past = place ? historyIn([place.spaceId]) : [];
  return (
    <>
      {!place ? (
        <p className="note-empty">Tap a room or machine on the map, or set “You are here”, to see and leave notes there.</p>
      ) : notes.length ? (
        <ul className="note-list">
          {notes.map((note) => (
            <NoteRow key={note.id} note={note} />
          ))}
        </ul>
      ) : null}
      {past.length > 0 && (
        <>
          <button className="link note-history-toggle" onClick={() => setHistory(!history)} aria-expanded={history}>
            {history ? "Hide history" : `History (${past.length})`}
          </button>
          {history && (
            <ul className="note-list note-history">
              {past.map((note) => (
                <NoteRow key={note.id} note={note} past />
              ))}
            </ul>
          )}
        </>
      )}
      <div className="card-actions">
        {job && !walking && job.noteIds.length > 0 && <button onClick={() => (closeNotes(), finishJob())}>Finish job</button>}
        <button className="primary" disabled={!place} onClick={() => openNotes("add")}>
          Add note
        </button>
      </div>
    </>
  );
}

/** A place without notes: one quiet line, since notes are mostly said by voice. "+ Note" opens the add form. */
function EmptyRow() {
  const job = useNotes((s) => s.job);
  const walking = useTwin((s) => s.walkStep !== null);
  return (
    <section className="card card-notes-empty" aria-label="What's here">
      <div className="note-empty-row">
        <span className="note-badge small">
          <NoteGlyph size={13} />
        </span>
        <span className="note-empty-text">
          No notes here <span aria-hidden>·</span> Say “Wanda, note: …”
        </span>
        {job && !walking && job.noteIds.length > 0 && (
          <button className="link note-empty-finish" onClick={() => (closeNotes(), finishJob())}>
            Finish job
          </button>
        )}
        <button className="note-empty-add" onClick={() => openNotes("add")}>
          + Note
        </button>
        <button className="x" onClick={closeNotes} aria-label="Close notes">
          ×
        </button>
      </div>
    </section>
  );
}

export function NotesSheet() {
  const sheet = useNotes((s) => s.sheet);
  const place = useNotes((s) => s.place);
  const all = useNotes((s) => s.notes);
  void all; // re-render on changes
  if (sheet === "closed") return null;
  const empty = sheet === "here" && !!place && notesIn([place.spaceId]).length === 0 && historyIn([place.spaceId]).length === 0;
  if (empty)
    return (
      <PhoneSheet open label="Notes" onClose={closeNotes}>
        <EmptyRow />
      </PhoneSheet>
    );
  return (
    <PhoneSheet open label="Notes" onClose={closeNotes}>
      <section className="card card-notes" aria-label={sheet === "add" ? "New note" : "What's here"}>
        <div className="card-head">
          <div className="card-title">
            <span className="note-badge">
              <NoteGlyph size={16} />
            </span>
            <div className="note-title">
              <span className="card-kicker">{sheet === "add" ? "New note" : "What's here?"}</span>
              <strong>{place?.name ?? "No place yet"}</strong>
            </div>
          </div>
          <button className="x" onClick={closeNotes} aria-label="Close notes">
            ×
          </button>
        </div>
        {sheet === "add" ? <AddForm key={place?.spaceId} /> : <HereList />}
      </section>
    </PhoneSheet>
  );
}

// ---- during guidance ----

/** "Klaus left a note here · since yesterday 14:12" with the text and photo, above the step sheet. */
export function GuideNote() {
  const guide = useNotes((s) => s.guide);
  if (!guide) return null;
  const [note, ...more] = guide.notes;
  return (
    <section className={`card card-guide-note ${note.kind === "issue" ? "issue" : ""}`} role="status" aria-live="polite" aria-label="Note here">
      <NoteThumb photo={note.photo} size={64} />
      <div className="note-row-body">
        <div className="note-meta">
          <span className="note-badge small">
            <NoteGlyph size={13} issue={note.kind === "issue"} />
          </span>
          <strong>{noteHeadline(note)}</strong> · <span className="nowrap">{sinceLabel(note, false)}</span>
        </div>
        {note.text && <p className="note-text">{note.text}</p>}
        {more.length > 0 && (
          <button className="link note-more" onClick={() => openNotes("here")}>
            {more.length} more note{more.length > 1 ? "s" : ""} here
          </button>
        )}
      </div>
      <button className="x" onClick={dismissGuide} aria-label="Close note">
        ×
      </button>
    </section>
  );
}

/** Everything notes puts into the dock: the guidance note, the report and the sheet. */
export function NotesDock() {
  return (
    <>
      <GuideNote />
      <Report />
      <NotesSheet />
      <PhotoViewer />
    </>
  );
}
