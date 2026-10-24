// Bottom sheet for the phone (owner: mobile session). Card, route step and finds go in here.
// Planner: a plain wrapper, the content keeps its own look. Worker: sits above the input, swipe down closes,
// `peek` shows only the first lines until tapped. Never covers the top of the plan (max 45% of the screen;
// `tall` allows 75% for a list). `onToggle`: tap or swipe up on the grip toggles the content (e.g. all steps).

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTwin } from "../store";
import "./Phone.css";

interface Props {
  open: boolean;
  onClose: () => void;
  label: string;
  peek?: boolean;
  tall?: boolean;
  onToggle?: () => void;
  children: ReactNode;
}

const CLOSE_DRAG_PX = 60;

export function PhoneSheet({ open, onClose, label, peek = false, tall = false, onToggle, children }: Props) {
  const worker = useTwin((s) => s.profile === "worker");
  const [expanded, setExpanded] = useState(!peek);
  const [drag, setDrag] = useState(0);
  const start = useRef<number | null>(null);
  const lift = useRef(0); // how far the grip was pulled up (only onToggle uses it)

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
      className={`sheet phone-sheet ${collapsed ? "peek" : ""} ${tall ? "tall" : ""} ${drag ? "dragging" : ""}`}
      aria-label={label}
      style={drag ? { transform: `translateY(${drag}px)` } : undefined}
      onClick={collapsed ? () => setExpanded(true) : undefined}
    >
      <div
        className="sheet-grip"
        onPointerDown={(event) => {
          start.current = event.clientY;
          lift.current = 0;
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          if (start.current === null) return;
          const delta = event.clientY - start.current;
          lift.current = Math.max(lift.current, -delta);
          setDrag(Math.max(0, delta));
        }}
        onPointerUp={() => {
          if (drag > CLOSE_DRAG_PX) onClose();
          else if (onToggle && (lift.current > 24 || drag < 6)) onToggle();
          else if (drag < 6 && peek) setExpanded(!expanded);
          start.current = null;
          setDrag(0);
        }}
        onPointerCancel={() => {
          start.current = null;
          setDrag(0);
        }}
      >
        <button className="sheet-handle" aria-label={collapsed ? "Show more" : onToggle ? "Show more or less" : "Close"} onClick={(event) => {
            // Pointer taps are handled on the grip; this is the keyboard path (Enter/Space has detail 0).
            if (event.detail !== 0) return;
            if (collapsed) setExpanded(true);
            else if (onToggle) onToggle();
            else onClose();
          }}
        />
      </div>
      <div className="sheet-body">{children}</div>
    </section>
  );
}
