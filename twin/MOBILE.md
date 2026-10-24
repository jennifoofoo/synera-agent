# Mobile (worker view): the essentials

Sources: `docs/mobile-audit.md`, `docs/specs/mobile-first.md`, Leonie's design decisions.

## Screen
- Only the building, a slim header (back, name, search). No lists, tabs, panels, no minimap.
- Starts in the 2D top-down view of the current floor; 3D is one tap away.
- At the bottom, in thumb reach: one "Ask or search…" input with a big mic.
- Route, next step and finds only when needed, as a bottom sheet (never over the plan). Cards only on tap, 2 to 3 lines.
- Touch targets at least 44 px. Inputs at least 16 px font (otherwise iOS zooms). `touch-action: manipulation`.

## Voice and sound (demo device: iPhone with Safari)
- Push-to-talk: tap the mic, speak. No hands-free in the video.
- Needs https: `scripts/tunnel.sh`.
- Unlock audio on the first tap (play a silent WAV, reuse the audio element).
- Keep the screen awake (Wake Lock) while listening and guiding.
- "Wanda is thinking" instead of silence. Send `voice: true` for speech input.

## Position and guidance
- Blue "You are here" dot, set with "I'm here" (`context.here`).
- Show only the current leg, small "Step 2 of 5" (`state.guide`).

## Performance
- Light rendering on the phone: no ambient occlusion, no post effects, load 3D on demand, things only nearby.

## Look
- Bluish, clean, a little gold as accent, colour only for information, respect `prefers-reduced-motion`.

## Acceptance
- On a real iPhone over the tunnel: loads without horizontal scrolling, tap selects, voice by tap, reply is spoken, guidance keeps the screen on.
