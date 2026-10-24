// Level 4 in the twin: a new building from floor plan images. Own small store so nothing else has to change.
// The draft is shown in the normal scene by swapping `building`/`model`/`state` in useTwin (buildingKey stays, so
// the chat still reaches the server, whose level4 tools work on the same draft). Problems are a red highlight.

import { create } from "zustand";
import { level4, type Along, type Level4Card, type Level4Fix, type Level4Preview } from "../api/level4";
import type { Building, BuildingState } from "../api/types";
import { buildModel, type BuildingModel } from "../model/model";
import { COLOURS } from "../model/palette";
import { useTwin } from "../store";

export type Step = "closed" | "form" | "reading" | "review" | "card" | "saved";

export interface FloorImage {
  id: number;
  file: File;
  url: string; // object URL for the thumbnail
  level: number;
}

interface Snapshot {
  building: Building | null;
  model: BuildingModel | null;
  state: BuildingState | null;
  focusedFloorId: string | null;
}

interface NewBuildingState {
  step: Step;
  floors: FloorImage[];
  along: Along | "scale_bar";
  length: string;
  name: string;
  progress: string;
  error: string | null;
  note: string | null; // what the last fix did, or which floors could not be read
  preview: Level4Preview | null;
  doorFrom: string | null; // first room of "add a door", waiting for the second tap
  card: Level4Card | null;
  acceptProblems: boolean;
  savedKey: string | null;
  busy: boolean;

  open: () => Promise<void>;
  close: () => void;
  addFiles: (files: FileList | File[]) => void;
  removeFloor: (id: number) => void;
  setLevel: (id: number, level: number) => void;
  setAlong: (along: Along | "scale_bar") => void;
  setLength: (length: string) => void;
  setName: (name: string) => void;
  read: () => Promise<void>;
  startOver: () => Promise<void>;
  fix: (fix: Level4Fix) => Promise<void>;
  startDoor: (spaceId: string | null) => void;
  askSave: () => Promise<void>;
  answer: (yes: boolean) => Promise<void>;
  setAcceptProblems: (on: boolean) => void;
  refresh: () => Promise<void>;
}

const TYPES = new Set(["image/png", "image/jpeg"]);
const MAX_BYTES = 10 * 1024 * 1024;
const MAX_SIDE = 4000; // phone photos are bigger than the reader needs; the server allows up to 8000 px
let floorId = 0;
let snapshot: Snapshot | null = null;
let shownView: Building | null = null;
let pollTimer: number | undefined;

/** PNG/JPG under the limits pass as they are; anything else the browser can show (HEIC from an iPhone, WebP,
 *  a huge photo) is redrawn as a JPG. Throws one plain sentence if it is not an image at all. */
export async function prepareImage(file: File): Promise<Blob> {
  if (!file.type.startsWith("image/") && file.type !== "") {
    throw new Error(`"${file.name}" is not an image. Choose a photo or a PNG/JPG of the floor plan.`);
  }
  let bitmap: ImageBitmap | HTMLImageElement;
  try {
    bitmap = await loadImage(file);
  } catch {
    throw new Error(`"${file.name}" could not be opened as an image. Choose a PNG or JPG.`);
  }
  const width = bitmap.width;
  const height = bitmap.height;
  if (Math.min(width, height) < 200) {
    throw new Error(`"${file.name}" is too small to read (${width} × ${height} px). Use a larger photo or image.`);
  }
  if (TYPES.has(file.type) && file.size <= MAX_BYTES && Math.max(width, height) <= MAX_SIDE) return file;
  const scale = Math.min(1, MAX_SIDE / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext("2d")!;
  context.fillStyle = "#fff"; // transparent PNG areas become paper, not black
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
  if (!blob) throw new Error(`"${file.name}" could not be converted. Choose a PNG or JPG.`);
  if (blob.size > MAX_BYTES) throw new Error(`"${file.name}" is larger than 10 MB, even after shrinking.`);
  return blob;
}

function loadImage(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if ("createImageBitmap" in window) return createImageBitmap(file).catch(() => loadElement(file));
  return loadElement(file);
}

function loadElement(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => (URL.revokeObjectURL(url), resolve(image));
    image.onerror = () => (URL.revokeObjectURL(url), reject(new Error("not an image")));
    image.src = url;
  });
}

/** One short line: the counts, then the most important problem (no way out first) and how many more there are. */
export function findingsLine(preview: Level4Preview): string {
  const head = (preview.summary ?? "").split(". ")[0];
  const counts = head ? `${head.replace(/\.$/, "")}.` : "";
  const errors = (preview.findings ?? []).filter((finding) => finding.level === "error");
  if (!errors.length) return `${counts} No problems found.`.trim();
  const main = errors.find((finding) => finding.code === "room_unreachable") ?? errors[0];
  const more = errors.length - 1;
  const rest = more ? ` ${more} more problem${more > 1 ? "s are" : " is"} marked red.` : "";
  return `${counts} ${main.message}${rest}`.trim();
}

/** Show the draft in the scene instead of the open building (first time: remember the building and frame it). */
function showDraft(preview: Level4Preview) {
  const view = preview.draft;
  if (!view) return;
  const twin = useTwin.getState();
  const first = snapshot === null;
  if (first) {
    snapshot = { building: twin.building, model: twin.model, state: twin.state, focusedFloorId: twin.focusedFloorId };
  }
  const model = buildModel(view);
  const red = [...(preview.suspect_spaces ?? [])];
  const keepFloor = !first && model.floorById.has(twin.focusedFloorId ?? "");
  shownView = view;
  useTwin.setState({
    building: view,
    model,
    state: view.state,
    selection: null,
    popover: null,
    highlights: red.length ? { draft: { ids: red, colour: COLOURS.danger } } : {},
    focusedFloorId: keepFloor ? twin.focusedFloorId : (model.floors[0]?.id ?? null),
    ...({ draft: true } as object), // store field requested from the scene session (Card hides while it is set)
  });
  if (first) window.setTimeout(() => useTwin.getState().requestCamera({ kind: "home" }), 60); // after the scene took the model
}

/** Put the building back that was open before the draft (nothing saved). */
function hideDraft(restore: boolean) {
  if (snapshot && restore) {
    useTwin.setState({ ...snapshot, selection: null, popover: null, highlights: {}, ...({ draft: false } as object) });
    useTwin.getState().requestCamera({ kind: "home" });
  } else if (snapshot) {
    useTwin.setState({ ...({ draft: false } as object) });
  }
  snapshot = null;
  shownView = null;
}

function stopPolling() {
  if (pollTimer !== undefined) window.clearInterval(pollTimer);
  pollTimer = undefined;
}

export const useNewBuilding = create<NewBuildingState>((set, get) => ({
  step: "closed",
  floors: [],
  along: "building_width",
  length: "",
  name: "",
  progress: "",
  error: null,
  note: null,
  preview: null,
  doorFrom: null,
  card: null,
  acceptProblems: false,
  savedKey: null,
  busy: false,

  async open() {
    set({ step: "form", error: null, note: null, savedKey: null });
    try {
      const status = await level4.status();
      if (status.state === "running") {
        set({ step: "reading", progress: status.message ?? "Reading…" });
        poll(set, get);
      } else if (status.has_draft) {
        await get().refresh(); // a draft from earlier (or from the chat): continue with it
      }
    } catch {
      /* no status: just show the form */
    }
  },

  close() {
    stopPolling();
    hideDraft(true);
    set({ step: "closed", doorFrom: null, card: null, error: null, note: null });
  },

  addFiles(files) {
    const list = Array.from(files).filter((file) => file.type.startsWith("image/") || file.type === "");
    if (list.length < Array.from(files).length) {
      set({ error: "That is not an image. Choose a photo or a PNG/JPG of the floor plan." });
      if (!list.length) return;
    }
    const used = new Set(get().floors.map((floor) => floor.level));
    const added: FloorImage[] = [];
    let level = 0;
    for (const file of list) {
      while (used.has(level)) level += 1;
      used.add(level);
      added.push({ id: ++floorId, file, url: URL.createObjectURL(file), level });
    }
    set({ floors: [...get().floors, ...added].sort((a, b) => a.level - b.level) });
    if (list.length === Array.from(files).length) set({ error: null });
  },
  removeFloor(id) {
    const floor = get().floors.find((item) => item.id === id);
    if (floor) URL.revokeObjectURL(floor.url);
    set({ floors: get().floors.filter((item) => item.id !== id) });
  },
  setLevel(id, level) {
    set({ floors: get().floors.map((floor) => (floor.id === id ? { ...floor, level } : floor)) });
  },
  setAlong(along) {
    const length = get().length;
    if (along === "door" && !length) set({ along, length: "0.9" });
    else if (along !== "door" && length === "0.9") set({ along, length: "" });
    else set({ along });
  },
  setLength(length) {
    set({ length });
  },
  setName(name) {
    set({ name });
  },

  async read() {
    const { floors, along, length, name } = get();
    if (!floors.length) return set({ error: "Add a photo or image of at least one floor plan." });
    const levels = floors.map((floor) => floor.level);
    if (new Set(levels).size !== levels.length) return set({ error: "Two images have the same floor number." });
    const metres = Number(length.replace(",", "."));
    if (along !== "scale_bar" && !(metres > 0)) {
      return set({ error: "Give one length you know in metres, for example the width of the building." });
    }
    set({ busy: true, error: null, progress: "Uploading…" });
    try {
      const sent = [];
      for (const floor of floors) {
        set({ progress: `Uploading floor ${floor.level}…` });
        const image = await prepareImage(floor.file);
        const { upload_id } = await level4.upload(image);
        sent.push(
          along === "scale_bar"
            ? { upload_id, level: floor.level, scale_bar: true }
            : { upload_id, level: floor.level, known_length_m: metres, along },
        );
      }
      const status = await level4.build(sent, name.trim() || undefined);
      set({ step: "reading", busy: false, progress: status.message ?? "Reading…" });
      poll(set, get);
    } catch (error) {
      set({ busy: false, error: (error as Error).message, progress: "" });
    }
  },

  async startOver() {
    stopPolling();
    hideDraft(true);
    get().floors.forEach((floor) => URL.revokeObjectURL(floor.url));
    set({ step: "form", floors: [], preview: null, card: null, doorFrom: null, error: null, note: null });
    await level4.reset().catch(() => undefined);
  },

  async fix(fix) {
    set({ busy: true, error: null, doorFrom: null });
    try {
      const preview = await level4.fix(fix);
      lastVersion = preview.version ?? lastVersion;
      set({ preview, busy: false, note: preview.done ?? null });
      showDraft(preview);
    } catch (error) {
      set({ busy: false, error: (error as Error).message });
    }
  },

  startDoor(spaceId) {
    useTwin.getState().select(null); // the next tap is the second room
    set({ doorFrom: spaceId, note: null, error: null });
  },

  async askSave() {
    set({ busy: true, error: null, doorFrom: null });
    try {
      const { card } = await level4.card();
      set({ card, step: "card", busy: false, acceptProblems: false });
    } catch (error) {
      set({ busy: false, error: (error as Error).message });
    }
  },

  async answer(yes) {
    set({ busy: true, error: null });
    try {
      const result = await level4.save(yes ? "yes" : "no", yes && get().acceptProblems);
      if (yes && result.saved && result.key) {
        hideDraft(false);
        set({ step: "saved", savedKey: result.key, card: null, busy: false, preview: null });
        const twin = useTwin.getState();
        await twin.loadBuildings();
        await twin.openBuilding(result.key);
        return;
      }
      set({ step: "review", card: null, busy: false, note: yes ? null : "Not saved. Keep fixing, or save later." });
      if (yes) set({ error: String(result.message ?? result.error ?? "Not saved.") });
    } catch (error) {
      set({ step: "review", card: null, busy: false, error: (error as Error).message });
    }
  },
  setAcceptProblems(acceptProblems) {
    set({ acceptProblems });
  },

  async refresh() {
    try {
      const preview = await level4.preview();
      if (!preview.draft) return;
      lastVersion = preview.version ?? lastVersion;
      set({ preview, step: get().step === "card" ? "card" : "review" });
      showDraft(preview);
    } catch (error) {
      set({ error: (error as Error).message });
    }
  },
}));

function poll(set: (partial: Partial<NewBuildingState>) => void, get: () => NewBuildingState) {
  stopPolling();
  pollTimer = window.setInterval(async () => {
    if (get().step !== "reading") return stopPolling();
    try {
      const status = await level4.status();
      if (status.state === "running") {
        const seconds = status.seconds ? ` · ${Math.round(status.seconds)} s` : "";
        set({ progress: `${(status.message ?? "Reading").replace(/\.$/, "")}…${seconds}` });
        return;
      }
      stopPolling();
      const failed = (status.errors ?? []).map((item) => `Floor ${item.level}: ${item.error}`).join(" ");
      if (status.state === "error" || !status.has_draft) {
        set({ step: "form", progress: "", error: failed || "The plans could not be read. Try a clearer image." });
        return;
      }
      set({ note: failed || null, progress: "" });
      await get().refresh();
    } catch (error) {
      stopPolling();
      set({ step: "form", progress: "", error: (error as Error).message });
    }
  }, 800);
}

// The open building changed under the draft (building menu, or the chat saved/opened one): leave draft mode.
useTwin.subscribe((twin, before) => {
  if (twin.building === before.building || !shownView || twin.building === shownView) return;
  const nb = useNewBuilding.getState();
  snapshot = null;
  shownView = null;
  useTwin.setState({ ...({ draft: false } as object) });
  if (nb.step === "review" || nb.step === "card") useNewBuilding.setState({ step: "closed", doorFrom: null, card: null });
});

// The chat may change the draft with its level4 tools (or build one): after each agent reply, show the new version.
let lastVersion: number | null = null;
void level4
  .status()
  .then((status) => (lastVersion ??= status.version))
  .catch(() => undefined);

useTwin.subscribe((twin, before) => {
  if (twin.chat.length === before.chat.length || twin.chat[twin.chat.length - 1]?.role !== "agent") return;
  const step = useNewBuilding.getState().step;
  if (step !== "review" && step !== "closed") return;
  void level4
    .status()
    .then((status) => {
      const seen = lastVersion;
      lastVersion = status.version;
      if (!status.has_draft || status.state === "running" || status.version === seen) return;
      if (useNewBuilding.getState().step === "closed") useNewBuilding.setState({ step: "review" });
      return useNewBuilding.getState().refresh();
    })
    .catch(() => undefined);
});
