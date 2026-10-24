// The one input: "Ask or search…". Typing completes the best match inline as grey ghost text (rooms, things,
// stairs/lifts, floors); Enter, → or a tap on the ghost flies there and selects it. Enter on a sentence asks the
// building (the reply shows in the Card). A list of matches only on a laptop, with ↓ or Cmd/Ctrl+K.
// Voice in via the mic (push-to-talk), replies to spoken questions are spoken back (mute toggle).
// Owner: chat/search session, see ARCHITECTURE.md.

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import Fuse from "fuse.js";
import { floorLabel } from "../model/model";
import { prettyType } from "../model/palette";
import { useTwin } from "../store";
import { keepAwake, listen, speak, speechInputProblem, spokenText, stopSpeaking, type Listener } from "../voice";
import { voiceHint } from "./phoneHints";
import "./Omnibox.css";

interface Hit {
  id: string;
  kind: "room" | "thing" | "connector" | "floor";
  title: string;
  subtitle: string;
  ref: string;
  type: string;
  floorId: string;
}

type Row = { kind: "hit"; hit: Hit } | { kind: "ask" };

const KIND_LABEL: Record<Hit["kind"], string> = { room: "Room", thing: "Thing", connector: "Stairs/lift", floor: "Floor" };
const QUESTION_START =
  /^(where|what|which|how|who|why|when|is|are|can|could|would|do|does|did|show|find|take|bring|route|guide|walk|lead|navigate|get|close|open|reopen|block|add|list|count|tell|give|help|i'?m|i am|we|my|please)\b/i;
const VOICE_PREF = "twin.voiceOut";
const MAX_HITS = 6;

// Card session's "Route here → Where are you?" mode; read defensively until the store has it.
interface PickingStore {
  pickingStartFor?: string | null;
  pickStart?: (spaceId: string, floorId: string) => Promise<void> | void;
  cancelPickStart?: () => void;
}
const picking = () => useTwin.getState() as unknown as PickingStore;

const coarsePointer = () => typeof window !== "undefined" && !!window.matchMedia?.("(pointer: coarse)").matches;

const KIND_RANK: Record<Hit["kind"], number> = { room: 0, connector: 1, thing: 2, floor: 3 };

/** The one best completion: a title that starts with the text wins (rooms first, then shorter), else fuse's best. */
function bestCompletion(hits: Hit[], fuse: Fuse<Hit>, query: string): Hit | null {
  const lower = query.toLowerCase();
  let best: Hit | null = null;
  for (const hit of hits) {
    if (!hit.title.toLowerCase().startsWith(lower)) continue;
    if (
      !best ||
      KIND_RANK[hit.kind] < KIND_RANK[best.kind] ||
      (KIND_RANK[hit.kind] === KIND_RANK[best.kind] && hit.title.length < best.title.length)
    )
      best = hit;
  }
  return best ?? fuse.search(query, { limit: 1 })[0]?.item ?? null;
}

function looksLikeQuestion(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.includes("?") || trimmed.split(/\s+/).length > 3 || QUESTION_START.test(trimmed);
}

export function Omnibox() {
  const model = useTwin((s) => s.model);
  const ask = useTwin((s) => s.ask);
  const busy = useTwin((s) => s.chatBusy);
  const chat = useTwin((s) => s.chat);
  const chatAvailable = useTwin((s) => s.chatAvailable);
  const speechAvailable = useTwin((s) => s.speechAvailable);
  const voiceOut = useTwin((s) => s.voiceOut);
  const setVoiceOut = useTwin((s) => s.setVoiceOut);
  const dismissReply = useTwin((s) => s.dismissReply);
  const flyTo = useTwin((s) => s.flyTo);
  const select = useTwin((s) => s.select);
  const focusFloor = useTwin((s) => s.focusFloor);
  const requestCamera = useTwin((s) => s.requestCamera);
  const pickingFor = useTwin((s) => (s as unknown as PickingStore).pickingStartFor ?? null);

  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [listening, setListening] = useState(false);
  const [heard, setHeard] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listenerRef = useRef<Listener | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Sound on by default; remembered per device.
  useEffect(() => {
    let on = true;
    try {
      on = localStorage.getItem(VOICE_PREF) !== "off";
    } catch {
      /* private mode */
    }
    setVoiceOut(on);
  }, [setVoiceOut]);

  // Cmd/Ctrl+K focuses the input from anywhere.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // A tap outside closes the hits and the history.
  useEffect(() => {
    const onDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
        setHistory(false);
      }
    };
    window.addEventListener("pointerdown", onDown);
    return () => window.removeEventListener("pointerdown", onDown);
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 7000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const allHits = useMemo<Hit[]>(() => {
    if (!model) return [];
    const floorName = (id: string) => {
      const floor = model.floorById.get(id);
      return floor ? floorLabel(floor) : "";
    };
    return [
      ...model.floors.map<Hit>((floor) => ({
        id: floor.id,
        kind: "floor",
        title: floorLabel(floor),
        subtitle: `${floor.spaces.length} rooms`,
        ref: floor.id,
        type: "floor level",
        floorId: floor.id,
      })),
      ...model.building.spaces
        .filter((space) => space.name)
        .map<Hit>((space) => ({
          id: space.id,
          kind: model.connectorBySpace.has(space.id) ? "connector" : "room",
          title: space.name,
          subtitle: [prettyType(space.room_type), floorName(space.floor_id)].filter(Boolean).join(" · "),
          ref: [space.ref, space.id].filter(Boolean).join(" "),
          type: `${space.room_type} ${space.type}`.replace(/_/g, " "),
          floorId: space.floor_id,
        })),
      ...model.building.assets.map<Hit>((asset) => ({
        id: asset.id,
        kind: "thing",
        title: asset.name,
        subtitle: [prettyType(asset.type), model.spaceById.get(asset.space_id)?.name, floorName(asset.floor_id)]
          .filter(Boolean)
          .join(" · "),
        ref: asset.id,
        type: `${asset.type} ${asset.category ?? ""}`.replace(/_/g, " "),
        floorId: asset.floor_id,
      })),
    ];
  }, [model]);
  // While picking a start, only rooms and stairs/lifts make sense.
  const hits = useMemo(
    () => (pickingFor ? allHits.filter((hit) => hit.kind === "room" || hit.kind === "connector") : allHits),
    [allHits, pickingFor],
  );

  // Focus the input when the card asks "Where are you?".
  useEffect(() => {
    if (pickingFor) inputRef.current?.focus();
  }, [pickingFor]);

  const fuse = useMemo(
    () =>
      new Fuse(hits, {
        keys: [
          { name: "title", weight: 0.6 },
          { name: "ref", weight: 0.25 },
          { name: "type", weight: 0.15 },
        ],
        threshold: 0.32,
        ignoreLocation: true,
      }),
    [hits],
  );

  const query = text.trim();
  const question = !pickingFor && looksLikeQuestion(query);
  const completion = useMemo(() => (query && !question ? bestCompletion(hits, fuse, query) : null), [hits, fuse, query, question]);
  // Ghost text after the typed text: the rest of the title, or "→ title" when the match is not a prefix.
  const ghost = completion
    ? completion.title.toLowerCase().startsWith(text.toLowerCase())
      ? completion.title.slice(text.length)
      : `  → ${completion.title}`
    : "";
  const rows = useMemo<Row[]>(() => {
    if (!query) return [];
    const found = fuse.search(query, { limit: question ? 3 : MAX_HITS }).map<Row>((result) => ({ kind: "hit", hit: result.item }));
    return question ? [{ kind: "ask" }, ...found] : [...found, { kind: "ask" }];
  }, [fuse, query, question]);

  useEffect(() => setActive(0), [query]);

  const go = (hit: Hit) => {
    setText("");
    setOpen(false);
    inputRef.current?.blur();
    if (picking().pickingStartFor) {
      // "Where are you?": set the position and start the route, no card in between (card session's action).
      void picking().pickStart?.(hit.id, hit.floorId);
      return;
    }
    if (hit.kind === "floor") {
      select(null);
      focusFloor(hit.floorId);
      requestCamera({ kind: "floor", floorId: hit.floorId });
      return;
    }
    const asset = model?.assetById.get(hit.id);
    const connector = model?.connectorBySpace.get(hit.id);
    if (asset) select({ kind: "asset", id: hit.id, floor_id: hit.floorId, space_id: asset.space_id });
    else if (connector) select({ kind: "connector", id: connector.id, floor_id: hit.floorId, space_id: hit.id });
    else select({ kind: "space", id: hit.id, floor_id: hit.floorId });
    flyTo(hit.id);
  };

  const submit = useCallback(
    async (message: string, voice = false) => {
      if (!message.trim() || useTwin.getState().chatBusy) return;
      if (picking().pickingStartFor) {
        setNotice("Type a room name, then pick it.");
        return;
      }
      if (!useTwin.getState().chatAvailable) {
        setNotice("Asking is off: the server has no agent key. Search still works.");
        return;
      }
      setText("");
      setOpen(false);
      setHistory(false);
      stopSpeaking();
      const reply = await ask(message, voice);
      if (reply && voice && useTwin.getState().voiceOut) void speak(reply.reply, useTwin.getState().speechAvailable);
    },
    [ask],
  );

  const pick = (row: Row | undefined) => {
    if (!row) return;
    if (row.kind === "hit") go(row.hit);
    else void submit(query);
  };

  const toggleMic = () => {
    if (listening) {
      listenerRef.current?.stop();
      return;
    }
    const problem = speechInputProblem();
    if (problem) {
      setNotice(problem);
      return;
    }
    stopSpeaking();
    setNotice(null);
    setOpen(false);
    setHeard("");
    setListening(true);
    keepAwake("listening", true);
    listenerRef.current = listen("en-US", {
      onInterim: setHeard,
      onFinal: (said) => void submit(said, true),
      onEnd: (error) => {
        listenerRef.current = null;
        keepAwake("listening", false);
        setListening(false);
        setHeard("");
        if (error) setNotice(voiceHint(error === "unsupported" ? undefined : error));
      },
    });
  };

  useEffect(() => () => listenerRef.current?.cancel(), []);

  const toggleSound = () => {
    const on = !voiceOut;
    if (!on) stopSpeaking();
    setVoiceOut(on);
    try {
      localStorage.setItem(VOICE_PREF, on ? "on" : "off");
    } catch {
      /* private mode */
    }
  };

  const pairs = useMemo(() => {
    const result: { question: string; answer: string; id: number }[] = [];
    chat.forEach((message, index) => {
      if (message.role !== "agent") return;
      const before = chat[index - 1];
      const failed = /^The (agent|request) failed/.test(message.text);
      result.push({
        id: message.id,
        question: before?.role === "user" ? before.text : "",
        answer: failed ? "Something went wrong, please ask again." : spokenText(message.text),
      });
    });
    return result.slice(-5).reverse();
  }, [chat]);

  const showRows = open && rows.length > 0 && !listening && !busy && !coarsePointer();
  const placeholder = listening
    ? "Listening…"
    : pickingFor
      ? "Where are you?"
      : chatAvailable
        ? "Ask or search…"
        : "Search rooms and things…";
  const showGhost = !!ghost && !listening && !showRows;

  // The ghost text sits exactly over the input: copy its font and padding (the phone CSS changes them).
  const [ghostStyle, setGhostStyle] = useState<CSSProperties>({});
  useLayoutEffect(() => {
    const input = inputRef.current;
    if (!showGhost || !input) return;
    const css = getComputedStyle(input);
    setGhostStyle({ font: css.font, letterSpacing: css.letterSpacing, padding: css.padding });
  }, [showGhost]);

  return (
    <div className="omnibox" ref={rootRef}>
      {history && pairs.length > 0 && (
        <ol className="ob-history" aria-label="Earlier replies">
          {pairs.map((pair) => (
            <li key={pair.id}>
              {pair.question && <div className="ob-q">{pair.question}</div>}
              <div className="ob-a">{pair.answer}</div>
            </li>
          ))}
        </ol>
      )}

      {showRows && (
        <ul className="ob-hits" role="listbox" id="ob-hits" aria-label="Results">
          {rows.map((row, index) => (
            <li key={row.kind === "hit" ? row.hit.id : "ask"} role="option" aria-selected={index === active}>
              <button
                type="button"
                className={`ob-row ${index === active ? "active" : ""} ${row.kind === "ask" ? "ob-ask" : ""}`}
                onPointerEnter={() => setActive(index)}
                onClick={() => pick(row)}
                disabled={row.kind === "ask" && !chatAvailable}
              >
                {row.kind === "hit" ? (
                  <>
                    <span className="ob-title">{row.hit.title}</span>
                    <span className="ob-sub">
                      <span className="ob-kind">{KIND_LABEL[row.hit.kind]}</span>
                      {row.hit.subtitle && ` · ${row.hit.subtitle}`}
                    </span>
                  </>
                ) : (
                  <>
                    <span className="ob-title">
                      <AskIcon /> Ask Wanda
                    </span>
                    <span className="ob-sub">{chatAvailable ? `“${query}”` : "Asking is off on this server"}</span>
                  </>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {(busy || listening || notice) && (
        <div className={`ob-status ${notice && !busy && !listening ? "ob-notice" : ""}`} role="status" aria-live="polite">
          {busy ? (
            <>
              <span className="ob-dots" aria-hidden>
                <i />
                <i />
                <i />
              </span>
              Wanda is thinking
            </>
          ) : listening ? (
            <>
              <span className="ob-rec" aria-hidden />
              {heard ? <span className="ob-heard">{heard}</span> : "Listening… tap the mic again to send"}
            </>
          ) : (
            <>
              <span>{notice}</span>
              <button type="button" className="x" aria-label="Dismiss" onClick={() => setNotice(null)}>
                ×
              </button>
            </>
          )}
        </div>
      )}

      <form
        className={`omnibox-input ${listening ? "is-listening" : ""}`}
        onSubmit={(event) => {
          event.preventDefault();
          if (!query) return;
          if (showRows) pick(rows[active] ?? { kind: "ask" });
          else if (completion) go(completion);
          else void submit(query);
        }}
      >
        <div className="ob-field">
          {showGhost && (
            <div className="ob-ghost" aria-hidden style={ghostStyle}>
              <span className="ob-typed">{text}</span>
              <span className="ob-suggest" onPointerDown={(event) => event.preventDefault()} onClick={() => completion && go(completion)}>
                {ghost}
              </span>
            </div>
          )}
          <input
            ref={inputRef}
            value={listening ? heard : text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              const input = event.currentTarget;
              const atEnd = input.selectionStart === input.value.length && input.selectionEnd === input.value.length;
              if ((event.key === "ArrowRight" || event.key === "Tab") && atEnd && completion && !showRows) {
                event.preventDefault();
                go(completion);
              } else if (event.key === "ArrowDown" && rows.length && !coarsePointer()) {
                event.preventDefault();
                if (!open) {
                  setOpen(true);
                  setActive(0);
                } else setActive((index) => (index + 1) % rows.length);
              } else if (event.key === "ArrowUp" && rows.length && showRows) {
                event.preventDefault();
                setActive((index) => (index - 1 + rows.length) % rows.length);
              } else if (event.key === "Escape") {
                if (open) setOpen(false);
                else if (text) setText("");
                else {
                  inputRef.current?.blur();
                  if (picking().pickingStartFor) picking().cancelPickStart?.();
                }
                stopSpeaking();
              }
            }}
            placeholder={placeholder}
            aria-label="Ask or search"
            aria-expanded={showRows}
            aria-controls="ob-hits"
            role="combobox"
            autoComplete="off"
            autoCorrect="off"
            enterKeyHint={question ? "send" : "search"}
            readOnly={listening}
          />
        </div>
        {pairs.length > 1 && (
          <button
            type="button"
            className={`ob-icon ${history ? "on" : ""}`}
            onClick={() => {
              // One card at a time: the history replaces the reply card while it is open.
              if (!history) dismissReply();
              setHistory(!history);
            }}
            aria-label={history ? "Hide earlier replies" : "Show earlier replies"}
            aria-pressed={history}
            title="Earlier replies"
          >
            <HistoryIcon />
          </button>
        )}
        <button
          type="button"
          className={`ob-icon ${voiceOut ? "" : "off"}`}
          onClick={toggleSound}
          aria-label={voiceOut ? "Mute spoken replies" : "Speak replies"}
          aria-pressed={!voiceOut}
          title={voiceOut ? "Spoken replies on" : "Spoken replies off"}
        >
          {voiceOut ? <SpeakerIcon /> : <MutedIcon />}
        </button>
        <button
          type="button"
          className={`ob-mic mic ${listening ? "listening" : ""}`}
          onClick={toggleMic}
          disabled={busy}
          aria-label={listening ? "Stop and send" : "Speak"}
          aria-pressed={listening}
          title={listening ? "Tap to send" : "Tap and speak"}
        >
          <MicIcon />
        </button>
      </form>
    </div>
  );
}

const iconProps = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

function MicIcon() {
  return (
    <svg {...iconProps}>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
    </svg>
  );
}

function SpeakerIcon() {
  return (
    <svg {...iconProps}>
      <path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" />
      <path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" />
    </svg>
  );
}

function MutedIcon() {
  return (
    <svg {...iconProps}>
      <path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" />
      <path d="M16 9.5l5 5M21 9.5l-5 5" />
    </svg>
  );
}

function HistoryIcon() {
  return (
    <svg {...iconProps}>
      <path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4" />
      <path d="M12 8v4l3 2" />
    </svg>
  );
}

function AskIcon() {
  return (
    <svg {...iconProps} width={15} height={15}>
      <path d="M5 18l-1.5 3 4-1.5A8.5 8.5 0 1 0 5 18z" />
    </svg>
  );
}
