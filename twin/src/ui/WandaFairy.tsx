import { useId } from "react";

const MIC_PATH =
  "M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z";

/** Wanda as a small fairy light inside the orb: a soft halo, two pairs of wings (one pair left, one right, flapping
 * by scaleX from the core), the glowing core with the white mic on it (only when `mic`: the orb is a button; the welcome card greets without it), and three sparks that
 * only show while thinking. The state comes from the orb's classes (Omnibox.css); only inner parts animate. */
export function WandaFairy({ size, mic = false, state }: { size?: number; mic?: boolean; state?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg className={state ? `wf wf-${state}` : "wf"} width={size} height={size} viewBox="0 0 48 48" aria-hidden focusable="false">
      <defs>
        <radialGradient id={`${id}-core`} cx="50%" cy="56%" r="55%">
          <stop offset="0" className="wf-stop-signal" />
          <stop offset="1" className="wf-stop-dark" />
        </radialGradient>
        <radialGradient id={`${id}-soft`}>
          <stop offset="0.55" className="wf-stop-signal" />
          <stop offset="1" className="wf-stop-signal wf-stop-clear" />
        </radialGradient>
      </defs>
      <circle className="wf-halo" cx="24" cy="24" r="24" fill={`url(#${id}-soft)`} />
      <g className="wf-body">
        {[false, true].map((left) => (
          <g key={left ? "l" : "r"} transform={left ? "matrix(-1 0 0 1 48 0)" : undefined}>
            <g className={`wf-wings ${left ? "wf-left" : "wf-right"}`}>
              <path className="wf-wing wf-wing-up" d="M25 22C29 14 37.5 4.8 44.8 4.2c3.6-.3 3.4 4.4.2 8.6C40 19 32.5 22.6 25 24.6z" />
              <path className="wf-wing wf-wing-down" d="M25.5 26.4c5.8.4 13.2 3.2 16.2 7.6 2.2 3.3-.5 6.2-4 4.4-4.4-2.3-8.9-7-12.2-10.2z" />
            </g>
          </g>
        ))}
        <g className="wf-core-g">
          <circle className="wf-glow" cx="24" cy="24" r="19" fill={`url(#${id}-soft)`} />
          <circle className="wf-core" cx="24" cy="24" r="15" fill={`url(#${id}-core)`} />
          {/* a thin light edge along the top-left rim, well clear of the mic */}
          <path className="wf-shine" d="M10.6 21.6A13.6 13.6 0 0 1 21.6 10.6" />
          {mic && <path className="wf-mic" d={MIC_PATH} transform="translate(24 24.4) scale(0.8) translate(-12 -11.5)" />}
        </g>
        <g className="wf-sparks">
          <circle className="wf-spark" cx="24" cy="4.6" r="1.5" />
          <circle className="wf-spark" cx="40.8" cy="33.7" r="1.5" />
          <circle className="wf-spark" cx="7.2" cy="33.7" r="1.5" />
        </g>
      </g>
    </svg>
  );
}
