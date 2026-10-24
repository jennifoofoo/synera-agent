// Phone glue (owner: mobile session). Mounted once in App; renders only on the worker profile.
// - header: the building name, Search (focuses the one input) on the right; no back button (the sheets close themselves)
// - viewport: --vvh/--vvtop follow the visual viewport so the input stays above the iOS keyboard
// - audio unlock on the first tap, screen wake lock while a guide or the step list is active

import { useEffect } from "react";
import { useTwin } from "../store";
import { installAudioUnlock, keepAwake } from "../voice";
import "./Phone.css";

let audioUnlockInstalled = false;

function useVisualViewport() {
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const root = document.documentElement;
    const update = () => {
      if (Math.abs(vv.scale - 1) > 0.01) return; // pinch zoom: leave the layout alone
      root.style.setProperty("--vvh", `${Math.round(vv.height)}px`);
      root.style.setProperty("--vvtop", `${Math.round(vv.offsetTop)}px`);
      root.classList.toggle("keyboard-open", window.innerHeight - vv.height > 120);
      if (window.scrollY) window.scrollTo(0, 0);
    };
    update();
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
    };
  }, []);
}

/** --dock-h: how much of the bottom the input (and sheet) cover; the floor rail stops above it. The same number
 * (from the dock's top edge to the bottom of the screen) goes to the store as bottomInset so the camera frames
 * above it. In landscape the dock sits bottom right beside the plan, so the inset is 0 there. */
function useDockHeight(worker: boolean) {
  const setBottomInset = useTwin((s) => s.setBottomInset);
  useEffect(() => {
    const dock = document.querySelector<HTMLElement>(".dock");
    if (!dock || !worker) return;
    const root = document.documentElement;
    const app = dock.parentElement ?? root;
    const measure = () => {
      const box = dock.getBoundingClientRect();
      const covered = Math.max(0, Math.round(app.getBoundingClientRect().bottom - box.top));
      root.style.setProperty("--dock-h", `${Math.round(box.height)}px`);
      const beside = box.left > window.innerWidth * 0.3; // landscape: dock on the right, plan uses the left
      setBottomInset(beside ? 0 : covered);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(dock);
    observer.observe(app);
    return () => {
      observer.disconnect();
      setBottomInset(0);
    };
  }, [worker, setBottomInset]);
}

export function Phone() {
  const worker = useTwin((s) => s.profile === "worker");
  const walking = useTwin((s) => s.walkStep !== null);
  const guiding = useTwin((s) => !!s.state?.guide?.active) || walking;
  const model = useTwin((s) => s.model);

  useVisualViewport();
  useDockHeight(worker);
  useEffect(() => {
    if (audioUnlockInstalled) return;
    audioUnlockInstalled = true;
    installAudioUnlock();
  }, []);
  useEffect(() => {
    keepAwake("guiding", guiding);
    return () => keepAwake("guiding", false);
  }, [guiding]);

  if (!worker || !model) return null;

  if (walking) return null; // no search or chat while walking the steps
  return (
    <button
      className="phone-search"
      aria-label="Search"
      onClick={() => document.querySelector<HTMLInputElement>(".omnibox-input input")?.focus()}
    >
      <svg viewBox="0 0 24 24" width="21" height="21" aria-hidden>
        <circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" strokeWidth="2.2" />
        <path d="M15.5 15.5L20 20" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
    </button>
  );
}
