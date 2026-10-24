// Planner list (laptop only): one small "List" button top right opens a slim sheet beside the 3D with three
// sections, no tabs: Changes (everything that differs from the loaded building), Rooms and Things (grouped by
// floor, searchable). Tap = fly + select. Keys: L toggles, Esc closes, arrows move between rows.
// Every fact comes from `state` / `model` (the API); "What changes?" asks the agent and only shows its words.

import { useEffect, useMemo, useRef, useState } from "react";
import type { BuildingState, Point, Space } from "../api/types";
import { floorLabel, type BuildingModel } from "../model/model";
import { prettyType } from "../model/palette";
import { useTwin } from "../store";
import { withoutAnswerLine } from "../voice";
import "./Planner.css";

const IMPACT = "impact";
const IMPACT_COLOUR = "#f43f5e";
const IMPACT_QUESTION = "What changes for routes now, with the closures as they are? At most three short sentences; name only rooms that are worse off now.";
const THING_CATEGORIES = new Set(["machine", "equipment"]);

interface Row {
  key: string;
  label: string;
  detail?: string;
  floorId: string;
  go: () => void;
  undo?: { label: string; run: () => void };
}

export function Planner() {
  const profile = useTwin((s) => s.profile);
  const model = useTwin((s) => s.model);
  const draft = useTwin((s) => s.draft);
  const [open, setOpen] = useState(false);
  const enabled = profile === "planner" && !!model && !draft;

  useEffect(() => {
    if (!enabled) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      const typing = !!target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
      const inSheet = !!target?.closest(".planner-sheet");
      if (event.key === "Escape" && open && (!typing || inSheet)) {
        event.preventDefault();
        setOpen(false);
      } else if (!typing && (event.key === "l" || event.key === "L")) {
        event.preventDefault();
        setOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, open]);

  if (!enabled) return null;
  return (
    <>
      <button
        className={`planner-toggle ${open ? "active" : ""}`}
        onClick={() => setOpen(!open)}
        title="Rooms, things and changes (L)"
        aria-expanded={open}
      >
        List
      </button>
      {open && <Sheet model={model!} onClose={() => setOpen(false)} />}
    </>
  );
}

function Sheet({ model, onClose }: { model: BuildingModel; onClose: () => void }) {
  const state = useTwin((s) => s.state);
  const [query, setQuery] = useState("");
  const sheetRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => searchRef.current?.focus(), []);

  // The camera frames fly-tos left of the sheet.
  useEffect(() => {
    const { setRightInset } = useTwin.getState();
    const sheet = sheetRef.current;
    if (!sheet) return;
    const observer = new ResizeObserver(() => setRightInset(Math.round(window.innerWidth - sheet.getBoundingClientRect().left)));
    observer.observe(sheet);
    return () => {
      observer.disconnect();
      setRightInset(0);
    };
  }, []);

  const changes = useChangeRows(model, state);
  const rooms = useMemo(() => roomRows(model), [model]);
  const things = useMemo(() => thingRows(model), [model]);
  const q = query.trim().toLowerCase();
  const match = (row: Row) => !q || `${row.label} ${row.detail ?? ""}`.toLowerCase().includes(q);
  // Corridors only when searched for: they would bury the rooms.
  const shownRooms = rooms.filter((row) => (q ? match(row) : !row.key.startsWith("corridor:")));
  const shownThings = things.filter(match);

  // Without changes to show, open at the rooms of the floor in view (big buildings start in the basement).
  useEffect(() => {
    if (changes.length) return;
    const floorId = useTwin.getState().focusedFloorId;
    const group = bodyRef.current?.querySelector<HTMLElement>(`.planner-rooms [data-floor="${CSS.escape(floorId ?? "")}"]`);
    if (group && bodyRef.current) bodyRef.current.scrollTop = group.offsetTop - 8;
  }, []);

  // Up/Down move between rows (and from the search into the list), Enter on a row = tap.
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const rows = Array.from(sheetRef.current?.querySelectorAll<HTMLButtonElement>(".planner-row") ?? []);
    if (!rows.length) return;
    event.preventDefault();
    const index = rows.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "ArrowDown") rows[Math.min(index + 1, rows.length - 1)].focus();
    else if (index <= 0) searchRef.current?.focus();
    else rows[index - 1].focus();
  };

  return (
    <div className="planner-sheet" ref={sheetRef} onKeyDown={onKeyDown} role="dialog" aria-label="List">
      <div className="planner-head">
        <input
          ref={searchRef}
          className="planner-search"
          placeholder="Filter rooms and things"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Filter rooms and things"
        />
        <button className="x" onClick={onClose} title="Close (Esc)" aria-label="Close">
          ×
        </button>
      </div>
      <div className="planner-body" ref={bodyRef}>
        {(!q || changes.some(match)) && (
          <section>
            <h3>Changes</h3>
            {changes.length === 0 ? <p className="planner-empty">Same as the loaded building.</p> : <Rows model={model} rows={changes.filter(match)} grouped={false} />}
            <Impact model={model} />
          </section>
        )}
        {(!q || shownRooms.length > 0) && (
          <section className="planner-rooms">
            <h3>Rooms</h3>
            <Rows model={model} rows={shownRooms} />
          </section>
        )}
        {shownThings.length > 0 && (
          <section>
            <h3>Things</h3>
            <Rows model={model} rows={shownThings} />
          </section>
        )}
        {q && !shownRooms.length && !shownThings.length && !changes.some(match) && <p className="planner-empty">Nothing matches “{query.trim()}”.</p>}
      </div>
    </div>
  );
}

function Rows({ model, rows, grouped = true }: { model: BuildingModel; rows: Row[]; grouped?: boolean }) {
  const stacked = !grouped; // changes: full sentence, detail below
  const groups: { floorId: string; rows: Row[] }[] = [];
  for (const row of rows) {
    const last = groups[groups.length - 1];
    if (last && (!grouped || last.floorId === row.floorId)) last.rows.push(row);
    else groups.push({ floorId: row.floorId, rows: [row] });
  }
  return (
    <>
      {groups.map((group) => {
        const floor = model.floorById.get(group.floorId);
        return (
          <div key={group.floorId + group.rows[0].key} className="planner-group" data-floor={group.floorId}>
            {grouped && floor && <div className="planner-floor">{floorLabel(floor)}</div>}
            {group.rows.map((row) => (
              <div key={row.key} className="planner-line">
                <button className={`planner-row ${stacked ? "stacked" : ""}`} onClick={row.go}>
                  <span className="planner-label">{row.label}</span>
                  {row.detail && <span className="planner-detail">{row.detail}</span>}
                </button>
                {row.undo && (
                  <button className="planner-undo" onClick={row.undo.run}>
                    {row.undo.label}
                  </button>
                )}
              </div>
            ))}
          </div>
        );
      })}
    </>
  );
}

// ---------- rows ----------

function byFloorThenName(model: BuildingModel) {
  const level = (floorId: string) => model.floorById.get(floorId)?.level ?? 0;
  return (a: Row, b: Row) => level(a.floorId) - level(b.floorId) || a.label.localeCompare(b.label, undefined, { numeric: true });
}

function selectAndFly(kind: "space" | "asset", id: string, floorId: string, spaceId?: string) {
  const { select, flyTo } = useTwin.getState();
  select({ kind, id, floor_id: floorId, ...(spaceId ? { space_id: spaceId } : {}) });
  flyTo(id);
}

function flyToPoint(floorId: string, point: Point) {
  const { focusFloor, requestCamera } = useTwin.getState();
  focusFloor(floorId);
  requestCamera({ kind: "point", floorId, point, radius: 5 });
}

function roomRows(model: BuildingModel): Row[] {
  return model.building.spaces
    .map((space) => ({
      key: `${space.type === "corridor" ? "corridor" : "room"}:${space.id}`,
      label: space.name || prettyType(space.room_type || space.type),
      detail: roomDetail(space),
      floorId: space.floor_id,
      go: () => selectAndFly("space", space.id, space.floor_id),
    }))
    .sort(byFloorThenName(model));
}

/** Ref and type, minus what the name already says ("Kitchen 0.25" needs neither). */
function roomDetail(space: Space): string | undefined {
  const name = (space.name ?? "").toLowerCase();
  const type = prettyType(space.room_type || space.type);
  const parts = [space.ref, type].filter((part): part is string => !!part && !name.includes(part.toLowerCase()));
  return parts.join(" · ") || undefined;
}

function thingRows(model: BuildingModel): Row[] {
  return model.building.assets
    .filter((asset) => THING_CATEGORIES.has(asset.category ?? ""))
    .map((asset) => ({
      key: `asset:${asset.id}`,
      label: asset.name,
      detail: model.spaceById.get(asset.space_id)?.name,
      floorId: asset.floor_id,
      go: () => selectAndFly("asset", asset.id, asset.floor_id, asset.space_id),
    }))
    .sort(byFloorThenName(model));
}

function roomName(model: BuildingModel, spaceId: string | undefined): string {
  const space = spaceId ? model.spaceById.get(spaceId) : undefined;
  return space ? space.name || prettyType(space.room_type || space.type) : spaceId ?? "?";
}

function between(model: BuildingModel, spaceIds: string[]): string {
  return spaceIds.length >= 2 ? `between ${roomName(model, spaceIds[0])} and ${roomName(model, spaceIds[1])}` : `at ${roomName(model, spaceIds[0])}`;
}

function useChangeRows(model: BuildingModel, state: BuildingState | null): Row[] {
  const setClosed = useTwin((s) => s.setClosed);
  if (!state) return [];
  const rows: Row[] = [];
  const level = (floorId: string) => floorLabel(model.floorById.get(floorId) ?? { id: floorId, level: 0, name: floorId, elevation_m: 0, height_m: 0 });

  for (const id of state.closed) {
    const reopen = { label: "Reopen", run: () => void setClosed(id, false) };
    const space = model.spaceById.get(id);
    const opening = model.openingById.get(id) ?? state.added_doors.find((door) => door.id === id);
    const connector = model.connectorById.get(id);
    if (space) {
      rows.push({ key: `closed:${id}`, label: `${roomName(model, id)} closed`, detail: level(space.floor_id), floorId: space.floor_id, go: () => selectAndFly("space", id, space.floor_id), undo: reopen });
    } else if (opening) {
      rows.push({ key: `closed:${id}`, label: `Door closed ${between(model, opening.space_ids)}`, detail: level(opening.floor_id), floorId: opening.floor_id, go: () => flyToPoint(opening.floor_id, opening.position), undo: reopen });
    } else if (connector) {
      const floorId = connector.floor_ids[0];
      rows.push({ key: `closed:${id}`, label: `${connector.name || prettyType(connector.kind)} closed`, detail: `${prettyType(connector.kind)} · all floors`, floorId, go: () => useTwin.getState().flyTo(id), undo: reopen });
    } else {
      rows.push({ key: `closed:${id}`, label: `${id} closed`, floorId: model.floors[0]?.id ?? "", go: () => undefined, undo: reopen });
    }
  }
  for (const door of state.added_doors) {
    rows.push({ key: `door:${door.id}`, label: `New door ${between(model, door.space_ids)}`, detail: level(door.floor_id), floorId: door.floor_id, go: () => flyToPoint(door.floor_id, door.position) });
  }
  for (const [id, edit] of Object.entries(state.added_assets ?? {})) {
    rows.push({ key: `added:${id}`, label: `${edit.name} added`, detail: `in ${roomName(model, edit.space_id)} · ${level(edit.floor_id)}`, floorId: edit.floor_id, go: () => flyToPoint(edit.floor_id, edit.position) });
  }
  for (const [id, edit] of Object.entries(state.moved_assets ?? {})) {
    rows.push({ key: `moved:${id}`, label: `${edit.name} moved`, detail: `to ${roomName(model, edit.space_id)} · ${level(edit.floor_id)}`, floorId: edit.floor_id, go: () => flyToPoint(edit.floor_id, edit.position) });
  }
  for (const id of state.removed_assets ?? []) {
    const asset = model.assetById.get(id);
    if (!asset) continue; // an added thing that was taken back again
    rows.push({ key: `removed:${id}`, label: `${asset.name} removed`, detail: `from ${roomName(model, asset.space_id)} · ${level(asset.floor_id)}`, floorId: asset.floor_id, go: () => flyToPoint(asset.floor_id, asset.position) });
  }
  for (const id of state.removed_openings ?? []) {
    const opening = model.openingById.get(id);
    if (!opening) continue;
    rows.push({ key: `gone:${id}`, label: `Door removed ${between(model, opening.space_ids)}`, detail: level(opening.floor_id), floorId: opening.floor_id, go: () => flyToPoint(opening.floor_id, opening.position) });
  }
  for (const [id, width] of Object.entries(state.widened_openings ?? {})) {
    const opening = model.openingById.get(id);
    if (!opening) continue;
    rows.push({ key: `wide:${id}`, label: `Door widened to ${width.toFixed(2)} m`, detail: `${between(model, opening.space_ids)} · ${level(opening.floor_id)}`, floorId: opening.floor_id, go: () => flyToPoint(opening.floor_id, opening.position) });
  }
  return rows;
}

// ---------- "What changes?" ----------

/** Rooms the reply names (unique names or refs only, longest first so "Hall B" is not also "Hall"). */
function roomsNamed(model: BuildingModel, text: string): string[] {
  const count = new Map<string, number>();
  for (const space of model.building.spaces) if (space.name) count.set(space.name, (count.get(space.name) ?? 0) + 1);
  const candidates: { word: string; id: string }[] = [];
  for (const space of model.building.spaces) {
    if (space.type === "corridor") continue;
    if (space.name && space.name.length >= 3 && count.get(space.name) === 1) candidates.push({ word: space.name, id: space.id });
    if (space.ref && space.ref.length >= 2) candidates.push({ word: space.ref, id: space.id });
  }
  candidates.sort((a, b) => b.word.length - a.word.length);
  let rest = text;
  const ids = new Set<string>();
  for (const { word, id } of candidates) {
    const pattern = new RegExp(`(^|[^\\w])${word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\w])`, "g");
    if (pattern.test(rest)) {
      ids.add(id);
      rest = rest.replace(pattern, "$1 ");
    }
  }
  return [...ids];
}

function Impact({ model }: { model: BuildingModel }) {
  const closed = useTwin((s) => s.state?.closed ?? []);
  const chatAvailable = useTwin((s) => s.chatAvailable);
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<{ text: string; for: string; rooms: string[] } | null>(null);
  const closedKey = closed.join(",");

  // A new set of closures makes the old answer and its red rooms stale.
  useEffect(() => {
    if (answer && answer.for !== closedKey) {
      setAnswer(null);
      useTwin.getState().setHighlight(IMPACT, null);
    }
  }, [closedKey, answer]);

  if (!closed.length || !chatAvailable) return null;

  const run = async () => {
    setBusy(true);
    const { select, ask, dismissReply, setHighlight } = useTwin.getState();
    select(null); // ask about the building, not about whatever is selected
    const reply = await ask(IMPACT_QUESTION);
    dismissReply(); // the answer lives here, not twice in the card
    setBusy(false);
    if (!reply || reply.error) {
      setAnswer({ text: reply?.error ?? "The agent did not answer.", for: closedKey, rooms: [] });
      return;
    }
    const text = withoutAnswerLine(reply.reply).replace(/\*\*|__|^#+\s*/gm, "");
    const ids = roomsNamed(model, reply.reply).filter((id) => !closed.includes(id)); // closed rooms are listed above
    setAnswer({ text, for: closedKey, rooms: ids });
    setHighlight(IMPACT, ids.length ? { ids, colour: IMPACT_COLOUR } : null);
  };

  const clear = () => {
    setAnswer(null);
    useTwin.getState().setHighlight(IMPACT, null);
  };

  return (
    <div className="planner-impact">
      {!answer && (
        <button onClick={() => void run()} disabled={busy}>
          {busy ? "Asking…" : "What changes?"}
        </button>
      )}
      {answer && (
        <div className="planner-answer">
          <p>{answer.text}</p>
          {answer.rooms.length > 0 && (
            <Rows
              model={model}
              grouped={false}
              rows={answer.rooms.map((id) => {
                const space = model.spaceById.get(id)!;
                const floor = model.floorById.get(space.floor_id);
                return { key: `impact:${id}`, label: roomName(model, id), detail: floor ? floorLabel(floor) : undefined, floorId: space.floor_id, go: () => selectAndFly("space", id, space.floor_id) };
              })}
            />
          )}
          <button className="x" onClick={clear} title="Hide" aria-label="Hide">
            ×
          </button>
        </div>
      )}
    </div>
  );
}
