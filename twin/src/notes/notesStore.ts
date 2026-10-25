// Place notes and the job report (owner: notes session). Deterministic, no agent: notes are kept through
// notes.ts (NotesStorage), the job is the guidance in progress (store.walkStep and state.route), the report is built
// from what was recorded. Voice hooks for the integrator: addNoteHere(text), notesHere(), finishJob() (see the end).

import { create } from "zustand";
import type { Point, Route } from "../api/types";
import type { BuildingModel } from "../model/model";
import { closedOnRoute } from "../model/closures";
import { useTwin, walkSteps } from "../store";
import { isSpeaking, speak, speechPending } from "../voice";
import { metresLeft, readable } from "../walkInfo";
import { newNoteId, notesStorage, whenLabel, type Note } from "./notes";

export const AUTHORS = ["Klaus", "Tom"] as const;
const AUTHOR_PREF = "twin.noteAuthor";
/** A guidance shorter than this without notes ends quietly (no report for a route started by mistake). */
const MIN_JOB_MS = 10_000;

/** Where a note goes: a room, optionally an asset in it, optionally a point. */
export interface NotePlace {
  spaceId: string;
  floorId: string;
  assetId: string | null;
  point: Point | null;
  /** "Press 3 · Production zone H-A1" or "Office 0.25". */
  name: string;
}

export interface Job {
  startedAt: number;
  endedAt: number | null;
  /** "Office 0.25", "Round · 4 stops", or null for a job without guidance (notes only). */
  title: string | null;
  lengthM: number | null;
  walkedM: number | null;
  stepCount: number;
  /** Furthest step reached (index into the walk lines). */
  maxStep: number;
  arrived: boolean;
  closures: string[];
  noteIds: string[];
}

interface NotesState {
  buildingKey: string | null;
  notes: Note[];
  loaded: boolean;
  storageLabel: string;
  author: string;
  error: string | null;
  /** The notes sheet: closed, the list for a place ("What's here?"), or the add form. */
  sheet: "closed" | "here" | "add";
  /** The place the sheet is about (frozen when it opens, so a tap on the map does not move a half-written note). */
  place: NotePlace | null;
  /** Text to start the add form with (e.g. from a voice command). */
  draft: string;
  job: Job | null;
  report: Job | null;
  /** The note card during guidance: notes at the place the walker is at now. */
  guide: { stepKey: string; notes: Note[] } | null;
  /** Guide cards the walker closed (by step key), so Back/Next does not bring them back. */
  dismissed: string[];
}

function loadAuthor(): string {
  try {
    return localStorage.getItem(AUTHOR_PREF) || AUTHORS[0];
  } catch {
    return AUTHORS[0];
  }
}

export const useNotes = create<NotesState>(() => ({
  buildingKey: null,
  notes: [],
  loaded: false,
  storageLabel: notesStorage().label,
  author: loadAuthor(),
  error: null,
  sheet: "closed",
  place: null,
  draft: "",
  job: null,
  report: null,
  guide: null,
  dismissed: [],
}));

export function setAuthor(author: string): void {
  useNotes.setState({ author });
  try {
    localStorage.setItem(AUTHOR_PREF, author);
  } catch {
    /* private mode: this tab only */
  }
}

// ---- places ----

export function placeName(model: BuildingModel, spaceId: string, assetId: string | null = null): string {
  const space = model.spaceById.get(spaceId)?.name || "this room";
  const asset = assetId ? model.assetById.get(assetId)?.name : null;
  return asset ? `${asset} · ${space}` : space;
}

/** The place "here": the tapped room or asset (or tapped point in a room), else "You are here". */
export function currentPlace(): NotePlace | null {
  const { model, selection, state } = useTwin.getState();
  if (!model) return null;
  if (selection) {
    if (selection.kind === "asset") {
      const asset = model.assetById.get(selection.id);
      if (asset) return { spaceId: asset.space_id, floorId: asset.floor_id, assetId: asset.id, point: asset.position, name: placeName(model, asset.space_id, asset.id) };
    }
    const spaceId = selection.kind === "space" ? selection.id : selection.space_id;
    const space = spaceId ? model.spaceById.get(spaceId) : undefined;
    if (space) return { spaceId: space.id, floorId: space.floor_id, assetId: null, point: selection.point ?? space.anchor, name: placeName(model, space.id) };
  }
  const position = state?.position;
  const space = position ? model.spaceById.get(position.space_id) : undefined;
  if (position && space) return { spaceId: space.id, floorId: space.floor_id, assetId: null, point: position.point ?? space.anchor, name: placeName(model, space.id) };
  return null;
}

/** Notes in a room (including notes on its assets), newest first. */
export function notesIn(spaceIds: Iterable<string>): Note[] {
  const ids = new Set(spaceIds);
  return useNotes
    .getState()
    .notes.filter((note) => ids.has(note.spaceId))
    .sort((a, b) => b.createdAt - a.createdAt);
}

// ---- loading and saving ----

let loadRun = 0;
export async function loadNotes(buildingKey: string | null): Promise<void> {
  const run = ++loadRun;
  useNotes.setState({ buildingKey, notes: [], loaded: false, guide: null, storageLabel: notesStorage().label });
  if (!buildingKey) return;
  try {
    const notes = await notesStorage().list(buildingKey);
    if (run === loadRun) useNotes.setState({ notes, loaded: true, error: null });
  } catch {
    if (run === loadRun) useNotes.setState({ loaded: true, error: "Notes could not be loaded on this device." });
  }
}

export async function addNote(input: { text: string; photo?: Blob | null; place?: NotePlace | null }): Promise<Note | null> {
  const { buildingKey, author } = useNotes.getState();
  const place = input.place ?? currentPlace();
  const text = input.text.trim();
  if (!buildingKey || !place || (!text && !input.photo)) return null;
  const note: Note = {
    id: newNoteId(),
    buildingKey,
    spaceId: place.spaceId,
    floorId: place.floorId,
    assetId: place.assetId,
    point: place.point,
    text,
    author,
    createdAt: Date.now(),
    photo: input.photo ?? null,
  };
  try {
    await notesStorage().add(note);
  } catch {
    useNotes.setState({ error: "This device could not save the note (storage full?)." });
    return null;
  }
  const job = useNotes.getState().job ?? newJob(null);
  useNotes.setState((s) => ({ notes: [...s.notes, note], error: null, job: { ...job, noteIds: [...job.noteIds, note.id] } }));
  return note;
}

export async function removeNote(id: string): Promise<void> {
  const { buildingKey } = useNotes.getState();
  if (!buildingKey) return;
  await notesStorage().remove(buildingKey, id);
  useNotes.setState((s) => ({ notes: s.notes.filter((note) => note.id !== id) }));
}

// ---- the sheet ----

export function openNotes(view: "here" | "add" = "here", draft = ""): void {
  // Switching between the list and the form keeps the place the sheet opened for.
  const { sheet, place } = useNotes.getState();
  useNotes.setState({ sheet: view, place: sheet !== "closed" && place ? place : currentPlace(), draft, error: null, report: null });
  // The place is frozen above; the room card closes so the dock shows one sheet at a time.
  if (useTwin.getState().selection) useTwin.getState().select(null);
}

export function closeNotes(): void {
  useNotes.setState({ sheet: "closed", draft: "" });
}

// ---- the job ----

function newJob(route: Route | null): Job {
  const { model, state } = useTwin.getState();
  const stepCount = walkSteps().length;
  let title: string | null = null;
  if (route?.ok && model) {
    const stops = route.via?.length ?? 0;
    const destination = route.destination ? model.spaceById.get(route.destination)?.name || "the destination" : "the destination";
    title = stops ? `Round · ${stops + 1} stops` : destination;
  }
  return {
    startedAt: Date.now(),
    endedAt: null,
    title,
    lengthM: route?.ok && route.length_m !== undefined ? Math.round(route.length_m) : null,
    walkedM: null,
    stepCount,
    maxStep: 0,
    arrived: false,
    closures: route?.ok && model ? closedOnRoute(model, route, state?.closed ?? []) : [],
    noteIds: [],
  };
}

function startJob(): void {
  const route = useTwin.getState().state?.route ?? null;
  const previous = useNotes.getState().job;
  const job = newJob(route);
  // Notes taken just before starting (no guidance yet) belong to this job.
  if (previous && previous.title === null) Object.assign(job, { startedAt: previous.startedAt, noteIds: previous.noteIds });
  useNotes.setState({ job, dismissed: [], guide: null });
}

/** End the job and show its report. Returns the report, or null when there was nothing to report. */
function endJob(quietIfShort: boolean): Job | null {
  const job = useNotes.getState().job;
  if (!job) return null;
  const endedAt = Date.now();
  let walkedM = job.walkedM;
  if (job.lengthM !== null) {
    if (job.arrived) walkedM = job.lengthM;
    else if (walkedM === null) walkedM = 0;
  }
  const report = { ...job, endedAt, walkedM };
  const short = endedAt - job.startedAt < MIN_JOB_MS && !job.noteIds.length;
  useNotes.setState({ job: null, guide: null, report: quietIfShort && short ? null : report });
  return quietIfShort && short ? null : report;
}

export function closeReport(): void {
  useNotes.setState({ report: null });
}

/** Track the walk: furthest step, metres walked so far (from the step lines, scaled to the route length). */
function trackStep(step: number): void {
  const job = useNotes.getState().job;
  if (!job) return;
  const lines = walkSteps().map(readable);
  const maxStep = Math.max(job.maxStep, step);
  const left = job.lengthM !== null ? metresLeft(lines, maxStep, job.lengthM) : null;
  const walkedM = left !== null && job.lengthM !== null ? Math.max(0, job.lengthM - left) : job.walkedM;
  const arrived = job.arrived || (lines.length > 0 && maxStep >= lines.length - 1);
  useNotes.setState({ job: { ...job, maxStep, walkedM, arrived, stepCount: lines.length } });
}

// ---- notes during guidance ----

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Spaces of the route that a step line names ("… via Office corridor 0.16 into Office 0.25."). */
export function spacesNamed(line: string, route: Route, model: BuildingModel): string[] {
  const text = readable(line);
  const ids = new Set([...line.matchAll(/\[([^\]]+)\]/g)].map((m) => m[1]));
  const candidates = [...new Set([route.start, ...(route.space_path ?? []), ...(route.via ?? []), route.destination])].filter((id): id is string => !!id);
  const found = candidates.filter((id) => {
    if (ids.has(id)) return true;
    const name = model.spaceById.get(id)?.name;
    return !!name && new RegExp(`(^|[^\\w.])${escapeRegExp(name)}(?![\\w]|\\.\\d)`).test(text);
  });
  return found;
}

/** Spaces the walker is at during step `step`: where the step before led to, plus the destination on the last step. */
export function spacesAtStep(step: number): string[] {
  const { model, state } = useTwin.getState();
  const route = state?.route;
  if (!model || !route?.ok) return [];
  const lines = walkSteps();
  const out = new Set<string>();
  if (step === 0 && route.start) out.add(route.start);
  if (step > 0) for (const id of spacesNamed(lines[step - 1] ?? "", route, model)) out.add(id);
  if (step >= lines.length - 1) {
    for (const id of spacesNamed(lines[step] ?? "", route, model)) out.add(id);
    if (route.destination) out.add(route.destination);
  }
  return [...out];
}

let spokenFor = "";
function updateGuide(step: number | null): void {
  if (step === null) {
    useNotes.setState({ guide: null });
    return;
  }
  const spaces = spacesAtStep(step);
  const notes = notesIn(spaces);
  const stepKey = `${step}:${spaces.join(",")}`;
  if (!notes.length || useNotes.getState().dismissed.includes(stepKey)) {
    useNotes.setState({ guide: null });
    return;
  }
  useNotes.setState({ guide: { stepKey, notes } });
  if (spokenFor !== stepKey) {
    spokenFor = stepKey;
    void speakAfterStep(noteSpeech(notes));
  }
}

export function dismissGuide(): void {
  const guide = useNotes.getState().guide;
  if (guide) useNotes.setState((s) => ({ guide: null, dismissed: [...s.dismissed, guide.stepKey] }));
}

/** "Klaus left a note here, yesterday 14:12: always release the left lever first." */
export function noteSpeech(notes: Note[]): string {
  const [first] = notes;
  if (!first) return "";
  const text = first.text ? `: ${first.text}` : ", with a photo.";
  const more = notes.length > 1 ? ` And ${notes.length - 1} more note${notes.length > 2 ? "s" : ""} here.` : "";
  return `${first.author} left a note here, ${whenLabel(first.createdAt)}${text}${/[.!?]$/.test(text) ? "" : "."}${more}`;
}

/** Speak after the step line the Walk sheet is reading (speak() would cut it off), only with voice on. */
async function speakAfterStep(text: string): Promise<void> {
  const twin = useTwin.getState();
  if (!text || !(twin.voiceOut || twin.handsFree)) return;
  const deadline = Date.now() + 15_000;
  await new Promise((resolve) => setTimeout(resolve, 400));
  while ((isSpeaking() || speechPending()) && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 250));
  const now = useTwin.getState();
  if (now.walkStep === null && !useNotes.getState().guide) return;
  await speak(text, now.speechAvailable);
}

// ---- wiring to the twin store ----

let installed = false;
export function installNotes(): () => void {
  if (installed) return () => {};
  installed = true;
  void loadNotes(useTwin.getState().buildingKey);
  const unsubscribe = useTwin.subscribe((now, before) => {
    if (now.buildingKey !== before.buildingKey) {
      endJob(true);
      void loadNotes(now.buildingKey);
    }
    if (now.walkStep !== before.walkStep) {
      if (before.walkStep === null && now.walkStep !== null) startJob();
      if (now.walkStep !== null) trackStep(now.walkStep);
      if (before.walkStep !== null && now.walkStep === null) endJob(true);
      updateGuide(now.walkStep);
    }
  });
  const unsubscribeNotes = useNotes.subscribe((now, before) => {
    if (now.notes !== before.notes) updateGuide(useTwin.getState().walkStep);
  });
  return () => {
    installed = false;
    unsubscribe();
    unsubscribeNotes();
  };
}

// ---- hooks for voice (integrator) ----

/** "Hey Wanda, note: …" — save a note at the current place (tapped room/asset, else "You are here").
 * Returns the sentence to speak. */
export async function addNoteHere(text: string): Promise<string> {
  const place = currentPlace();
  if (!place) return "Tell me where you are first, then I can leave the note there.";
  const note = await addNote({ text, place });
  if (!note) return useNotes.getState().error ?? "I could not save that note.";
  return `Noted at ${place.name}.`;
}

/** "Hey Wanda, what's here?" — opens the list for the current place and returns the sentence to speak. */
export function notesHere(): string {
  const place = currentPlace();
  if (!place) return "Tell me where you are first.";
  openNotes("here");
  const notes = notesIn([place.spaceId]);
  if (!notes.length) return `No notes at ${place.name} yet.`;
  return notes.length === 1 ? noteSpeech(notes) : `${notes.length} notes here. ${noteSpeech(notes)}`;
}

/** "Hey Wanda, finished" — ends guidance (if any) and shows the job report. Returns the sentence to speak. */
export function finishJob(): string {
  const twin = useTwin.getState();
  if (twin.walkStep !== null) {
    trackStep(twin.walkStep);
    const report = endJob(false);
    twin.stopWalk(); // the subscription sees no job any more and stays quiet
    void twin.clearRoute();
    return report ? reportSpeech(report) : "Done.";
  }
  const report = endJob(false) ?? showEmptyReport();
  return reportSpeech(report);
}

function showEmptyReport(): Job {
  const report = { ...newJob(null), endedAt: Date.now() };
  useNotes.setState({ report });
  return report;
}

function reportSpeech(job: Job): string {
  const notes = job.noteIds.length;
  const parts = ["Job finished."];
  if (job.walkedM) parts.push(`${job.walkedM} metres walked.`);
  if (notes) parts.push(`${notes} note${notes === 1 ? "" : "s"} saved.`);
  return parts.join(" ");
}

if (typeof window !== "undefined") {
  (window as unknown as { __twinNotes: unknown }).__twinNotes = { useNotes, addNoteHere, notesHere, finishJob, openNotes, spacesAtStep };
}
