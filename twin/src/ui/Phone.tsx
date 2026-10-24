// Phone glue (owner: mobile session). Mounted once in App; renders only on the worker profile.
// - header buttons: Back (one step back) left of the name, Search (focuses the one input) on the right
// - viewport: --vvh/--vvtop follow the visual viewport so the input stays above the iOS keyboard
// - audio unlock on the first tap, screen wake lock while a guide is active

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

/** The header row (Back, name, Search) covers the top of the plan, so the camera must frame below it: topInset is
 * at least the header's bottom edge. A bigger value (the directions sheet) wins; when that sheet closes and resets
 * topInset to 0, this puts the header back. */
function useHeaderInset(worker: boolean, ready: boolean) {
  const topInset = useTwin((s) => s.topInset);
  const setTopInset = useTwin((s) => s.setTopInset);
  useEffect(() => {
    if (!worker || !ready) return;
    const measure = () => {
      const header = document.querySelector<HTMLElement>(".phone-back");
      if (!header) return;
      const bottom = Math.round(header.getBoundingClientRect().bottom + 6);
      if (useTwin.getState().topInset < bottom) setTopInset(bottom);
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [worker, ready, topInset, setTopInset]);
  useEffect(() => () => setTopInset(0), [worker, setTopInset]);
}

export function Phone() {
  const worker = useTwin((s) => s.profile === "worker");
  const guiding = useTwin((s) => !!s.state?.guide?.active);
  const selection = useTwin((s) => s.selection);
  const replyShown = useTwin((s) => s.replyShown);
  const floorMode = useTwin((s) => s.floorMode);
  const model = useTwin((s) => s.model);

  useVisualViewport();
  useDockHeight(worker);
  useHeaderInset(worker, !!model);
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

  // One step back: close the card, then the reply, then leave single-floor, then the home view.
  const back = () => {
    const s = useTwin.getState();
    if (s.selection) s.select(null);
    else if (s.replyShown) s.dismissReply();
    else if (s.floorMode !== "stacked") s.setFloorMode("stacked");
    else if (s.campusHook?.back()) return; // a campus building -> the site
    else s.requestCamera({ kind: "home" });
  };
  const campusBack = useTwin.getState().campusHook?.backLabel() ?? null;
  const backLabel = selection ? "Close" : replyShown ? "Dismiss reply" : floorMode !== "stacked" ? "All floors" : (campusBack ?? "Home view");

  return (
    <>
      <button className="phone-back" onClick={back} aria-label={backLabel}>
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
          <path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
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
    </>
  );
}
