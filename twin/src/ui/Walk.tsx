// Step-by-step directions after "Start" (owner: phone session). Deterministic: the lines are state.route.steps from
// /api/route, Next/Back only move an index in the store; nothing here calls the agent. Current step big at the bottom,
// pull the sheet up (or "All steps") for the whole list. While walking, App shows only this sheet in the dock.
// With spoken replies on, each step is read out via speak() (/api/speak TTS or the browser voice, no LLM).
// Auto-Pace (off by default): after a step has been read out, a timer of the expected walking time + 5 s runs;
// "Say" then moves on by itself, "Ask" asks "Are you there?" and waits for Next or a spoken "yes". All local.

import { useCallback, useEffect, useRef, useState } from "react";
import { useTwin, walkSteps } from "../store";
import { listen, speak, speechEnded, speechInputProblem, stopSpeaking, type Listener } from "../voice";
import { PhoneSheet } from "./PhoneSheet";
import "./Walk.css";

/** Walking time in whole minutes (1.2 m/s indoors, at least 1). */
export function walkMinutes(lengthM: number): number {
  return Math.max(1, Math.round(lengthM / 72));
}

/** Metres named in a step line ("Walk about 11 m …"). */
function metresIn(line: string): number {
  return [...line.matchAll(/(\d+(?:\.\d+)?)\s*m\b/g)].reduce((sum, m) => sum + Number(m[1]), 0);
}

/** Auto-Pace wait for a step: walking time at 1.2 m/s (at least 4 s) plus 5 s; stairs/lift lines without metres 12 s. */
export function stepSeconds(line: string): number {
  const metres = metresIn(line);
  return metres > 0 ? Math.max(4, metres / 1.2) + 5 : 12;
}

// Test hook only: ?pace=0.1 runs the Auto-Pace timers ten times faster. The shipped default is 1.
function paceScale(): number {
  const value = Number(new URLSearchParams(window.location.search).get("pace"));
  return value > 0 && value <= 1 ? value : 1;
}

const YES = /\b(yes|yeah|yep|yup|next|okay|ok|go|continue|there|ja|jo|weiter|nächste)\b/i;

type Phase = { kind: "idle" } | { kind: "running"; ms: number; key: number } | { kind: "asking" } | { kind: "arrived" };

/** The Auto-Pace timer for the current step. Restarts on every step change; stops while off, while the step
 * list is open or the page is hidden. Waits for the step to finish being spoken before it starts. */
function useAutoPace(step: number | null, line: string, last: boolean, list: boolean, spoken: React.MutableRefObject<Promise<void>>) {
  const mode = useTwin((s) => s.autoPace);
  const setWalkStep = useTwin((s) => s.setWalkStep);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [hidden, setHidden] = useState(() => document.visibilityState === "hidden");

  useEffect(() => {
    const onChange = () => setHidden(document.visibilityState === "hidden");
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);

  useEffect(() => {
    setPhase({ kind: "idle" });
    if (mode === "off" || step === null || !line || list || hidden) return;
    let cancelled = false;
    let timer = 0;
    const say = (text: string) => {
      const { voiceOut, speechAvailable } = useTwin.getState();
      if (voiceOut) void speak(text, speechAvailable);
    };
    void (async () => {
      await spoken.current;
      // Capped by the text length: some browser voices keep reporting "speaking" after they are done.
      await speechEnded(1500 + line.length * 75);
      if (cancelled) return;
      const ms = stepSeconds(line) * 1000 * paceScale();
      setPhase({ kind: "running", ms, key: Date.now() });
      timer = window.setTimeout(() => {
        if (cancelled) return;
        if (last) {
          setPhase({ kind: "arrived" });
          say("You're there.");
        } else if (mode === "say") {
          setWalkStep(step + 1);
        } else {
          setPhase({ kind: "asking" });
          say("Are you there?");
        }
      }, ms);
    })();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [mode, step, line, last, list, hidden, setWalkStep, spoken]);

  return { mode, phase };
}

type Change = { direction: "up" | "down" }[] | undefined;

/** Up or down for a ride step: the n-th "Take/Use … to …" line is the n-th floor change. */
function rideUp(changes: Change, steps: string[], step: number): boolean {
  const index = steps.slice(0, step).filter(isRide).length;
  return changes?.[index]?.direction !== "down";
}

function isRide(line: string): boolean {
  return /^(Take|Use) .+ to /.test(line);
}

/** The standard maps pictogram for a step: start dot, straight arrow, stairs/lift up or down, arrival pin. */
function TurnIcon({ line, up }: { line: string; up: boolean }) {
  const path = /^Start/.test(line)
    ? <circle cx="12" cy="12" r="5" fill="currentColor" stroke="none" />
    : /arrived/i.test(line)
      ? <path d="M12 21s-6-5.6-6-10a6 6 0 0 1 12 0c0 4.4-6 10-6 10zm0-8a2 2 0 1 0 0-4 2 2 0 0 0 0 4z" fill="currentColor" stroke="none" />
      : isRide(line)
        ? <path d={up ? "M5 19h4v-4h4v-4h4V7M14 7h3v3" : "M5 7h4v4h4v4h4v4M14 19h3v-3"} />
        : <path d="M12 20V5M6 11l6-6 6 6" />;
  return (
    <svg className="walk-icon" viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {path}
    </svg>
  );
}

export function Walk() {
  const model = useTwin((s) => s.model);
  const step = useTwin((s) => s.walkStep);
  const route = useTwin((s) => s.state?.route ?? null);
  const setWalkStep = useTwin((s) => s.setWalkStep);
  const stopWalk = useTwin((s) => s.stopWalk);
  const clearRoute = useTwin((s) => s.clearRoute);
  const [list, setList] = useState(false);
  const walking = step !== null;

  // The route went away (cleared, building changed): stop walking.
  useEffect(() => {
    if (walking && !route?.ok) stopWalk();
  }, [walking, route, stopWalk]);
  useEffect(() => {
    if (!walking) setList(false);
  }, [walking]);
  const line = step !== null ? readable(walkSteps()[step] ?? "") : "";
  const spoken = useRef<Promise<void>>(Promise.resolve());
  useEffect(() => {
    const { voiceOut, speechAvailable } = useTwin.getState();
    spoken.current = line && voiceOut ? speak(line, speechAvailable) : Promise.resolve();
  }, [line, step]);
  useEffect(() => () => stopSpeaking(), []);
  const lastStep = step !== null && step >= walkSteps().length - 1;
  const { mode, phase } = useAutoPace(step, line, lastStep, list, spoken);
  const setAutoPace = useTwin((s) => s.setAutoPace);
  const cycleAuto = () => setAutoPace(mode === "off" ? "say" : mode === "say" ? "ask" : "off");
  const listenYes = useYesListener(phase.kind === "asking", useCallback(() => {
    const now = useTwin.getState().walkStep;
    if (now !== null) useTwin.getState().setWalkStep(now + 1);
  }, []));

  if (step === null || !model || !route?.ok) return null;
  const steps = walkSteps().map(readable);
  const last = step >= steps.length - 1;
  // What is left from the current step on: the metres named in the remaining step lines, scaled to the route length.
  const allMetres = steps.reduce((sum, line) => sum + metresIn(line), 0);
  const leftMetres = steps.slice(step).reduce((sum, line) => sum + metresIn(line), 0);
  const length =
    route.length_m === undefined ? null : Math.round(allMetres > 0 ? (route.length_m * leftMetres) / allMetres : route.length_m * (1 - step / steps.length));
  const minutes = length !== null ? walkMinutes(length) : null;
  const end = () => {
    stopWalk();
    void clearRoute();
  };

  return (
    <PhoneSheet open label="Directions" tall={list} onClose={() => setList(false)} onToggle={() => setList(!list)}>
      <section className="card card-walk" aria-label="Directions">
        <div className="card-head">
          <span className="card-kicker">
            Step {step + 1} of {steps.length}
            {length !== null && <span className="card-muted"> · {length} m left · {minutes} min</span>}
          </span>
          <button className="x" onClick={end} aria-label="End directions">
            ×
          </button>
        </div>
        <div className="walk-now">
          <TurnIcon line={steps[step]} up={rideUp(route.floor_changes, steps, step)} />
          <p aria-live="polite">{steps[step]}</p>
        </div>
        {mode !== "off" && (
          <div className="walk-pace" aria-live="polite">
            {phase.kind === "running" && (
              <div className="walk-pace-bar" aria-hidden>
                <span key={phase.key} style={{ animationDuration: `${phase.ms}ms` }} />
              </div>
            )}
            {phase.kind === "asking" && (
              <p className="walk-ask">
                <span>Are you there?</span>
                <span className="card-muted"> · waiting for you</span>
                {listenYes && (
                  <button className="link walk-say-yes" onClick={listenYes.start} disabled={listenYes.listening}>
                    {listenYes.listening ? "Listening…" : "Say “yes”"}
                  </button>
                )}
              </p>
            )}
            {phase.kind === "arrived" && <p className="walk-ask">You're there.</p>}
          </div>
        )}
        <div className="card-actions">
          <button disabled={step === 0} onClick={() => setWalkStep(step - 1)}>
            Back
          </button>
          <button className="primary" onClick={last ? end : () => setWalkStep(step + 1)}>
            {last ? "Done" : "Next"}
          </button>
        </div>
        <div className="walk-foot">
          {steps.length > 1 && (
            <button className="link walk-toggle" onClick={() => setList(!list)} aria-expanded={list}>
              {list ? "Hide steps" : `All ${steps.length} steps`}
            </button>
          )}
          <button
            className={`walk-auto ${mode}`}
            onClick={cycleAuto}
            aria-label={`Auto-Pace: ${mode === "off" ? "off" : mode === "say" ? "moves on by itself" : "asks first"}. Tap to change.`}
          >
            Auto{mode !== "off" && <b>{mode === "say" ? "Say" : "Ask"}</b>}
          </button>
        </div>
        {list && (
          <ol className="walk-list">
            {steps.map((line, index) => (
              <li key={index}>
                <button className={index === step ? "now" : index < step ? "done" : ""} aria-current={index === step ? "step" : undefined} onClick={() => setWalkStep(index)}>
                  <span className="walk-num">{index + 1}</span>
                  <span>{line}</span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </section>
    </PhoneSheet>
  );
}

/** "Say yes" in Ask mode: a one-shot local listen (no agent); a yes/next/weiter moves to the next step.
 * Null when this browser has no speech input. The listen is dropped when asking ends. */
function useYesListener(asking: boolean, onYes: () => void) {
  const [listening, setListening] = useState(false);
  const listener = useRef<Listener | null>(null);
  useEffect(() => {
    if (!asking) listener.current?.cancel();
  }, [asking]);
  useEffect(() => () => listener.current?.cancel(), []);
  if (speechInputProblem()) return null;
  const start = () => {
    if (listener.current) return;
    stopSpeaking();
    setListening(true);
    const current: Listener = listen("en-US", {
      onFinal: (said) => {
        if (YES.test(said)) onYes();
      },
      onEnd: () => {
        if (listener.current === current) listener.current = null;
        setListening(false);
      },
    });
    listener.current = current;
  };
  return { start, listening };
}

/** The server's step lines name rooms as "Office 0.46 [building-F0-S046]"; the id in brackets is not for people. */
function readable(line: string): string {
  return line.replace(/\s*\[[^\]]*\]/g, "");
}
