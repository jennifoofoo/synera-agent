// Hands-free toggle and status (owner: hands-free session). The same button sits next to the omnibox buttons and in
// the step sheet; one tap switches "Hey Wanda" listening on or off. The engine is handsFree.ts.

import { useTwin } from "../store";
import { primeEarcon } from "../voice";
import "./HandsFree.css";

export function HandsFreeButton({ className = "" }: { className?: string }) {
  const on = useTwin((s) => s.handsFree);
  const status = useTwin((s) => s.handsFreeStatus);
  const setHandsFree = useTwin((s) => s.setHandsFree);
  const toggle = () => {
    if (!on) primeEarcon(); // inside the tap, so the chime may play later
    setHandsFree(!on);
  };
  return (
    <button
      type="button"
      className={`hf-btn ${on ? `on ${status}` : ""} ${className}`}
      onPointerDown={(event) => event.preventDefault()}
      onClick={toggle}
      aria-pressed={on}
      aria-label={on ? "Hands-free on. Tap to mute." : "Hands-free: say “Hey Wanda”"}
      title={on ? "Hands-free on: say “Hey Wanda”. Tap to mute." : "Hands-free: say “Hey Wanda”"}
    >
      <WavesIcon />
    </button>
  );
}

/** One line: what hands-free is doing now. Null when it is off and has nothing to say. */
export function HandsFreeStatus({ className = "" }: { className?: string }) {
  const on = useTwin((s) => s.handsFree);
  const status = useTwin((s) => s.handsFreeStatus);
  const heard = useTwin((s) => s.handsFreeHeard);
  const notice = useTwin((s) => s.handsFreeNotice);
  if (!on && !notice) return null;
  return (
    <div className={`hf-status ${on ? status : "notice"} ${className}`} role="status" aria-live="polite">
      {!on ? (
        <span>{notice}</span>
      ) : status === "thinking" ? (
        <>
          <span className="hf-dots" aria-hidden>
            <i />
            <i />
            <i />
          </span>
          <span className="hf-text">Wanda is thinking</span>
        </>
      ) : status === "heard" ? (
        <>
          <span className="hf-dot live" aria-hidden />
          <span className="hf-text strong">{heard || "Yes?"}</span>
        </>
      ) : (
        <>
          <span className="hf-dot" aria-hidden />
          <span className="hf-text">Say “Hey Wanda”</span>
        </>
      )}
    </div>
  );
}

/** A microphone with sound waves on both sides. */
function WavesIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <path fill="currentColor" d="M12 14.5c1.4 0 2.5-1.1 2.5-2.5V6c0-1.4-1.1-2.5-2.5-2.5S9.5 4.6 9.5 6v6c0 1.4 1.1 2.5 2.5 2.5z" />
      <path fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" d="M7 11.5a5 5 0 0 0 10 0M12 16.5v3.5M4.5 8.5v5M19.5 8.5v5M2 10v2M22 10v2" />
    </svg>
  );
}
