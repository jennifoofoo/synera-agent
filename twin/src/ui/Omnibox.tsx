// The one input: "Ask or search…". Typing completes the best place inline as grey ghost text (see Autocomplete);
// accepting it flies there and selects it. Enter on a sentence asks the building (the reply shows in the Card).
// Voice in via the mic (push-to-talk), replies to spoken questions are spoken back (mute toggle).
// By default only two round buttons show: Chat (opens the input) and Talk (push-to-talk). The input stays mounted
// but invisible, so the header search, Cmd/Ctrl+K and Chat just focus it; focus opens it, an empty blur closes it.
// Owner: chat/search session, see ARCHITECTURE.md.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTwin } from "../store";
import { keepAwake, listen, speak, speechInputProblem, spokenText, stopSpeaking, type Listener } from "../voice";
import { pauseHandsFree } from "../handsFree";
import { Autocomplete, type PlaceHit } from "./Autocomplete";
import { HandsFreeButton, HandsFreeStatus } from "./HandsFree";
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
  const handsFreeOn = useTwin((s) => s.handsFree);
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

  // Stop listening now: the UI leaves the listening state at once; the listener sends what it heard (send) or
  // drops it, releases the mic and then runs onEnd. Safe to call when not listening.
  const stopListening = useCallback((send: boolean) => {
    const listener = listenerRef.current;
    if (!listener) return;
    setListening(false);
    setHeard("");
    if (send) listener.stop();
    else listener.cancel();
  }, []);

  // A toggle: the listener ref, not the `listening` state, says whether a listen is running (no stale closure).
  const toggleMic = () => {
    if (listenerRef.current) {
      stopListening(true);
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
    pauseHandsFree(true); // one recognition at a time
    const listener: Listener = listen("en-US", {
      onInterim: (said) => {
        if (listenerRef.current === listener) setHeard(said);
      },
      onFinal: (said) => void submit(said, true),
      onEnd: (error) => {
        if (listenerRef.current === listener) listenerRef.current = null;
        keepAwake("listening", false);
        pauseHandsFree(false);
        setListening(false);
        setHeard("");
        if (error) setNotice(voiceHint(error === "unsupported" ? undefined : error));
      },
    });
    listenerRef.current = listener;
  };

  // Leaving drops the listen: unmount, the page going to the background, another building, the directions sheet.
  useEffect(() => () => listenerRef.current?.cancel(), []);
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === "hidden") stopListening(false);
    };
    const onPageHide = () => stopListening(false);
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", onPageHide);
    };
  }, [stopListening]);
  useEffect(
    () =>
      useTwin.subscribe((state, before) => {
        const sheetToggled = (state.directions === null) !== (before.directions === null);
        if (sheetToggled || state.buildingKey !== before.buildingKey) stopListening(false);
      }),
    [stopListening],
  );

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
              {heard ? <span className="ob-heard">{heard}</span> : "Listening… tap again to send"}
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

      {!busy && !listening && !notice && <HandsFreeStatus className="ob-hf-status" />}

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
          {/* "Hey Wanda" is switched on in the step sheet; here only while it is on, to see and mute it */}
          {handsFreeOn && <HandsFreeButton className="ob-fab" />}
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
            aria-label={listening ? "Stop and send" : voiceOut ? "Talk" : "Talk (spoken replies off)"}
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
            <MicIcon />
            {!voiceOut && !listening && (
              <span className="ob-badge" aria-hidden>
                <MutedIcon />
              </span>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

const iconProps = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
// Filled pictograms in the standard Material shapes (as in Google Maps), so they read at a glance.
const glyphProps = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "currentColor", "aria-hidden": true };

function MicIcon() {
  return (
    <svg {...glyphProps}>
      <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z" />
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

function SpeakerIcon() {
  return (
    <svg {...glyphProps}>
      <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
    </svg>
  );
}

/** Standard "speaker muted": the speaker crossed by one full diagonal slash. */
function MutedIcon() {
  return (
    <svg {...glyphProps}>
      <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z" />
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
