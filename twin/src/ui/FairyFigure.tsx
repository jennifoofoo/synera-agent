import { useId } from "react";
import "./FairyFigure.css";

const WING_UP = "M25 23C27 15 33 7.5 40.5 4.8c4.4-1.6 5.8 2.4 3 6.4C39.8 16.6 32 21.4 25 24z";
const WING_DOWN = "M25 26c5.8-.2 11.4 2.4 13.4 6.4 1.4 3-1.2 4.8-4 3C31 33.6 27.6 29.6 25 26z";
const BODY = "M24 19c2 0 2.7 1.8 2.5 4-.3 4.6 1.9 11.4 1.3 16.4-.5 4-2.2 7.6-3.8 11.6-1.6-4-3.3-7.6-3.8-11.6-.6-5 1.6-11.8 1.3-16.4-.2-2.2.5-4 2.5-4z";
/* a four-point sparkle around (0, 0); placed by a wrapping <g>, since the twinkle animation owns its transform */
/* a four-point sparkle around (0, 0); placed by a wrapping <g>, since the twinkle animation owns its transform */
const STAR = "M0-2.2l.6 1.6 1.6.6-1.6.6-.6 1.6-.6-1.6-1.6-.6 1.6-.6z";

/** Wanda as a small fairy figure (welcome card, chat sidebar): a slender glowing light body with a soft glow for a
 * head, two pairs of translucent wings that flutter from the body, and a short trail of sparkles that twinkle.
 * Decorative only (aria-hidden). Size via `--fairy-h` (default 64 px, width is 3/4 of it). Self-contained: tokens
 * only, motion is transform and opacity only, nothing runs with prefers-reduced-motion. */
export function FairyFigure({ className }: { className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg className={className ? `ff ${className}` : "ff"} viewBox="0 0 48 64" aria-hidden focusable="false">
      <defs>
        <radialGradient id={`${id}-halo`} cx="24" cy="26" r="22" gradientUnits="userSpaceOnUse">
          <stop offset="0" className="ff-stop-signal ff-stop-faint" />
          <stop offset="1" className="ff-stop-signal ff-stop-clear" />
        </radialGradient>
        <radialGradient id={`${id}-body`} cx="24" cy="23" r="24" gradientUnits="userSpaceOnUse">
          <stop offset="0" className="ff-stop-ink" />
          <stop offset="0.32" className="ff-stop-signal" />
          <stop offset="1" className="ff-stop-dark" />
        </radialGradient>
        <radialGradient id={`${id}-glow`}>
          <stop offset="0" className="ff-stop-signal ff-stop-soft" />
          <stop offset="1" className="ff-stop-signal ff-stop-clear" />
        </radialGradient>
        <radialGradient id={`${id}-head`} cx="45%" cy="62%" r="70%">
          <stop offset="0" className="ff-stop-ink" />
          <stop offset="0.55" className="ff-stop-signal" />
          <stop offset="1" className="ff-stop-dark" />
        </radialGradient>
      </defs>
      <circle className="ff-halo" cx="24" cy="26" r="22" fill={`url(#${id}-halo)`} />
      <g className="ff-float">
        {[false, true].map((left) => (
          <g key={left ? "l" : "r"} transform={left ? "matrix(-1 0 0 1 48 0)" : undefined}>
            <path className="ff-wing ff-wing-up" d={WING_UP} />
            <path className="ff-wing ff-wing-down" d={WING_DOWN} />
          </g>
        ))}
        <path className="ff-body" d={BODY} fill={`url(#${id}-body)`} />
        <circle className="ff-head-glow" cx="24" cy="14.5" r="6.5" fill={`url(#${id}-glow)`} />
        <circle className="ff-head" cx="24" cy="14.6" r="2.9" fill={`url(#${id}-head)`} />
        <g className="ff-trail">
          <g transform="translate(21 55.5)">
            <path className="ff-spark ff-s1" d={STAR} />
          </g>
          <circle className="ff-spark ff-s2" cx="26" cy="57" r="0.9" />
          <circle className="ff-spark ff-s3" cx="17.5" cy="59.5" r="0.8" />
          <g transform="translate(23.5 62) scale(0.7)">
            <path className="ff-spark ff-s4" d={STAR} />
          </g>
        </g>
      </g>
    </svg>
  );
}
