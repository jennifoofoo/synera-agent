// Job report (owner: notes session): shown when guidance ends or on "Finish job" / finishJob(). Facts only from
// what notes/notesStore.ts recorded: destination or round, times, metres from the route, closures, notes and photos.

import { useState } from "react";
import { clockLabel, durationLabel, type Note } from "../notes/notes";
import { closeReport, placeName, useNotes, type Job } from "../notes/notesStore";
import type { BuildingModel } from "../model/model";
import { useTwin } from "../store";
import { NoteThumb } from "./Facts";
import { PhoneSheet } from "./PhoneSheet";

function notesWith(ids: string[], notes: Note[]): Note[] {
  const wanted = new Set(ids);
  return notes.filter((note) => wanted.has(note.id));
}

function walkedLine(job: Job): string | null {
  if (job.walkedM === null) return null;
  // A round: walked against its planned length (legs walked differently, e.g. a stop skipped, show here).
  if (job.lengthM !== null && (!job.arrived || job.round)) return `${job.walkedM} m of ${job.lengthM} m`;
  return `${job.walkedM} m`;
}

/** "4 of 5" and the names checked / not checked, for a round. */
export function stopsLine(job: Job): { count: string; checked: string[]; missed: string[] } | null {
  if (!job.round) return null;
  const { stops, checked } = job.round;
  const done = new Set(checked);
  return {
    count: `${stops.filter((stop) => done.has(stop.spaceId)).length} of ${stops.length}`,
    checked: stops.filter((stop) => done.has(stop.spaceId)).map((stop) => stop.name),
    missed: stops.filter((stop) => !done.has(stop.spaceId)).map((stop) => stop.name),
  };
}

/** The report as plain text (Copy, Share). */
export function reportText(job: Job, notes: Note[], seen: Note[], model: BuildingModel | null, building: string | null): string {
  const where = (note: Note) => (model ? placeName(model, note.anchor.space_id, note.anchor.asset_id) : note.anchor.space_id);
  const lines = [`Job report${building ? ` · ${building}` : ""}`];
  const stops = stopsLine(job);
  if (job.title && stops) lines.push(`${job.title}${job.arrived ? " (complete)" : " (ended early)"}`);
  else if (job.title) lines.push(`${job.title.startsWith("Round") ? "Round" : "Destination"}: ${job.title}${job.arrived ? " (arrived)" : job.lengthM !== null ? " (ended early)" : ""}`);
  const end = job.endedAt ?? Date.now();
  lines.push(`Time: ${clockLabel(job.startedAt)} to ${clockLabel(end)} (${durationLabel(end - job.startedAt)})`);
  const walked = walkedLine(job);
  if (walked) lines.push(`Walked: ${walked}`);
  if (stops) {
    lines.push(`Stops checked: ${stops.count}${stops.checked.length ? ` (${stops.checked.join(", ")})` : ""}`);
    if (stops.missed.length) lines.push(`Not checked: ${stops.missed.join(", ")}`);
  }
  lines.push(`Closures: ${job.closures.length ? job.closures.join(", ") : "none on the way"}`);
  if (notes.length) {
    lines.push(`Notes (${notes.length}):`);
    for (const note of notes) lines.push(`- ${clockLabel(note.created_at)} ${note.author} at ${where(note)}: ${note.text || "(photo)"}${note.photo && note.text ? " (photo)" : ""}`);
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
  const stops = stopsLine(report);
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
    const photos = notes.filter((note) => note.photo).map((note) => note.photo as string);
    const blobs = await Promise.all(photos.map((url) => fetch(url).then((r) => r.blob()).catch(() => null)));
    const files = blobs.flatMap((blob, index) => (blob ? [new File([blob], `note-${index + 1}.jpg`, { type: "image/jpeg" })] : []));
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
          {stops && (
            <div>
              <dt>Stops checked</dt>
              <dd>{stops.count}</dd>
            </div>
          )}
          <div>
            <dt>Notes</dt>
            <dd>{notes.length}</dd>
          </div>
        </dl>
        {stops && (
          <p className="card-line">
            {stops.checked.length ? `Checked: ${stops.checked.join(", ")}` : "No stop checked"}
            {stops.missed.length ? ` · Not checked: ${stops.missed.join(", ")}` : ""}
            {report.closures.length ? ` · Avoided closed ${report.closures.join(", ")}` : ""}
          </p>
        )}
        {report.title && !stops && (
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
                    <strong>{model ? placeName(model, note.anchor.space_id, note.anchor.asset_id) : note.anchor.space_id}</strong> · {clockLabel(note.created_at)} · {note.author}
                  </div>
                  {note.text && <p className="note-text">{note.text}</p>}
                </div>
              </li>
            ))}
          </ul>
        )}
        {seen.length > 0 && (
          <p className="card-line report-seen">
            Read {stops ? "during the round" : "on the way"}: {[...new Set(seen.map((note) => `${note.author} at ${model ? placeName(model, note.anchor.space_id, note.anchor.asset_id) : note.anchor.space_id}`))].join(", ")}
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
