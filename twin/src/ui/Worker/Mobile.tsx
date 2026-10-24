// TODO (phone session): everything from docs/mobile-audit.md that is UI-only:
// - audio unlock on the first touch (silent WAV, reuse the element) and Screen Wake Lock while listening/guiding
//   (expose unlockAudio()/holdWakeLock() for ui/Omnibox.tsx to call; keep them in src/ui/Worker/mobile.ts),
// - card as a bottom sheet, 44 px targets, 16 px inputs (base styles already set font-size: 16px on the input),
// - "voice needs Chrome/Safari" note, lazy-load checks, test over scripts/tunnel.sh (https).
// Mounted only when profile === "worker" (width < 1100 px). Styles: src/ui/Worker/Mobile.css.

import { useTwin } from "../../store";

export function Mobile() {
  const profile = useTwin((s) => s.profile);
  if (profile !== "worker") return null;
  return null; // stub
}
