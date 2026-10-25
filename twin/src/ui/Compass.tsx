import { useEffect, useRef, useState } from "react";
import { controlsRef } from "../scene/FloorMesh";
import { useTwin } from "../store";

const DRAG_START_PX = 4;
const DRAG_RAD_PER_PX = 0.012;
const TILT_STEP = 0.17; // about 10 degrees per press of a tilt button
const HINT_KEY = "twin.tiltHintSeen";
const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/** Compass and tilt buttons at the end of the floor rail (2D and 3D). The needle points north.
 * Click the compass: north up, straight down. Drag it: sideways rotates, up or down tilts (3D).
 * 3D also gets two tilt buttons: flatter (towards the horizon, clamped in CameraRig) and steeper (towards top-down). */
export function Compass() {
  const flat = useTwin((s) => s.viewMode === "2d");
  const needle = useRef<SVGGElement>(null);
  const drag = useRef<{ id: number; x: number; y: number; moved: boolean } | null>(null);

  // The needle follows the camera every frame (no React render; the controls change under the canvas' own loop).
  useEffect(() => {
    let frame = 0;
    let shown = NaN;
    const tick = () => {
      const c = controlsRef.current;
      if (c && needle.current && c.azimuthAngle !== shown) {
        shown = c.azimuthAngle;
        needle.current.setAttribute("transform", `rotate(${(shown * 180) / Math.PI} 12 12)`);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  const onPointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, moved: false };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const onPointerMove = (event: React.PointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    const c = controlsRef.current;
    if (!d || d.id !== event.pointerId || !c) return;
    const dx = event.clientX - d.x;
    const dy = event.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < DRAG_START_PX) return;
    d.moved = true;
    d.x = event.clientX;
    d.y = event.clientY;
    void c.rotate(dx * DRAG_RAD_PER_PX, flat ? 0 : -dy * DRAG_RAD_PER_PX, true);
  };
  const onPointerUp = (event: React.PointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    drag.current = null;
    if (!d || d.id !== event.pointerId || d.moved) return;
    resetNorth();
  };
  const resetNorth = () => {
    const c = controlsRef.current;
    if (c) void c.rotateTo(0, c.minPolarAngle, !useTwin.getState().reducedMotion);
  };
  const tilt = (by: number) => {
    const c = controlsRef.current;
    if (c) void c.rotate(0, by, !useTwin.getState().reducedMotion);
  };

  return (
    <>
      <button
        className="rail-toggle rail-compass"
        data-testid="compass"
        title="Compass: click for north up, drag to rotate"
        aria-label="Compass: north up and straight down"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => (drag.current = null)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            resetNorth();
          }
        }}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden>
          <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1.4" opacity="0.5" />
          <g ref={needle}>
            <path d="M12 3.5 15 12H9z" fill="var(--signal, #e5484d)" />
            <path d="M12 20.5 9 12h6z" fill="currentColor" opacity="0.55" />
          </g>
        </svg>
      </button>
      {!flat && (
        <>
          <button className="rail-toggle rail-tilt" data-testid="tilt-flatter" onClick={() => tilt(TILT_STEP)} title="Tilt towards the horizon (Option + drag)" aria-label="Tilt flatter">
            <TiltIcon flatter />
          </button>
          <button className="rail-toggle rail-tilt" data-testid="tilt-steeper" onClick={() => tilt(-TILT_STEP)} title="Tilt towards straight down" aria-label="Tilt steeper">
            <TiltIcon />
          </button>
        </>
      )}
    </>
  );
}

function TiltIcon({ flatter = false }: { flatter?: boolean }) {
  // A floor plate seen flat (wide, thin) or from above (taller), with an arrow.
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {flatter ? <path d="M3 17 7 13h14l-4 4z" /> : <path d="M5 20 7 11h12l-2 9z" />}
      <path d={flatter ? "M12 3v6m-2.5-2.5L12 9l2.5-2.5" : "M12 9V3M9.5 5.5 12 3l2.5 2.5"} />
    </svg>
  );
}

/** One-time hint in 3D on the laptop: "Option + drag to tilt" (remembered in localStorage). */
export function TiltHint() {
  const flat = useTwin((s) => s.viewMode === "2d");
  const worker = useTwin((s) => s.profile === "worker");
  const model = useTwin((s) => s.model);
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (flat || worker || !model) return;
    let seen = false;
    try {
      seen = localStorage.getItem(HINT_KEY) === "1";
      localStorage.setItem(HINT_KEY, "1");
    } catch {
      // storage blocked: show it this once anyway
    }
    if (seen) return;
    setShow(true);
    const timer = setTimeout(() => setShow(false), 7000);
    return () => clearTimeout(timer);
  }, [flat, worker, model]);
  if (!show || flat) return null;
  return (
    <div className="tilt-hint" role="status" onClick={() => setShow(false)}>
      {IS_MAC ? "Option" : "Alt"} + drag to tilt and rotate. Or use the compass.
    </div>
  );
}
