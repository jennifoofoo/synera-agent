// Bottom sheet for the phone (owner: mobile session). Card, route step and finds go in here.
// Planner: a plain wrapper, the content keeps its own look. Worker: sits above the input, swipe down closes,
// `peek` shows only the first lines until tapped. Never covers the top of the plan (max 45% of the screen).

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTwin } from "../store";
import "./Phone.css";

interface Props {
  open: boolean;
  onClose: () => void;
  label: string;
  peek?: boolean;
  children: ReactNode;
}

const CLOSE_DRAG_PX = 60;

export function PhoneSheet({ open, onClose, label, peek = false, children }: Props) {
  const worker = useTwin((s) => s.profile === "worker");
  const [expanded, setExpanded] = useState(!peek);
  const [drag, setDrag] = useState(0);
  const start = useRef<number | null>(null);

  useEffect(() => setExpanded(!peek), [peek]);
  useEffect(() => {
    if (!open || !worker) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, worker, onClose]);

  if (!open) return null;
  if (!worker) return <div className="sheet">{children}</div>;

  const collapsed = peek && !expanded;
  return (
    <section
      className={`sheet phone-sheet ${collapsed ? "peek" : ""} ${drag ? "dragging" : ""}`}
      aria-label={label}
      style={drag ? { transform: `translateY(${drag}px)` } : undefined}
      onClick={collapsed ? () => setExpanded(true) : undefined}
    >
      <div
        className="sheet-grip"
        onPointerDown={(event) => {
          start.current = event.clientY;
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => start.current !== null && setDrag(Math.max(0, event.clientY - start.current))}
        onPointerUp={() => {
          if (drag > CLOSE_DRAG_PX) onClose();
          else if (drag < 6 && peek) setExpanded(!expanded);
          start.current = null;
          setDrag(0);
        }}
        onPointerCancel={() => {
          start.current = null;
          setDrag(0);
        }}
      >
        <button className="sheet-handle" aria-label={collapsed ? "Show more" : "Close"} onClick={(event) => {
            // Pointer taps are handled on the grip; this is the keyboard path (Enter/Space has detail 0).
            if (event.detail !== 0) return;
            if (collapsed) setExpanded(true);
            else onClose();
          }}
        />
      </div>
      <div className="sheet-body">{children}</div>
    </section>
  );
}
