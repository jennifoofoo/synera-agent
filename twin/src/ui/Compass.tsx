import { useEffect, useRef, useState } from "react";
import { controlsRef } from "../scene/FloorMesh";
import { useTwin } from "../store";

const TILT_STEP = 0.17; // about 10 degrees per press of a tilt button
const HINT_KEY = "twin.tiltHintSeen";
const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/** Camera nudges behind the floor rail's "…" menu (FloorRail.tsx). North up turns the view north and straight down;
 * tilt goes flatter (towards the horizon, clamped in CameraRig) or steeper (towards top-down). */
export function resetNorth() {
  const c = controlsRef.current;
  if (c) void c.rotateTo(0, c.minPolarAngle, !useTwin.getState().reducedMotion);
}
export function tilt(flatter: boolean) {
  const c = controlsRef.current;
  if (c) void c.rotate(0, flatter ? TILT_STEP : -TILT_STEP, !useTwin.getState().reducedMotion);
}

/** The compass needle as an icon; it follows the camera every frame (no React render). */
export function CompassIcon() {
  const needle = useRef<SVGGElement>(null);
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
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1.4" opacity="0.5" />
      <g ref={needle}>
        <path d="M12 3.5 15 12H9z" fill="var(--signal, #e5484d)" />
        <path d="M12 20.5 9 12h6z" fill="currentColor" opacity="0.55" />
      </g>
    </svg>
  );
}

export function TiltIcon({ flatter = false }: { flatter?: boolean }) {
  // A floor plate seen flat (wide, thin) or from above (taller), with an arrow.
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {flatter ? <path d="M3 17 7 13h14l-4 4z" /> : <path d="M5 20 7 11h12l-2 9z" />}
      <path d={flatter ? "M12 3v6m-2.5-2.5L12 9l2.5-2.5" : "M12 9V3M9.5 5.5 12 3l2.5 2.5"} />
    </svg>
  );
}

/** One-time hint in 3D on the laptop: "Option + drag to tilt", shown after the first plain drag on the map (not at
 * start, where the welcome card is), remembered in localStorage. */
export function TiltHint() {
  const flat = useTwin((s) => s.viewMode === "2d");
  const worker = useTwin((s) => s.profile === "worker");
  const model = useTwin((s) => s.model);
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (flat || worker || !model) return;
    try {
      if (localStorage.getItem(HINT_KEY) === "1") return;
    } catch {
      // storage blocked: show it after the first drag anyway
    }
    let start: { x: number; y: number } | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onDown = (event: PointerEvent) => {
      const onMap = event.target instanceof Element && event.target.closest("canvas");
      start = onMap && !event.altKey ? { x: event.clientX, y: event.clientY } : null;
    };
    const onUp = (event: PointerEvent) => {
      if (!start || Math.hypot(event.clientX - start.x, event.clientY - start.y) < 8) return;
      start = null;
      try {
        localStorage.setItem(HINT_KEY, "1");
      } catch {
        // storage blocked
      }
      window.removeEventListener("pointerdown", onDown, { capture: true });
      window.removeEventListener("pointerup", onUp, { capture: true });
      setShow(true);
      timer = setTimeout(() => setShow(false), 7000);
    };
    window.addEventListener("pointerdown", onDown, { capture: true });
    window.addEventListener("pointerup", onUp, { capture: true });
    return () => {
      window.removeEventListener("pointerdown", onDown, { capture: true });
      window.removeEventListener("pointerup", onUp, { capture: true });
      if (timer) clearTimeout(timer);
    };
  }, [flat, worker, model]);
  if (!show || flat) return null;
  return (
    <div className="tilt-hint" role="status" onClick={() => setShow(false)}>
      {IS_MAC ? "Option" : "Alt"} + drag to tilt and rotate. Or use "…" beside the floors.
    </div>
  );
}
