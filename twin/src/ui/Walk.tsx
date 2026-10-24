// Step-by-step directions after "Start" (owner: phone session). Deterministic: the lines are state.route.steps from
// /api/route, Next/Back only move an index in the store; nothing here calls the agent. Current step big at the bottom,
// pull the sheet up (or "All steps") for the whole list. While walking, App shows only this sheet in the dock.

import { useEffect, useState } from "react";
import { useTwin, walkSteps } from "../store";
import { PhoneSheet } from "./PhoneSheet";
import "./Walk.css";

const WALK_M_PER_MIN = 72; // 1.2 m/s, indoor walking pace

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

  if (step === null || !model || !route?.ok) return null;
  const steps = walkSteps().map(readable);
  const last = step >= steps.length - 1;
  const length = route.length_m !== undefined ? Math.round(route.length_m) : null;
  const minutes = length !== null ? Math.max(1, Math.round(length / WALK_M_PER_MIN)) : null;
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
        <p className="walk-now" aria-live="polite">
          {steps[step]}
        </p>
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
