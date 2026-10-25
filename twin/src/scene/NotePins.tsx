// Note pins on the map (owner: notes session): one small blue tag per room with notes, offset up and right of the
// note's point so the room name under it stays readable. Tap: the newest note with its photo; tap that: the list.

import { useState } from "react";
import { Html } from "@react-three/drei";
import type { BuildingModel } from "../model/model";
import { whenLabel, type Note } from "../notes/notes";
import { closeNotes, openNotes, useNotes } from "../notes/notesStore";
import { useTwin } from "../store";
import { usePhotoUrl } from "../ui/Notes";

interface Props {
  model: BuildingModel;
  floorY: (floorId: string) => number;
  visibleFloors: Set<string>;
}

function Pop({ note, count, onOpen }: { note: Note; count: number; onOpen: () => void }) {
  const url = usePhotoUrl(note.photo);
  return (
    <div className="note-pin-pop" role="button" tabIndex={0} onClick={(event) => (event.stopPropagation(), onOpen())}>
      {url && <img src={url} alt="" />}
      <div className="note-meta">
        <strong>{note.author}</strong> · {whenLabel(note.createdAt)}
      </div>
      {note.text && <p className="note-text">{note.text}</p>}
      <div className="note-meta">{count > 1 ? `All ${count} notes here` : "Open"}</div>
    </div>
  );
}

export function NotePins({ model, floorY, visibleFloors }: Props) {
  const notes = useNotes((s) => s.notes);
  const [open, setOpen] = useState<string | null>(null);
  const bySpace = new Map<string, Note[]>();
  for (const note of notes) {
    if (!visibleFloors.has(note.floorId) || !model.spaceById.has(note.spaceId)) continue;
    bySpace.set(note.spaceId, [...(bySpace.get(note.spaceId) ?? []), note]);
  }
  return (
    <>
      {[...bySpace].map(([spaceId, list]) => {
        const newest = list.reduce((a, b) => (b.createdAt > a.createdAt ? b : a));
        const space = model.spaceById.get(spaceId)!;
        const point = newest.point ?? space.anchor;
        const show = () => {
          setOpen(null);
          closeNotes();
          useTwin.getState().select({ kind: "space", id: spaceId, floor_id: space.floor_id });
          openNotes("here");
        };
        return (
          <Html key={spaceId} position={[point[0], floorY(space.floor_id) + 0.1, -point[1]]} center zIndexRange={[4, 0]}>
            <button
              className="note-pin"
              aria-label={`${list.length} note${list.length > 1 ? "s" : ""} in ${space.name}`}
              onClick={(event) => {
                event.stopPropagation();
                setOpen(open === spaceId ? null : spaceId);
              }}
            >
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" aria-hidden>
                <path d="M5 4h14v11l-5 5H5z" />
              </svg>
              {list.length > 1 && list.length}
              {open === spaceId && <Pop note={newest} count={list.length} onOpen={show} />}
            </button>
          </Html>
        );
      })}
    </>
  );
}
