// Step-by-step directions after "Start" (owner: phone session). Deterministic: the lines are state.route.steps from
// /api/route, Next/Back only move an index in the store; nothing here calls the agent. Current step big at the bottom,
// pull the sheet up (or "All steps") for the whole list. While walking, App shows only this sheet in the dock.
// With spoken replies on, each step is read out via speak() (/api/speak TTS or the browser voice, no LLM).

import { useEffect, useState } from "react";
import { useTwin, walkSteps } from "../store";
import { speak, stopSpeaking } from "../voice";
import { metresLeft, readable, walkMinutes } from "../walkInfo";
import { acceptWalkWithMeHint, declineWalkWithMeHint, honestLine, toggleWalkWithMe, useWalkMotion, walkWithMeAvailable } from "../walkWithMe";
import { HandsFreeButton, HandsFreeStatus } from "./HandsFree";
import { PhoneSheet } from "./PhoneSheet";
import { RoundBar } from "./Round";
import { inRound, roundDone } from "../round/round";
import "./Walk.css";

export { walkMinutes };

type Change = { direction: "up" | "down" }[] | undefined;

/** Up or down for a ride step: the n-th "Take/Use … to …" line is the n-th floor change. */
export function rideUp(changes: Change, steps: string[], step: number): boolean {
  const index = steps.slice(0, step).filter(isRide).length;
  return changes?.[index]?.direction !== "down";
}

function isRide(line: string): boolean {
  return /^(Take|Use) .+ to /.test(line);
}

/** The standard maps pictogram for a step: start dot, straight arrow, stairs/lift up or down, arrival pin. */
export function TurnIcon({ line, up }: { line: string; up: boolean }) {
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
  const motionOn = useWalkMotion((s) => s.on);
  const estimate = useWalkMotion((s) => s.estimate);
  const motionNotice = useWalkMotion((s) => s.notice);
  const motionAnswered = useWalkMotion((s) => s.answered);
  const line = step !== null ? honestLine(readable(walkSteps()[step] ?? "")) : "";
  const repeat = useTwin((s) => s.walkRepeat); // "repeat" said or typed while walking
  useEffect(() => {
    const { voiceOut, handsFree, speechAvailable } = useTwin.getState();
    if (line && (voiceOut || handsFree)) void speak(line, speechAvailable);
  }, [line, step, repeat]);
  useEffect(() => () => stopSpeaking(), []);
  // Esc ends the route (guide and line in one go), unless the key belongs to a text field.
  useEffect(() => {
    if (!walking) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      useTwin.getState().stopWalk();
      void useTwin.getState().clearRoute();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [walking]);

  if (step === null || !model || !route?.ok) return null;
  const steps = walkSteps().map(readable).map(honestLine);
  const last = step >= steps.length - 1;
  // What is left from the current step on: the metres named in the remaining step lines, scaled to the route length.
  // Walk with me on: the module's estimate (walking metres only), shown as "about".
  const length = estimate ? Math.round(estimate.distanceLeftM) : metresLeft(steps, step, route.length_m);
  const minutes = length !== null ? walkMinutes(length) : null;
  const end = () => {
    stopWalk();
    void clearRoute();
  };

  return (
    <PhoneSheet open label="Directions" tall={list} onClose={() => setList(false)} onToggle={() => setList(!list)}>
      <section className="card card-walk" aria-label="Directions">
        <RoundBar />
        <div className="card-head">
          <span className="card-kicker">
            Step {step + 1} of {steps.length}
            {length !== null && (
              <span className="card-muted">
                {" "}
                · {estimate ? "about " : ""}
                <span className="walk-left">{length}</span> m left · {minutes} min
              </span>
            )}
          </span>
          <HandsFreeButton />
          {/* One clear way out: ends the guide and clears the route (Esc does the same). */}
          <button className="walk-end" onClick={end} title="End the route (Esc)">
            End route
          </button>
        </div>
        <div className="walk-now">
          <TurnIcon line={steps[step]} up={rideUp(route.floor_changes, steps, step)} />
          <p aria-live="polite">{steps[step]}</p>
        </div>
        <HandsFreeStatus />
        {/* Asked once, at the start of the guide, on phones that have the sensors; the answer is remembered. */}
        {step === 0 && !motionOn && !motionAnswered && walkWithMeAvailable() && (
          <div className="walk-hint" role="group" aria-label="Walk with me hint">
            <p>Walk with me? I'll move along as you walk.</p>
            <div className="walk-hint-actions">
              <button className="link" onClick={declineWalkWithMeHint}>
                Not now
              </button>
              <button className="primary" onClick={() => void acceptWalkWithMeHint()}>
                Turn on
              </button>
            </div>
          </div>
        )}
        <div className="card-actions">
          <button disabled={step === 0} onClick={() => setWalkStep(step - 1)}>
            Back
          </button>
          {/* Walk with me following: Next is the fallback (stairs, no motion, noisy halls), so it is a normal button;
              waiting at stairs/lift (or motion off) it is the main action again. Same 44 px tap target.
              In an inspection round the last step's Done moves on to the next stop. */}
          <button className={estimate && motionOn && !estimate.atConnector && !last ? "walk-next" : "walk-next primary"} onClick={last ? (inRound() ? () => void roundDone() : end) : () => setWalkStep(step + 1)}>
            {last ? "Done" : "Next"}
          </button>
        </div>
        {/* One quiet row under the buttons: the Walk with me switch (counts steps, moves an estimated dot along the
            route; off by default) and the list toggle. */}
        <div className="walk-foot">
          <label className="walk-motion-switch">
            <input type="checkbox" role="switch" checked={motionOn} onChange={() => void toggleWalkWithMe()} aria-label="Walk with me" />
            Walk with me
          </label>
          {steps.length > 1 && (
            <button className="link walk-toggle" onClick={() => setList(!list)} aria-expanded={list}>
              {list ? "Hide steps" : `All ${steps.length} steps`}
            </button>
          )}
        </div>
        {(motionNotice || estimate?.atConnector || estimate?.offRoute) && (
          <p className="walk-motion-note" role="status" aria-live="polite">
            {estimate?.atConnector ? "Waiting here. Tap Next once you are through." : estimate?.offRoute ? "Looks like you turned around?" : motionNotice}
          </p>
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
