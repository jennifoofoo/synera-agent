// Laptop chat column (docs/specs/chat-sidebar.md): on the planner profile from 1024 px the chat is a fixed column on
// the left. Top to bottom: building and floor, the Omnibox (Wanda orb + input), the whole conversation (scrolls, full
// answers, newest at the bottom), and docked below it the card or the walk sheet, the notes and the campus card.
// The map gets the rest: App makes .app a grid and every other child sits in the map column (Sidebar.css).
// Phone (worker) and windows under 1024 px never render this.

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { create } from "zustand";
import { floorLabel } from "../model/model";
import { useTwin } from "../store";
import { withoutAnswerLine } from "../voice";
import { Omnibox } from "./Omnibox";
import { TopBar } from "./TopBar";
import "./Sidebar.css";

const COLLAPSED_KEY = "twin.sidebarCollapsed";
export const SIDEBAR_MIN_WIDTH = 1024;

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false; // private mode: open by default
  }
}

export const useSidebar = create<{ collapsed: boolean; setCollapsed: (collapsed: boolean) => void }>((set) => ({
  collapsed: readCollapsed(),
  setCollapsed(collapsed) {
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      /* private mode: not remembered */
    }
    set({ collapsed });
  },
}));

/** True while the window is at least `px` wide (follows resizes). */
export function useMinWidth(px: number): boolean {
  const query = `(min-width: ${px}px)`;
  const [match, setMatch] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.(query).matches);
  useEffect(() => {
    const list = window.matchMedia?.(query);
    if (!list) return;
    const onChange = () => setMatch(list.matches);
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);
  return match;
}

/** The left column. `dock` is what used to float at the bottom (card or walk sheet, notes, campus card). */
export function Sidebar({ walking, dock }: { walking: boolean; dock: ReactNode }) {
  const setCollapsed = useSidebar((s) => s.setCollapsed);
  return (
    <aside className="sidebar" aria-label="Chat with the building">
      <div className="sb-head">
        <TopBar />
        <button
          type="button"
          className="sb-toggle"
          aria-label="Hide chat"
          aria-expanded
          title="Hide chat"
          onClick={() => setCollapsed(true)}
        >
          <ChevronIcon left />
        </button>
      </div>
      <FloorLine />
      <Omnibox walking={walking} docked />
      <ChatLog />
      <div className="sb-dock">{dock}</div>
    </aside>
  );
}

/** Collapsed: one small button top left brings the column back. */
export function SidebarExpand() {
  const setCollapsed = useSidebar((s) => s.setCollapsed);
  return (
    <button type="button" className="sb-toggle sb-expand" aria-label="Show chat" aria-expanded={false} title="Show chat" onClick={() => setCollapsed(false)}>
      <ChevronIcon />
    </button>
  );
}

function FloorLine() {
  const model = useTwin((s) => s.model);
  const floorId = useTwin((s) => s.focusedFloorId);
  const floor = floorId ? model?.floorById.get(floorId) : undefined;
  if (!floor) return null;
  return <div className="sb-floor">{floorLabel(floor)}</div>;
}

/** The whole conversation, oldest first, complete answers. Typed and spoken questions alike (both go through ask). */
function ChatLog() {
  const chat = useTwin((s) => s.chat);
  const busy = useTwin((s) => s.chatBusy);
  const ref = useRef<HTMLOListElement>(null);
  useLayoutEffect(() => {
    const list = ref.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [chat, busy]);
  return (
    <ol className="sb-log" ref={ref} aria-label="Conversation" aria-live="polite">
      {chat.length === 0 && !busy && <li className="sb-empty">Ask Wanda anything about this building, or tap the orb and talk.</li>}
      {chat.map((message) =>
        message.role === "user" ? (
          <li key={message.id} className="sb-msg sb-user">
            {message.text}
          </li>
        ) : (
          <li key={message.id} className="sb-msg sb-agent">
            <div className="sb-text">
              {/^The (agent|request) failed/.test(message.text) ? "Something went wrong, please ask again." : withoutAnswerLine(message.text)}
            </div>
            {message.note && <div className="sb-note">{message.note}</div>}
          </li>
        ),
      )}
      {busy && (
        <li className="sb-msg sb-agent sb-thinking" aria-label="Wanda is thinking">
          <span className="ob-dots" aria-hidden>
            <i />
            <i />
            <i />
          </span>
        </li>
      )}
    </ol>
  );
}

function ChevronIcon({ left = false }: { left?: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="M9 4v16" />
      <path d={left ? "M15.5 10l-2 2 2 2" : "M13.5 10l2 2-2 2"} />
    </svg>
  );
}
