// Step-by-step directions after "Start" (owner: phone session). Deterministic: the lines are state.route.steps from
// /api/route, Next/Back only move an index in the store; nothing here calls the agent. Current step big at the bottom,
// pull the sheet up (or "All steps") for the whole list. While walking, App shows only this sheet in the dock.
// With spoken replies on, each step is read out via speak() (/api/speak TTS or the browser voice, no LLM).

import { useEffect, useState } from "react";
import { useTwin, walkSteps } from "../store";
import { speak, stopSpeaking } from "../voice";
import { PhoneSheet } from "./PhoneSheet";
import "./Walk.css";

/** Walking time in whole minutes (1.2 m/s indoors, at least 1). */
export function walkMinutes(lengthM: number): number {
  return Math.max(1, Math.round(lengthM / 72));
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
  useEffect(() => {
    const { voiceOut, speechAvailable } = useTwin.getState();
    if (line && voiceOut) void speak(line, speechAvailable);
  }, [line]);
  useEffect(() => () => stopSpeaking(), []);

  if (step === null || !model || !route?.ok) return null;
  const steps = walkSteps().map(readable);
  const last = step >= steps.length - 1;
  const length = route.length_m !== undefined ? Math.round(route.length_m) : null;
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
            {length !== null && <span className="card-muted"> · {length} m · {minutes} min</span>}
          </span>
          <button className="x" onClick={end} aria-label="End directions">
            ×
          </button>
        </div>
        <div className="walk-now">
          <TurnIcon line={steps[step]} up={rideUp(route.floor_changes, steps, step)} />
          <p aria-live="polite">{steps[step]}</p>
        </div>
        <div className="card-actions">
          <button disabled={step === 0} onClick={() => setWalkStep(step - 1)}>
            Back
          </button>
          <button className="primary" onClick={last ? end : () => setWalkStep(step + 1)}>
            {last ? "Done" : "Next"}
          </button>
        </div>
        {steps.length > 1 && (
          <button className="link walk-toggle" onClick={() => setList(!list)} aria-expanded={list}>
            {list ? "Hide steps" : `All ${steps.length} steps`}
          </button>
        )}
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

/** The server's step lines name rooms as "Office 0.46 [building-F0-S046]"; the id in brackets is not for people. */
function readable(line: string): string {
  return line.replace(/\s*\[[^\]]*\]/g, "");
}
