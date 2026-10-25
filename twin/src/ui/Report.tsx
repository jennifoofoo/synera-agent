// Job report (owner: notes session): shown when guidance ends or on "Finish job" / finishJob(). Facts only from
// what notes/notesStore.ts recorded: destination or round, times, metres from the route, closures, notes and photos.

import { useState } from "react";
import { clockLabel, durationLabel, type Note } from "../notes/notes";
import { closeReport, placeName, useNotes, type Job } from "../notes/notesStore";
import type { BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { NoteThumb } from "./Notes";
import { PhoneSheet } from "./PhoneSheet";

function notesWith(ids: string[], notes: Note[]): Note[] {
  const wanted = new Set(ids);
  return notes.filter((note) => wanted.has(note.id));
}

function walkedLine(job: Job): string | null {
  if (job.walkedM === null) return null;
  if (job.lengthM !== null && !job.arrived) return `${job.walkedM} m of ${job.lengthM} m`;
  return `${job.walkedM} m`;
}

/** The report as plain text (Copy, Share). */
export function reportText(job: Job, notes: Note[], seen: Note[], model: BuildingModel | null, building: string | null): string {
  const where = (note: Note) => (model ? placeName(model, note.spaceId, note.assetId) : note.spaceId);
  const lines = [`Job report${building ? ` · ${building}` : ""}`];
  if (job.title) lines.push(`${job.title.startsWith("Round") ? "Round" : "Destination"}: ${job.title}${job.arrived ? " (arrived)" : job.lengthM !== null ? " (ended early)" : ""}`);
  const end = job.endedAt ?? Date.now();
  lines.push(`Time: ${clockLabel(job.startedAt)} to ${clockLabel(end)} (${durationLabel(end - job.startedAt)})`);
  const walked = walkedLine(job);
  if (walked) lines.push(`Walked: ${walked}`);
  lines.push(`Closures: ${job.closures.length ? job.closures.join(", ") : "none on the way"}`);
  if (notes.length) {
    lines.push(`Notes (${notes.length}):`);
    for (const note of notes) lines.push(`- ${clockLabel(note.createdAt)} ${note.author} at ${where(note)}: ${note.text || "(photo)"}${note.photo && note.text ? " (photo)" : ""}`);
  } else lines.push("Notes: none");
  if (seen.length) {
    lines.push(`Notes read on the way (${seen.length}):`);
    for (const note of seen) lines.push(`- ${note.author} at ${where(note)}: ${note.text || "(photo)"}`);
  }
  return lines.join("\n");
}

export function Report() {
  const report = useNotes((s) => s.report);
  const all = useNotes((s) => s.notes);
  const model = useTwin((s) => s.model);
  const building = useTwin((s) => s.building?.name ?? null);
  const [done, setDone] = useState<string | null>(null);
  if (!report) return null;
  const notes = notesWith(report.noteIds, all);
  const seen = notesWith(report.seenIds, all);
  const text = reportText(report, notes, seen, model, building);
  const end = report.endedAt ?? Date.now();
  const walked = walkedLine(report);
  const canShare = typeof navigator !== "undefined" && typeof navigator.share === "function";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setDone("Copied");
    } catch {
      setDone("Copy is blocked here");
    }
  };
  const share = async () => {
    const files = notes
      .filter((note) => note.photo)
      .map((note, index) => new File([note.photo as Blob], `note-${index + 1}.jpg`, { type: "image/jpeg" }));
    const withFiles = files.length && navigator.canShare?.({ files }) ? { files } : {};
    try {
      await navigator.share({ title: "Job report", text, ...withFiles });
    } catch {
      /* cancelled */
    }
  };
  const close = () => {
    setDone(null);
    closeReport();
  };

  return (
    <PhoneSheet open label="Job report" onClose={close}>
      <section className="card card-report" aria-label="Job report">
        <div className="card-head">
          <div className="note-title">
            <span className="card-kicker">Job report</span>
            <strong>{report.title ?? "Notes"}</strong>
          </div>
          <button className="x" onClick={close} aria-label="Close report">
            ×
          </button>
        </div>
        <dl className="report-facts">
          <div>
            <dt>Time</dt>
            <dd>
              {clockLabel(report.startedAt)}–{clockLabel(end)}
            </dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>{durationLabel(end - report.startedAt)}</dd>
          </div>
          {walked && (
            <div>
              <dt>Walked</dt>
              <dd>{walked}</dd>
            </div>
          )}
          <div>
            <dt>Notes</dt>
            <dd>{notes.length}</dd>
          </div>
        </dl>
        {report.title && (
          <p className="card-line">
            {report.arrived ? "Arrived" : report.lengthM !== null ? "Ended before the destination" : ""}
            {report.closures.length ? `${report.arrived || report.lengthM !== null ? " · " : ""}Avoided closed ${report.closures.join(", ")}` : ""}
          </p>
        )}
        {notes.length > 0 && (
          <ul className="note-list report-notes">
            {notes.map((note) => (
              <li className="note-row" key={note.id}>
                <NoteThumb photo={note.photo} size={48} />
                <div className="note-row-body">
                  <div className="note-meta">
                    <strong>{model ? placeName(model, note.spaceId, note.assetId) : note.spaceId}</strong> · {clockLabel(note.createdAt)} · {note.author}
                  </div>
                  {note.text && <p className="note-text">{note.text}</p>}
                </div>
              </li>
            ))}
          </ul>
        )}
        {seen.length > 0 && (
          <p className="card-line report-seen">
            Read on the way: {seen.map((note) => `${note.author} at ${model ? placeName(model, note.spaceId, note.assetId) : note.spaceId}`).join(", ")}
          </p>
        )}
        <div className="card-actions">
          <button onClick={() => void copy()}>{done ?? "Copy as text"}</button>
          {canShare && (
            <button className="primary" onClick={() => void share()}>
              Share
            </button>
          )}
        </div>
      </section>
    </PhoneSheet>
  );
}
