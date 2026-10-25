// Laptop chat column (docs/specs/chat-sidebar.md): on the planner profile from 1024 px the chat is a fixed column on
// the left, laid out like a chat app. Top to bottom: the building as a calm heading with its floor, a quiet tool row
// (Round, Notes, On map), the conversation (scrolls, full answers, newest at the bottom; empty it greets with Wanda's
// welcome and the suggestion chips), the card slot (route card, place card, walk sheet, notes, campus card) and the
// composer at the bottom (the Wanda orb for voice, the text field, the speaker toggle).
// The map gets the rest: App makes .app a grid and every other child sits in the map column (Sidebar.css).
// Phone (worker) and windows under 1024 px never render this.

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { create } from "zustand";
import { floorLabel } from "../model/model";
import { useTwin } from "../store";
import { withoutAnswerLine } from "../voice";
import { parseChatMarkdown, type Inline } from "../chatMarkdown";
import { NotesButton } from "./Facts";
import { Omnibox } from "./Omnibox";
import { Round } from "./Round";
import { TopBar } from "./TopBar";
import { FairyFigure } from "./FairyFigure";
import { useWelcomeChips } from "./Welcome";
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

/** The column opening or closing changes the canvas width: frame the building again in the new map area, unless the
 * camera was sent somewhere else (a room, a route) since the last Home. */
export function useReframeOnColumn(docked: boolean): void {
  const first = useRef(true);
  useEffect(() => {
    // The first render frames on load (store.openBuilding); the column is already there by then.
    if (first.current) {
      first.current = false;
      return;
    }
    const timer = window.setTimeout(() => {
      const { camera, model, requestCamera } = useTwin.getState();
      if (model && camera.kind === "home") requestCamera({ kind: "home" });
    }, 120); // after the canvas has measured its new size (react-three-fiber observes it)
    return () => window.clearTimeout(timer);
  }, [docked]);
}

/** The left column. `dock` is what used to float at the bottom of the map (card or walk sheet, notes, campus card). */
export function Sidebar({ walking, dock }: { walking: boolean; dock: ReactNode }) {
  const setCollapsed = useSidebar((s) => s.setCollapsed);
  return (
    <aside className="sidebar" aria-label="Chat with the building">
      <header className="sb-head">
        <div className="sb-title">
          <TopBar />
          <FloorLine />
        </div>
        <button type="button" className="sb-toggle" aria-label="Hide chat" aria-expanded title="Hide chat" onClick={() => setCollapsed(true)}>
          <PanelIcon />
        </button>
      </header>
      <div className="sb-tools" role="toolbar" aria-label="Tools">
        <Round />
        <NotesButton />
      </div>
      <ChatLog />
      {/* Cards slot: route, place, walk, round and notes cards sit here, right above the composer. */}
      <div className="sb-dock">{dock}</div>
      <div className="sb-composer">
        <Omnibox walking={walking} docked />
      </div>
    </aside>
  );
}

/** Collapsed: one small button top left brings the column back. */
export function SidebarExpand() {
  const setCollapsed = useSidebar((s) => s.setCollapsed);
  return (
    <button type="button" className="sb-toggle sb-expand" aria-label="Show chat" aria-expanded={false} title="Show chat" onClick={() => setCollapsed(false)}>
      <PanelIcon />
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
  const empty = chat.length === 0 && !busy;
  return (
    <ol className={`sb-log ${empty ? "sb-log-empty" : ""}`} ref={ref} aria-label="Conversation" aria-live="polite">
      {empty && <ColumnWelcome />}
      {chat.map((message) =>
        message.role === "user" ? (
          <li key={message.id} className="sb-msg sb-user">
            {message.text}
          </li>
        ) : (
          <li key={message.id} className="sb-msg sb-agent">
            <div className="sb-text">
              {/^The (agent|request) failed/.test(message.text) ? "Something went wrong, please ask again." : <Markdown text={withoutAnswerLine(message.text)} />}
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

/** The empty conversation: Wanda's welcome (as on the phone's welcome card) and the questions this building answers. */
function ColumnWelcome() {
  const name = useTwin((s) => s.building?.name);
  const chips = useWelcomeChips();
  return (
    <li className="sb-welcome" aria-label="Welcome">
      <FairyFigure className="sb-welcome-fairy" />
      <h2 className="welcome-title">Hi, I'm Wanda.</h2>
      <p className="welcome-sub">What can I help you find in {name ?? "this building"}?</p>
      {chips.length > 0 && (
        <div className="welcome-chips">
          {chips.map((text) => (
            <button key={text} type="button" className="welcome-chip" onClick={() => void useTwin.getState().ask(text)}>
              {text}
            </button>
          ))}
        </div>
      )}
    </li>
  );
}

/** Wanda's reply with its little markdown (bold, italic, lists, line breaks) as React nodes, never as HTML. */
function Markdown({ text }: { text: string }) {
  return (
    <>
      {parseChatMarkdown(text).map((block, index) =>
        block.kind === "p" ? (
          <p key={index}>
            {block.lines.map((line, i) => (
              <span key={i}>
                {i > 0 && <br />}
                <Runs runs={line} />
              </span>
            ))}
          </p>
        ) : block.kind === "ul" ? (
          <ul key={index}>
            {block.items.map((item, i) => (
              <li key={i}>
                <Runs runs={item} />
              </li>
            ))}
          </ul>
        ) : (
          <ol key={index} start={block.start}>
            {block.items.map((item, i) => (
              <li key={i}>
                <Runs runs={item} />
              </li>
            ))}
          </ol>
        ),
      )}
    </>
  );
}

function Runs({ runs }: { runs: Inline[] }) {
  return (
    <>
      {runs.map((run, i) => {
        const text = run.italic ? <em>{run.text}</em> : run.text;
        return run.bold ? <strong key={i}>{text}</strong> : <span key={i}>{text}</span>;
      })}
    </>
  );
}

function PanelIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="M9 4v16" />
    </svg>
  );
}
