// Place knowledge and the job report (owner: notes session). Deterministic, no agent: facts (notes, issues) are kept
// through notes.ts (FactsStorage: the server's /api/facts when it answers, else IndexedDB), the job is the guidance in
// progress (store.walkStep and state.route), the report is built from what was recorded. Voice hooks for the
// integrator: notesCommand(text), or addNoteHere(text), notesHere(), finishJob() (see the end).

import { create } from "zustand";
import type { BuildingState, Point, Route } from "../api/types";
import type { BuildingModel } from "../model/model";
import { closedOnRoute } from "../model/closures";
import { useTwin, walkSteps } from "../store";
import { isSpeaking, speak, speechPending } from "../voice";
import { metresLeft, readable } from "../walkInfo";
import { normalizeSpeech } from "../wake";
import { useRound } from "../round/round";
import { isCurrent, newestFirst, pickFactsStorage, whenLabel, type FactKind, type FactsStorage, type Note } from "./notes";

export const AUTHORS = ["Klaus", "Tom"] as const;
const AUTHOR_PREF = "twin.noteAuthor";
/** A guidance shorter than this without notes ends quietly (no report for a route started by mistake). */
const MIN_JOB_MS = 10_000;

/** Where a note goes: a room, optionally an asset in it, optionally a point. */
export interface NotePlace {
  spaceId: string;
  floorId: string;
  assetId: string | null;
  /** A door, lift or stairs the note is about (anchor.element_id). */
  elementId: string | null;
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
  /** Notes saved during the job. */
  noteIds: string[];
  /** Notes shown on the way (left by others before). */
  seenIds: string[];
}

interface NotesState {
  buildingKey: string | null;
  /** Every fact of the building, current and past (history); notesIn() gives the current ones. */
  notes: Note[];
  loaded: boolean;
  storage: FactsStorage | null;
  storageLabel: string;
  /** Map layer "Notes & photos" (spec: off by default). During guidance the route's notes show anyway. */
  layer: boolean;
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

const LAYER_PREF = "twin.notesLayer";

function loadLayer(): boolean {
  try {
    return localStorage.getItem(LAYER_PREF) === "1";
  } catch {
    return false;
  }
}

export function setLayer(layer: boolean): void {
  useNotes.setState({ layer });
  try {
    localStorage.setItem(LAYER_PREF, layer ? "1" : "0");
  } catch {
    /* private mode: this tab only */
  }
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
  storage: null,
  storageLabel: "",
  layer: loadLayer(),
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

/** The place "here": the tapped room or asset (or tapped point in a room), else the place of the current guidance
 * step, else "You are here". */
export function currentPlace(): NotePlace | null {
  const { model, selection, state } = useTwin.getState();
  if (!model) return null;
  if (selection) {
    if (selection.kind === "asset") {
      const asset = model.assetById.get(selection.id);
      if (asset) return { spaceId: asset.space_id, floorId: asset.floor_id, assetId: asset.id, elementId: null, point: asset.position, name: placeName(model, asset.space_id, asset.id) };
    }
    const element = selection.kind === "opening" || selection.kind === "connector" ? selection.id : null;
    const opening = selection.kind === "opening" ? model.openingById.get(selection.id) : undefined;
    const connector = selection.kind === "connector" ? model.connectorById.get(selection.id) : undefined;
    const spaceId = selection.kind === "space" ? selection.id : (selection.space_id ?? opening?.space_ids[0] ?? connector?.space_ids.find((id) => model.spaceById.get(id)?.floor_id === selection.floor_id));
    const space = spaceId ? model.spaceById.get(spaceId) : undefined;
    if (space) {
      const name = connector?.name ? `${connector.name} · ${space.name}` : placeName(model, space.id);
      return { spaceId: space.id, floorId: space.floor_id, assetId: null, elementId: element, point: selection.point ?? opening?.position ?? space.anchor, name };
    }
  }
  // Guiding: the place the walker reached with the current step ("You are here" still shows the start).
  const walkStep = useTwin.getState().walkStep;
  const atStep = walkStep !== null ? spacesAtStep(walkStep).at(-1) : undefined;
  const reached = atStep ? model.spaceById.get(atStep) : undefined;
  if (reached) return { spaceId: reached.id, floorId: reached.floor_id, assetId: null, elementId: null, point: reached.anchor, name: placeName(model, reached.id) };
  const position = state?.position;
  const space = position ? model.spaceById.get(position.space_id) : undefined;
  if (position && space) return { spaceId: space.id, floorId: space.floor_id, assetId: null, elementId: null, point: position.point ?? space.anchor, name: placeName(model, space.id) };
  return null;
}

/** Only what matters to the walker, no noise: in an inspection round, notes on the round's own devices (shown at that
 * stop); on a normal route, notes at the destination. Everything else on the way stays quiet. */
export function relevantNotes(notes: Note[]): Note[] {
  const { plan, guiding, index } = useRound.getState();
  if (plan && guiding) {
    const stop = plan.stops[index];
    const assets = new Set(stop ? stop.assetIds : []);
    return notes.filter((note) => !!note.anchor.asset_id && assets.has(note.anchor.asset_id));
  }
  const destination = useTwin.getState().state?.route?.destination;
  return notes.filter((note) => note.anchor.space_id === destination);
}

/** Notes and issues valid now in a room (including those on its machines and doors), newest first. Closures show on
 * the map's closure marks, not as notes. */
export function notesIn(spaceIds: Iterable<string>): Note[] {
  const ids = new Set(spaceIds);
  const now = Date.now();
  return useNotes
    .getState()
    .notes.filter((note) => note.kind !== "closure" && ids.has(note.anchor.space_id) && isCurrent(note, now))
    .sort(newestFirst);
}

/** Resolved and expired notes in a room (the history), newest first. */
export function historyIn(spaceIds: Iterable<string>): Note[] {
  const ids = new Set(spaceIds);
  const now = Date.now();
  return useNotes
    .getState()
    .notes.filter((note) => note.kind !== "closure" && ids.has(note.anchor.space_id) && !isCurrent(note, now) && Date.parse(note.valid_from) <= now)
    .sort(newestFirst);
}

// ---- loading and saving ----

let loadRun = 0;
export async function loadNotes(buildingKey: string | null): Promise<void> {
  const run = ++loadRun;
  useNotes.setState({ buildingKey, notes: [], loaded: false, guide: null });
  if (!buildingKey) return;
  const storage = await pickFactsStorage(buildingKey);
  if (run !== loadRun) return;
  useNotes.setState({ storage, storageLabel: storage.label });
  try {
    const notes = await storage.list(buildingKey);
    if (run === loadRun) useNotes.setState({ notes: mergeStateFacts(notes), loaded: true, error: null });
  } catch {
    if (run === loadRun) useNotes.setState({ loaded: true, error: "Notes could not be loaded." });
  }
}

/** state.facts (the server's current facts in every reply) wins over what was listed before. */
function mergeStateFacts(notes: Note[]): Note[] {
  const live = (useTwin.getState().state as { facts?: Note[] } | null)?.facts;
  if (!Array.isArray(live) || !live.length) return notes;
  const byId = new Map(notes.map((note) => [note.id, note]));
  for (const fact of live) byId.set(fact.id, fact);
  return [...byId.values()].sort(newestFirst);
}

export async function addNote(input: { text: string; photo?: Blob | null; place?: NotePlace | null; kind?: FactKind; source?: "text" | "voice" | "tap" }): Promise<Note | null> {
  const { buildingKey, author, storage } = useNotes.getState();
  const place = input.place ?? currentPlace();
  const text = input.text.trim();
  if (!buildingKey || !storage || !place || (!text && !input.photo)) return null;
  let note: Note;
  let state: unknown;
  try {
    ({ fact: note, state } = await storage.add(buildingKey, {
      kind: input.kind === "issue" ? "issue" : "note",
      anchor: { space_id: place.spaceId, asset_id: place.assetId, element_id: place.elementId, point: place.point, floor_id: place.floorId },
      text,
      author,
      photo: input.photo ?? null,
      source: input.source ?? "tap",
    }));
  } catch {
    useNotes.setState({ error: storage.kind === "server" ? "The server could not save the note." : "This device could not save the note (storage full?)." });
    return null;
  }
  applyServerState(state);
  const job = useNotes.getState().job ?? newJob(null);
  // A new note shows on the map at once, even with the layer off until now.
  useNotes.setState((s) => ({ notes: [note, ...s.notes.filter((n) => n.id !== note.id)], error: null, job: { ...job, noteIds: [...job.noteIds, note.id] } }));
  if (!useNotes.getState().layer) setLayer(true);
  return note;
}

/** The server's state after a save or undo (`{fact, state}`), so the map, state.facts and closures stay in step. */
function applyServerState(state: unknown): void {
  const twin = useTwin.getState();
  if (state && typeof state === "object" && "closed" in state && twin.state) twin.applyState(state as unknown as BuildingState);
}

/** Undo is only for a note just made (typos); later a note is resolved, never deleted (spec). */
export const UNDO_MS = 2 * 60_000;

export function canUndo(note: Note): boolean {
  const { storage, notes } = useNotes.getState();
  if (!storage?.undo || Date.now() - Date.parse(note.created_at) >= UNDO_MS) return false;
  // The server undoes only the building's newest fact.
  return storage.kind !== "server" || [...notes].sort(newestFirst)[0]?.id === note.id;
}

export function canResolve(note: Note): boolean {
  return !!useNotes.getState().storage?.resolve && isCurrent(note);
}

export async function undoNote(id: string): Promise<void> {
  const { buildingKey, storage } = useNotes.getState();
  if (!buildingKey || !storage?.undo) return;
  try {
    const reply = await storage.undo(buildingKey, id);
    if (reply) applyServerState(reply.state);
  } catch (error) {
    useNotes.setState({ error: error instanceof Error && storage.kind === "server" ? `${error.message}` : "Could not undo that note." });
    return;
  }
  useNotes.setState((s) => ({ notes: s.notes.filter((note) => note.id !== id), job: s.job ? { ...s.job, noteIds: s.job.noteIds.filter((n) => n !== id) } : s.job }));
}

export async function resolveNote(id: string): Promise<void> {
  const { buildingKey, storage, author } = useNotes.getState();
  if (!buildingKey || !storage?.resolve) return;
  const next = await storage.resolve(buildingKey, id, author);
  useNotes.setState((s) => ({ notes: s.notes.map((note) => (note.id === id ? next : note)) }));
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
    seenIds: [],
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
  const own = new Set(useNotes.getState().job?.noteIds ?? []);
  const notes = relevantNotes(notesIn(spaces)).filter((note) => !own.has(note.id)); // not the walker's own notes from this job
  const stepKey = `${step}:${spaces.join(",")}`;
  if (!notes.length || useNotes.getState().dismissed.includes(stepKey)) {
    useNotes.setState({ guide: null });
    return;
  }
  const job = useNotes.getState().job;
  const seen = job ? notes.map((note) => note.id).filter((id) => !job.seenIds.includes(id) && !job.noteIds.includes(id)) : [];
  useNotes.setState({ guide: { stepKey, notes }, ...(job && seen.length ? { job: { ...job, seenIds: [...job.seenIds, ...seen] } } : {}) });
  if (spokenFor !== stepKey) {
    spokenFor = stepKey;
    void speakAfterStep(noteSpeech(notes));
  }
}

export function dismissGuide(): void {
  const guide = useNotes.getState().guide;
  if (guide) useNotes.setState((s) => ({ guide: null, dismissed: [...s.dismissed, guide.stepKey] }));
}

/** Who and what, for the card title: "Klaus left a note here" / "Klaus reported a problem here". */
export function noteHeadline(note: Note): string {
  const who = note.author || "Someone";
  return note.kind === "issue" ? `${who} reported a problem here` : `${who} left a note here`;
}

/** "Klaus left a note here, yesterday 14:12: always release the left lever first." (age and author, spec) */
export function noteSpeech(notes: Note[]): string {
  const [first] = notes;
  if (!first) return "";
  const text = first.text ? `: ${first.text}` : ", with a photo.";
  const more = notes.length > 1 ? ` And ${notes.length - 1} more note${notes.length > 2 ? "s" : ""} here.` : "";
  return `${noteHeadline(first)}, ${whenLabel(first.valid_from)}${text}${/[.!?]$/.test(text) ? "" : "."}${more}`;
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
  // The server sends the facts valid now with every state (state.facts): take them, and re-read the history when
  // they change (a fact resolved through the chat leaves state.facts).
  const unsubscribeFacts = useTwin.subscribe((now, before) => {
    const live = (now.state as { facts?: Note[] } | null)?.facts;
    if (live === (before.state as { facts?: Note[] } | null)?.facts || !Array.isArray(live)) return;
    useNotes.setState((s) => ({ notes: mergeStateFacts(s.notes) }));
    const { storage, buildingKey } = useNotes.getState();
    if (storage?.kind === "server" && buildingKey) void storage.list(buildingKey).then((notes) => useNotes.setState({ notes: mergeStateFacts(notes) }), () => {});
  });
  const unsubscribeNotes = useNotes.subscribe((now, before) => {
    if (now.notes !== before.notes) updateGuide(useTwin.getState().walkStep);
  });
  return () => {
    installed = false;
    unsubscribe();
    unsubscribeFacts();
    unsubscribeNotes();
  };
}

// ---- hooks for voice (integrator) ----

/** "Hey Wanda, note: …" — save a note at the current place (tapped room/asset, else "You are here").
 * Returns the sentence to speak. */
export async function addNoteHere(text: string, kind: "note" | "issue" = "note"): Promise<string> {
  const place = currentPlace();
  if (!place) return "Tell me where you are first, then I can leave the note there.";
  const note = await addNote({ text, place, kind, source: "voice" });
  if (!note) return useNotes.getState().error ?? "I could not save that note.";
  return kind === "issue" ? `Problem noted at ${place.name}.` : `Noted at ${place.name}.`;
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
  closeNotes();
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

const ISSUE_SAID = /^\s*(?:problem|issue|report a problem|störung|stoerung|defekt)\b\s*(?:here|hier)?\s*[:,.-]?\s*(.+)$/i;
const NOTE_SAID = /^\s*(?:note|take a note|make a note|merk dir|merke dir|merk|notiz|notiere)\b\s*(?:that|this|here|hier|dass|das)?\s*[:,.-]?\s*(.+)$/i;
const HERE_SAID = /^(?:what'?s here|what is here|any notes(?: here)?|notes here|was gibt'?s hier|was gibt es hier|gibt es hier notizen)$/;
const FINISH_SAID = /^(?:finished|i'?m finished|i am finished|job done|finish(?: the)? job|end(?: the)? job|fertig|ich bin fertig|feierabend|auftrag fertig)$/;

/** One call for the hands-free handler: a notes command ("note: …", "what's here", "finished") runs here and
 * returns the sentence to speak; anything else returns null. While walking, "finished"/"fertig" before the last step
 * is left to the walking commands ("fertig" = next station). */
export function notesCommand(text: string): Promise<string> | null {
  const issue = ISSUE_SAID.exec(text);
  if (issue && issue[1].trim().length > 1) return addNoteHere(issue[1].trim(), "issue");
  const note = NOTE_SAID.exec(text);
  if (note && note[1].trim().length > 1) return addNoteHere(note[1].trim());
  const said = normalizeSpeech(text).replace(/^(?:please|bitte) /, "").replace(/ (?:please|bitte)$/, "");
  if (HERE_SAID.test(said)) return Promise.resolve(notesHere());
  if (FINISH_SAID.test(said)) {
    const { walkStep } = useTwin.getState();
    if (walkStep !== null && walkStep < walkSteps().length - 1 && said === "fertig") return null;
    return Promise.resolve(finishJob());
  }
  return null;
}

if (typeof window !== "undefined") {
  (window as unknown as { __twinNotes: unknown }).__twinNotes = { useNotes, addNoteHere, notesHere, finishJob, notesCommand, openNotes, spacesAtStep };
}
