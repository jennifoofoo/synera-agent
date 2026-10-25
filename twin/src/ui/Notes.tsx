// Place notes on screen (owner: notes session): the Notes button, the sheet ("What's here?" list and the add form),
// the note card during guidance and the photo viewer. State and rules live in notes/notesStore.ts.

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { downscalePhoto, whenLabel, type Note } from "../notes/notes";
import {
  AUTHORS,
  addNote,
  closeNotes,
  dismissGuide,
  finishJob,
  installNotes,
  notesIn,
  openNotes,
  removeNote,
  setAuthor,
  useNotes,
} from "../notes/notesStore";
import { useTwin } from "../store";
import { listenOnce, speechInputAvailable } from "../voice";
import { PhoneSheet } from "./PhoneSheet";
import { Report } from "./Report";
import "./Notes.css";

/** An object URL for a stored photo, revoked when the component goes away. */
export function usePhotoUrl(photo: Blob | null): string | null {
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

export function NoteThumb({ photo, size = 56 }: { photo: Blob | null; size?: number }) {
  const url = usePhotoUrl(photo);
  if (!url) return null;
  return (
    <button className="note-thumb" style={{ width: size, height: size }} onClick={() => showPhoto(url)} aria-label="Show photo">
      <img src={url} alt="" />
    </button>
  );
}

function NoteGlyph({ size = 18 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M5 4h14v11l-5 5H5z" />
      <path d="M14 20v-5h5M8.5 9h7M8.5 12.5h4" />
    </svg>
  );
}

function NoteRow({ note, onRemove }: { note: Note; onRemove?: () => void }) {
  const model = useTwin((s) => s.model);
  const asset = note.assetId ? model?.assetById.get(note.assetId)?.name : null;
  const [confirm, setConfirm] = useState(false);
  return (
    <li className="note-row">
      <NoteThumb photo={note.photo} />
      <div className="note-row-body">
        <div className="note-meta">
          <strong>{note.author}</strong> · {whenLabel(note.createdAt)}
          {asset && <span> · {asset}</span>}
        </div>
        {note.text && <p className="note-text">{note.text}</p>}
      </div>
      {onRemove && (
        // Two taps: a note is someone's knowledge, it should not go with a stray tap.
        <button className={`link note-remove ${confirm ? "armed" : ""}`} onClick={() => (confirm ? onRemove() : setConfirm(true))} onBlur={() => setConfirm(false)}>
          {confirm ? "Delete?" : "Delete"}
        </button>
      )}
    </li>
  );
}

// ---- the button ----

/** Bottom left: "Notes" (opens "What's here?" for the tapped room or "You are here"); installs the notes store. */
export function NotesButton() {
  const sheet = useNotes((s) => s.sheet);
  const notes = useNotes((s) => s.notes);
  const model = useTwin((s) => s.model);
  const draft = useTwin((s) => s.draft);
  const selection = useTwin((s) => s.selection);
  const position = useTwin((s) => s.state?.position ?? null);
  useEffect(installNotes, []);
  if (!model || draft || sheet !== "closed") return null;
  const spaceId = selection?.kind === "asset" ? model.assetById.get(selection.id)?.space_id : selection?.kind === "space" ? selection.id : (selection?.space_id ?? position?.space_id);
  const here = spaceId ? notes.filter((note) => note.spaceId === spaceId).length : 0;
  return (
    <button className="notes-fab" onClick={() => openNotes("here")} aria-label={here ? `Notes, ${here} here` : "Notes"}>
      <NoteGlyph />
      <span>Notes</span>
      {here > 0 && <span className="notes-count">{here}</span>}
    </button>
  );
}

// ---- the sheet ----

function AuthorSwitch() {
  const author = useNotes((s) => s.author);
  return (
    <div className="note-author" role="radiogroup" aria-label="Notes by">
      {AUTHORS.map((name) => (
        <button key={name} role="radio" aria-checked={author === name} className={author === name ? "on" : ""} onClick={() => setAuthor(name)}>
          {name}
        </button>
      ))}
    </div>
  );
}

function AddForm() {
  const place = useNotes((s) => s.place);
  const draft = useNotes((s) => s.draft);
  const storageLabel = useNotes((s) => s.storageLabel);
  const [text, setText] = useState(draft);
  const [photo, setPhoto] = useState<Blob | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const stopListening = useRef<(() => void) | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const photoUrl = usePhotoUrl(photo);
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
    const note = await addNote({ text, photo, place });
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
          placeholder="What should the next person know here?"
          rows={3}
          maxLength={600}
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
        <span className="note-storage">{storageLabel}</span>
      </div>
      {problem && <p className="note-problem">{problem}</p>}
      <div className="card-actions">
        <button onClick={() => openNotes("here")}>Cancel</button>
        <button className="primary" onClick={() => void save()} disabled={busy || (!text.trim() && !photo)}>
          Save note
        </button>
      </div>
    </div>
  );
}

function HereList() {
  const place = useNotes((s) => s.place);
  const all = useNotes((s) => s.notes);
  const job = useNotes((s) => s.job);
  const walking = useTwin((s) => s.walkStep !== null);
  void all; // re-render on changes
  const notes = place ? notesIn([place.spaceId]) : [];
  return (
    <>
      {!place ? (
        <p className="note-empty">Tap a room or machine on the map, or set “You are here”, to see and leave notes there.</p>
      ) : notes.length ? (
        <ul className="note-list">
          {notes.map((note) => (
            <NoteRow key={note.id} note={note} onRemove={() => void removeNote(note.id)} />
          ))}
        </ul>
      ) : (
        <p className="note-empty">No notes here yet. Leave one for the next shift.</p>
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

export function NotesSheet() {
  const sheet = useNotes((s) => s.sheet);
  const place = useNotes((s) => s.place);
  if (sheet === "closed") return null;
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
          <AuthorSwitch />
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

/** "Klaus left a note here · yesterday 14:12" with the text and photo, above the step sheet. */
export function GuideNote() {
  const guide = useNotes((s) => s.guide);
  if (!guide) return null;
  const [note, ...more] = guide.notes;
  return (
    <section className="card card-guide-note" role="status" aria-live="polite" aria-label="Note here">
      <NoteThumb photo={note.photo} size={64} />
      <div className="note-row-body">
        <div className="note-meta">
          <span className="note-badge small">
            <NoteGlyph size={13} />
          </span>
          <strong>{note.author} left a note here</strong> · <span className="nowrap">{whenLabel(note.createdAt)}</span>
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
