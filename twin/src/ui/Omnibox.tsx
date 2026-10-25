// The one input: "Ask or search…". Typing completes the best place inline as grey ghost text (see Autocomplete);
// accepting it flies there and selects it. Enter on a sentence asks the building (the reply shows in the Card).
// Voice in via the mic (push-to-talk), replies to spoken questions are spoken back (mute toggle).
// By default one bottom bar shows: the Wanda orb, which is the Talk button (push-to-talk), a one-line caption (what
// Wanda hears, thinks or says) and Ask (opens the input). The orb is the one voice control: Stop while Wanda speaks,
// Mute / Unmute Wanda (hands-free) while walking, Talk otherwise. The input stays mounted but invisible, so the
// header search, Cmd/Ctrl+K, the caption and Ask just focus it; focus opens it, an empty blur or Escape closes it.
// Owner: chat/search session, see ARCHITECTURE.md.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { setHandsFreeMuted, useTwin } from "../store";
import { isSpeaking, keepAwake, listen, sharedAudio, speak, speechInputProblem, spokenText, stopSpeaking, withoutIds, type Listener } from "../voice";
import { startAudioElementLevel, startMicLevel } from "../audioLevel";
import { cancelFollowUp, followUpAfterSpeech, imHere, pauseHandsFree, setFollowUpPref } from "../handsFree";
import { parseWake } from "../wake";
import { Autocomplete, type PlaceHit } from "./Autocomplete";
import { HandsFreeStatus } from "./HandsFree";
import { voiceHint } from "./phoneHints";
import "./Omnibox.css";
import { WandaFairy } from "./WandaFairy";

const QUESTION_START =
  /^(where|what|which|how|who|why|when|is|are|can|could|would|do|does|did|show|find|take|bring|route|guide|walk|lead|navigate|get|close|open|reopen|block|add|list|count|tell|give|help|i'?m|i am|we|my|please)\b/i;
const VOICE_PREF = "twin.voiceOut";
/** How long the last reply stays in the caption after Wanda has finished speaking. */
const REPLY_LINGER_MS = 6000;
/** Shown when the input opens on an empty chat: the usual first questions, sent as if typed. */
const SUGGESTIONS = [
  { label: "Nearest toilet", message: "Where is the nearest toilet?" },
  { label: "Way out", message: "What is the nearest way out?" },
  { label: "Coffee", message: "Where can I get a coffee?" },
];

function looksLikeQuestion(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.includes("?") || trimmed.split(/\s+/).length > 3 || QUESTION_START.test(trimmed);
}

/** `docked`: the laptop chat column (Sidebar.tsx): the Wanda bar and the input both stay visible. */
export function Omnibox({ walking = false, docked = false }: { walking?: boolean; docked?: boolean }) {
  const model = useTwin((s) => s.model);
  const ask = useTwin((s) => s.ask);
  const busy = useTwin((s) => s.chatBusy);
  const handsFreeOn = useTwin((s) => s.handsFree);
  const followUp = useTwin((s) => s.followUp);
  const followUpOpen = useTwin((s) => s.followUpOpen);
  const followUpHeard = useTwin((s) => s.followUpHeard);
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
  const handsFreeStatus = useTwin((s) => s.handsFreeStatus);
  const handsFreeHeard = useTwin((s) => s.handsFreeHeard);

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
  const talkRef = useRef<HTMLButtonElement>(null);
  const micRef = useRef<HTMLButtonElement>(null);
  const [speaking, setSpeaking] = useState(false);
  const [lingering, setLingering] = useState(false);

  const setLevel = useCallback((level: number) => {
    const value = level.toFixed(3);
    talkRef.current?.style.setProperty("--wanda-level", value);
    micRef.current?.style.setProperty("--wanda-level", value);
  }, []);

  // Listening: the ring follows the microphone. Not on iOS, where a second mic stream can cut the recognition.
  useEffect(() => {
    if (!listening) return;
    const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    const stop = ios ? () => {} : startMicLevel(setLevel);
    return () => {
      stop();
      setLevel(0);
    };
  }, [listening, setLevel]);

  // Speaking: watch the voice (shared audio element or browser voice); 100 ms is plenty for a state flag.
  useEffect(() => {
    const timer = window.setInterval(() => {
      const now = !listening && isSpeaking();
      setSpeaking((was) => (was === now ? was : now));
    }, 100);
    return () => window.clearInterval(timer);
  }, [listening]);

  // After speaking the reply stays in the caption for a moment, then the bar is back to idle.
  useEffect(() => {
    if (speaking) {
      setLingering(true);
      return;
    }
    const timer = window.setTimeout(() => setLingering(false), REPLY_LINGER_MS);
    return () => window.clearTimeout(timer);
  }, [speaking]);

  // While spoken: the ring follows the audio, or a gentle sine breathing (1.6 s) when it cannot be measured.
  useEffect(() => {
    if (!speaking) return;
    let measured = false;
    const audio = sharedAudio();
    const stopAudio = audio.paused
      ? () => {}
      : startAudioElementLevel(audio, (level) => {
          measured = true;
          setLevel(level);
        });
    const started = performance.now();
    const breathe = window.setInterval(() => {
      if (measured) return;
      setLevel(0.25 + 0.25 * Math.sin(((performance.now() - started) / 1600) * 2 * Math.PI));
    }, 50);
    return () => {
      stopAudio();
      window.clearInterval(breathe);
      setLevel(0);
    };
  }, [speaking, setLevel]);

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
      if (!useTwin.getState().chatAvailable && useTwin.getState().walkStep === null) {
        setNotice("Asking is off: the server has no agent key. Search still works.");
        return;
      }
      setText("");
      setHistory(false);
      cancelFollowUp();
      stopSpeaking();
      inputRef.current?.blur(); // the keyboard goes away, the reply card shows
      const reply = await ask(message, voice);
      if (reply && voice && useTwin.getState().voiceOut) void speak(reply.reply, useTwin.getState().speechAvailable);
      if (voice) followUpAfterSpeech(); // the mic opens again for a few seconds once Wanda has finished speaking
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
      onFinal: (said) => {
        // "Hey Wanda, where is the toilet" sends the question only; "Hey Wanda" alone gets "I'm here." and a listen.
        const wake = parseWake(said);
        if (wake && !wake.rest) imHere();
        else void submit(wake ? wake.rest : said, true);
      },
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

  // Stop (the red button): drop what is being heard, stop the voice and do not reopen the mic afterwards.
  const stopAll = () => {
    stopListening(false);
    cancelFollowUp();
    stopSpeaking();
    setLingering(false);
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
    if (fired) return;
    // One voice control: while Wanda speaks it stops her; while walking it mutes or unmutes hands-free ("Hey Wanda"
    // is on by itself during a walk, and nothing else offers a mute); otherwise it is Talk (tap again to send).
    if (!listenerRef.current && speaking) {
      stopAll();
      return;
    }
    if (walking && !listenerRef.current) {
      setHandsFreeMuted(handsFreeOn); // remembered for the rest of the walk
      useTwin.getState().setHandsFree(!handsFreeOn);
      return;
    }
    if (followUpOpen && !handsFreeOn) cancelFollowUp(); // one recognition at a time
    toggleMic();
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

  const lastReply = useMemo(() => {
    for (let index = chat.length - 1; index >= 0; index--) {
      const message = chat[index];
      if (message.role !== "agent") continue;
      return /^The (agent|request) failed/.test(message.text) ? "Something went wrong, please ask again." : spokenText(message.text);
    }
    return "";
  }, [chat]);

  // The bar's state, most urgent first: hearing, thinking, speaking, the reply lingering, guiding, idle.
  const hfHeard = handsFreeOn && handsFreeStatus === "heard";
  const followUpListening = followUpOpen && !handsFreeOn;
  const hearing = listening || hfHeard || followUpListening;
  let mode: "listening" | "thinking" | "speaking" | "reply" | "idle" = "idle";
  let caption: string;
  if (hearing) {
    mode = "listening";
    caption = listening ? heard || "Listening…" : hfHeard ? handsFreeHeard || "Yes?" : followUpHeard || "Listening… ask your next question";
  } else if (busy) {
    mode = "thinking";
    caption = "Wanda is thinking…";
  } else if (speaking && lastReply) {
    mode = "speaking";
    caption = lastReply;
  } else if (lingering && lastReply) {
    mode = "reply";
    caption = lastReply;
  } else if (walking) {
    // The step itself is the big line of the walk sheet (and the map pill): the bar stays quiet.
    caption = "";
  } else if (!chatAvailable && !walking) {
    caption = "Search rooms and things";
  } else {
    caption = handsFreeOn ? "Ask or say “Hey Wanda”" : "Say “Wanda” or tap the mic";
  }
  const stops = speaking && !listening;
  const orbLabel = listening ? "Stop and send" : stops ? "Stop" : walking ? (handsFreeOn ? "Mute Wanda" : "Unmute Wanda") : voiceOut ? "Talk" : "Talk (spoken replies off)";
  const orbTitle = listening ? "Tap to send" : stops ? "Tap to stop" : walking ? (handsFreeOn ? "Tap to mute “Hey Wanda”" : "Tap so Wanda listens again") : "Tap and speak (hold: spoken replies on/off)";
  // While walking the bar only says that Wanda listens or speaks, never the step or the reply (the sheet has them).
  if (walking) caption = mode === "listening" ? "Listening…" : mode === "speaking" ? "Speaking…" : "";

  const placeholder = listening
    ? "Listening…"
    : chatAvailable
      ? "Ask or search…"
      : "Search rooms and things…";

  return (
    <div className={`omnibox ${expanded ? "expanded" : "collapsed"}${docked ? " docked" : ""}`} ref={rootRef}>
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

      {(notice || (expanded && (busy || listening))) && (
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

      {expanded && !walking && chatAvailable && chat.length === 0 && !text.trim() && !listening && !busy && (
        <div className="ob-chips" role="group" aria-label="Suggestions">
          {SUGGESTIONS.map((chip) => (
            <button
              key={chip.label}
              type="button"
              className="ob-chip"
              onPointerDown={(event) => event.preventDefault()} // keep the input open
              onClick={() => void submit(chip.message)}
            >
              {chip.label}
            </button>
          ))}
        </div>
      )}

      {expanded && followUpOpen && !handsFreeOn && !busy && !listening && !notice && (
        <div className="ob-status ob-followup" role="status" aria-live="polite">
          <span className="ob-rec" aria-hidden />
          {followUpHeard ? <span className="ob-heard">{followUpHeard}</span> : "Listening… ask your next question"}
          <button type="button" className="x" aria-label="Stop listening" onClick={cancelFollowUp}>
            ×
          </button>
        </div>
      )}

      {/* While walking, the step sheet has the hands-free button and line: shown once, never twice. */}
      {/* Collapsed, the bar's caption shows what hands-free hears; the pill stays for its notices (when it is off). */}
      {!walking && !busy && !listening && !notice && (expanded || !handsFreeOn) && <HandsFreeStatus className="ob-hf-status" />}

      {!walking && (
      <form
        className={`omnibox-input ${listening ? "is-listening" : ""}`}
        onSubmit={(event) => event.preventDefault()}
        aria-hidden={(!expanded && !docked) || undefined}
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
          onEscape={() => {
            stopSpeaking();
            if (!inputRef.current?.value.trim()) inputRef.current?.blur(); // Escape on an empty input closes it
          }}
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
          className={`ob-icon ob-followup-toggle ${followUp ? "" : "off"}`}
          onPointerDown={(event) => event.preventDefault()}
          onClick={() => {
            setFollowUpPref(!followUp);
            setNotice(followUp ? "Follow-up listening off." : "Follow-up listening on: after a spoken reply, just keep talking.");
          }}
          aria-label={followUp ? "Follow-up listening on. Tap to turn off." : "Follow-up listening off. Tap to turn on."}
          aria-pressed={followUp}
          title={followUp ? "Follow-up listening on" : "Follow-up listening off"}
        >
          <FollowUpIcon />
        </button>
        <button
          type="button"
          ref={micRef}
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
        <button
          type="button"
          className="ob-icon ob-close"
          onPointerDown={(event) => event.preventDefault()}
          onClick={() => {
            setText("");
            setHistory(false);
            inputRef.current?.blur();
            setExpanded(false);
          }}
          aria-label="Close"
          title="Close (Esc)"
        >
          <CloseIcon />
        </button>
      </form>
      )}

      {(!expanded || walking || docked) && (
        <div className={`wanda-bar ob-fabs ${mode}`}>
          {/* The orb is the mic: one voice button, voice first. While walking it stays: "next", "back", "repeat",
              "stop" by voice (see store.ask). */}
          <button
            type="button"
            ref={talkRef}
            className={`wanda-orb ${mode} wb-orb ob-talk mic ${listening ? "listening" : ""} ${speaking ? "speaking" : ""} ${walking && !handsFreeOn ? "muted" : ""}`}
            aria-label={orbLabel}
            aria-pressed={walking && !listening && !stops ? !handsFreeOn : listening}
            title={orbTitle}
            disabled={busy}
            onPointerDown={talkDown}
            onPointerUp={talkUp}
            onPointerLeave={talkUp}
            onPointerCancel={talkUp}
            onContextMenu={(event) => event.preventDefault()}
            onClick={talkClick}
          >
            <WandaFairy mic />
            {(!voiceOut || (walking && !handsFreeOn)) && !listening && (
              <span className="ob-badge" aria-hidden>
                <MutedIcon />
              </span>
            )}
          </button>
          <div
            className="wb-caption"
            role="status"
            aria-live="polite"
            title={walking ? undefined : "Type to ask or search (Ctrl+K)"}
            // Focus inside the tap so iOS opens the keyboard; the focus opens the input.
            onClick={walking ? undefined : () => inputRef.current?.focus()}
          >
            {mode === "speaking" && !walking && <span className="wb-kicker">Speaking · </span>}
            <span className="wb-text">{withoutIds(caption)}</span>
          </div>
          {!walking && (
            <button
              type="button"
              className="wb-btn wb-ask"
              aria-label="Ask"
              title="Type to ask or search (Ctrl+K)"
              onClick={() => inputRef.current?.focus()}
            >
              <KeyboardIcon />
            </button>
          )}
          {/* One voice entry point: no separate stop or hands-free button here. "Hey Wanda" is switched on with the
              walk (and the wake word); the step sheet has its own toggle. */}
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

function KeyboardIcon() {
  return (
    <svg {...iconProps}>
      <rect x="2.5" y="6" width="19" height="12" rx="2.5" />
      <path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M7.5 14h9" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg {...iconProps}>
      <path d="M6 6l12 12M18 6L6 18" />
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

/** A speech bubble with a return arrow: keep talking after the reply. */
function FollowUpIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden>
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4 5.5h16v10H10l-4 3.5v-3.5H4zM15.5 9.5a3 3 0 1 1-1-2.2M15.6 6.2v1.6h-1.6"
      />
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
