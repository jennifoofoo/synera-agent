// The one input: "Ask or search…". Typing completes the best place inline as grey ghost text (see Autocomplete);
// accepting it flies there and selects it. Enter on a sentence asks the building (the reply shows in the Card).
// Voice in via the mic (push-to-talk), replies to spoken questions are spoken back (mute toggle).
// By default only two round buttons show: Chat (opens the input) and Talk (push-to-talk). The input stays mounted
// but invisible, so the header search, Cmd/Ctrl+K and Chat just focus it; focus opens it, an empty blur closes it.
// Owner: chat/search session, see ARCHITECTURE.md.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTwin } from "../store";
import { keepAwake, listen, speak, speechInputProblem, spokenText, stopSpeaking, type Listener } from "../voice";
import { Autocomplete, type PlaceHit } from "./Autocomplete";
import { voiceHint } from "./phoneHints";
import "./Omnibox.css";

const QUESTION_START =
  /^(where|what|which|how|who|why|when|is|are|can|could|would|do|does|did|show|find|take|bring|route|guide|walk|lead|navigate|get|close|open|reopen|block|add|list|count|tell|give|help|i'?m|i am|we|my|please)\b/i;
const VOICE_PREF = "twin.voiceOut";

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

  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [heard, setHeard] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const longPress = useRef<{ timer: number; fired: boolean } | null>(null);
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
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // A tap outside closes the hits and the history.
  useEffect(() => {
    const onDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setHistory(false);
    };
    window.addEventListener("pointerdown", onDown);
    return () => window.removeEventListener("pointerdown", onDown);
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 7000);
    return () => window.clearTimeout(timer);
  }, [notice]);


  const go = (hit: PlaceHit) => {
    setText("");
    inputRef.current?.blur();
    if (hit.kind === "floor") {
      select(null);
      focusFloor(hit.floorId);
      requestCamera({ kind: "floor", floorId: hit.floorId });
      return;
    }
    const connector = model?.connectorBySpace.get(hit.id);
    if (hit.kind === "thing") select({ kind: "asset", id: hit.id, floor_id: hit.floorId, space_id: hit.spaceId ?? undefined });
    else if (connector) select({ kind: "connector", id: connector.id, floor_id: hit.floorId, space_id: hit.id });
    else select({ kind: "space", id: hit.id, floor_id: hit.floorId });
    flyTo(hit.id);
  };

  const submit = useCallback(
    async (message: string, voice = false) => {
      if (!message.trim() || useTwin.getState().chatBusy) return;
      if (!useTwin.getState().chatAvailable) {
        setNotice("Asking is off: the server has no agent key. Search still works.");
        return;
      }
      setText("");
      setHistory(false);
      stopSpeaking();
      inputRef.current?.blur(); // the keyboard goes away, the reply card shows
      const reply = await ask(message, voice);
      if (reply && voice && useTwin.getState().voiceOut) void speak(reply.reply, useTwin.getState().speechAvailable);
    },
    [ask],
  );

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

  // Close the input again when it loses focus with nothing typed (not while listening or busy).
  const collapseIfIdle = () => {
    window.setTimeout(() => {
      const inside = rootRef.current?.contains(document.activeElement);
      if (!inside && !inputRef.current?.value.trim() && !listenerRef.current) setExpanded(false);
    }, 0);
  };

  // Long-press on Talk switches spoken replies on/off (the speaker icon only lives in the open input).
  const talkDown = () => {
    longPress.current = {
      fired: false,
      timer: window.setTimeout(() => {
        if (!longPress.current) return;
        longPress.current.fired = true;
        const on = !useTwin.getState().voiceOut;
        toggleSound();
        setNotice(on ? "Spoken replies on." : "Spoken replies off.");
      }, 600),
    };
  };
  const talkUp = () => {
    if (longPress.current) window.clearTimeout(longPress.current.timer);
  };
  const talkClick = () => {
    const fired = longPress.current?.fired;
    longPress.current = null;
    if (!fired) toggleMic();
  };

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

  const placeholder = listening
    ? "Listening…"
    : chatAvailable
      ? "Ask or search…"
      : "Search rooms and things…";

  return (
    <div className={`omnibox ${expanded ? "expanded" : "collapsed"}`} ref={rootRef}>
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
        onSubmit={(event) => event.preventDefault()}
        aria-hidden={!expanded || undefined}
      >
        <Autocomplete
          inputRef={inputRef}
          value={listening ? heard : text}
          onChange={setText}
          onPick={go}
          onEnter={(message) => void submit(message)}
          noCompletion={looksLikeQuestion}
          listPlacement="above"
          placeholder={placeholder}
          ariaLabel="Ask or search"
          readOnly={listening}
          enterKeyHint={looksLikeQuestion(text) ? "send" : "search"}
          onEscape={stopSpeaking}
          onFocus={() => setExpanded(true)}
          onBlur={collapseIfIdle}
        />
        {pairs.length > 1 && (
          <button
            type="button"
            className={`ob-icon ${history ? "on" : ""}`}
            onPointerDown={(event) => event.preventDefault()}
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
          onPointerDown={(event) => event.preventDefault()}
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
          onPointerDown={(event) => event.preventDefault()}
          onClick={toggleMic}
          disabled={busy}
          aria-label={listening ? "Stop and send" : "Speak"}
          aria-pressed={listening}
          title={listening ? "Tap to send" : "Tap and speak"}
        >
          <MicIcon />
        </button>
      </form>

      {!expanded && (
        <div className="ob-fabs">
          <button
            type="button"
            className="ob-fab"
            aria-label="Chat"
            title="Type to ask or search"
            // Focus inside the tap so iOS opens the keyboard; the focus opens the input.
            onClick={() => inputRef.current?.focus()}
          >
            <ChatIcon />
          </button>
          <button
            type="button"
            className={`ob-fab ob-talk mic ${listening ? "listening" : ""}`}
            aria-label={listening ? "Stop and send" : "Talk"}
            aria-pressed={listening}
            title={listening ? "Tap to send" : "Tap and speak (hold: spoken replies on/off)"}
            disabled={busy}
            onPointerDown={talkDown}
            onPointerUp={talkUp}
            onPointerLeave={talkUp}
            onPointerCancel={talkUp}
            onContextMenu={(event) => event.preventDefault()}
            onClick={talkClick}
          >
            {voiceOut ? <MicIcon /> : <MicMutedIcon />}
          </button>
        </div>
      )}
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

function ChatIcon() {
  return (
    <svg {...iconProps} width={22} height={22}>
      <path d="M5 18l-1.5 3 4-1.5A8.5 8.5 0 1 0 5 18z" />
    </svg>
  );
}

/** Mic with a small slash in the corner: spoken replies are off. */
function MicMutedIcon() {
  return (
    <svg {...iconProps}>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
      <path d="M17 3.5l4 4" strokeWidth={2.2} />
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
