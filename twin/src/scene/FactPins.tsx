// Fact pins on the map (owner: notes session; spec docs/specs/place-knowledge.md): one small tag per room with notes
// or problems valid now, in the room's top-right corner so the centred room name stays readable (a machine note: just
// above the machine). Shown with the layer "Notes & photos" on (off by default); during guidance the rooms of the
// route show theirs anyway. Tap: the newest note with age, author and photo; tap that: the list. Closures are not
// pinned here (they keep their own closure marks).

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Html } from "@react-three/drei";
import type { Point } from "../api/types";
import type { BuildingModel } from "../model/model";
import { newestFirst, sinceLabel, type Note } from "../notes/notes";
import { closeNotes, notesIn, openNotes, relevantNotes, useNotes } from "../notes/notesStore";
import { useTwin } from "../store";

interface Props {
  model: BuildingModel;
  floorY: (floorId: string) => number;
  visibleFloors: Set<string>;
}

function Pop({ note, count, onOpen }: { note: Note; count: number; onOpen: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  // Near a screen edge the preview slides back inside the viewport (8 px margin).
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    element.style.translate = "0px";
    const box = element.getBoundingClientRect();
    const margin = 8;
    const shift = box.left < margin ? margin - box.left : box.right > window.innerWidth - margin ? window.innerWidth - margin - box.right : 0;
    if (shift) element.style.translate = `${Math.round(shift)}px`;
  });
  return (
    <div ref={ref} className="note-pin-pop" role="button" tabIndex={0} onClick={(event) => (event.stopPropagation(), onOpen())}>
      {note.photo && <img src={note.photo} alt="" />}
      <div className="note-meta">
        {note.kind === "issue" && <span className="note-kind">Problem</span>}
        {sinceLabel(note)}
      </div>
      {note.text && <p className="note-text">{note.text}</p>}
      <div className="note-meta">{count > 1 ? `All ${count} notes here` : "Open"}</div>
    </div>
  );
}

/** Room notes sit in the room's top-right corner (inset), away from the centred room name and the route pins. */
function innerCorner(polygon: Point[], anchor: Point): Point {
  if (polygon.length < 3) return anchor;
  const xs = polygon.map((p) => p[0]);
  const ys = polygon.map((p) => p[1]);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const inset = Math.min(1.4, (maxX - minX) * 0.2, (maxY - minY) * 0.2);
  const corner: Point = [maxX - inset, maxY - inset];
  // An L-shaped room may not contain its bounding-box corner: fall back to halfway between corner and anchor.
  return inside(corner, polygon) ? corner : [(corner[0] + anchor[0]) / 2, (corner[1] + anchor[1]) / 2];
}

function inside(point: Point, polygon: Point[]): boolean {
  let hit = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > point[1] !== yj > point[1] && point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

export function FactPins({ model, floorY, visibleFloors }: Props) {
  const notes = useNotes((s) => s.notes);
  const layer = useNotes((s) => s.layer);
  const guide = useNotes((s) => s.guide);
  const walkStep = useTwin((s) => s.walkStep);
  const route = useTwin((s) => s.state?.route ?? null);
  const [open, setOpen] = useState<string | null>(null);
  // The preview closes on any tap elsewhere and when the guidance moves on.
  useEffect(() => setOpen(null), [walkStep]);
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!(event.target as HTMLElement | null)?.closest?.(".note-pin")) setOpen(null);
    };
    window.addEventListener("pointerdown", close, true);
    return () => window.removeEventListener("pointerdown", close, true);
  }, [open]);
  // During guidance the note card already shows these notes: no second marker next to the destination pin.
  const shown = new Set(guide?.notes.map((note) => note.anchor.space_id) ?? []);
  // Layer on: every room with notes. Layer off: only the rooms of the route being walked.
  const onRoute = walkStep !== null && route?.ok ? [route.start, ...(route.space_path ?? []), ...(route.via ?? []), route.destination] : [];
  const spaces = layer ? new Set(notes.map((note) => note.anchor.space_id)) : new Set(onRoute.filter((id): id is string => !!id));
  const bySpace = new Map<string, Note[]>();
  for (const spaceId of spaces) {
    const space = model.spaceById.get(spaceId);
    if (!space || !visibleFloors.has(space.floor_id) || shown.has(spaceId)) continue;
    const here = layer ? notesIn([spaceId]) : relevantNotes(notesIn([spaceId])); // walking: only what matters, no noise
    if (here.length) bySpace.set(spaceId, here);
  }
  return (
    <>
      {[...bySpace].map(([spaceId, list]) => {
        const newest = [...list].sort(newestFirst)[0];
        const issue = list.some((note) => note.kind === "issue");
        const space = model.spaceById.get(spaceId)!;
        const asset = newest.anchor.asset_id ? model.assetById.get(newest.anchor.asset_id) : undefined;
        const point = asset ? asset.position : innerCorner(space.polygon, space.anchor);
        const show = () => {
          setOpen(null);
          closeNotes();
          useTwin.getState().select({ kind: "space", id: spaceId, floor_id: space.floor_id });
          openNotes("here");
        };
        return (
          <Html key={spaceId} position={[point[0], floorY(space.floor_id) + 0.1, -point[1]]} center zIndexRange={[4, 0]}>
            <button
              className={`note-pin ${asset ? "" : "corner"} ${issue ? "issue" : ""}`}
              aria-label={`${list.length} note${list.length > 1 ? "s" : ""}${issue ? " with a problem" : ""} in ${space.name}`}
              onClick={(event) => {
                event.stopPropagation();
                setOpen(open === spaceId ? null : spaceId);
              }}
            >
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" aria-hidden>
                {issue ? <path d="M12 4 21 20H3zM12 10v4.5M12 17.5v.01" /> : <path d="M5 4h14v11l-5 5H5z" />}
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
