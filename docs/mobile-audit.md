# Mobile audit of the page (Chromium Pixel 7 at 412 px, WebKit iPhone 14 at 390 px, touch on)

Written for Leonie's mobile version, see `docs/specs/mobile-first.md`. Not run: real iOS Safari, real Android permission prompts. Screenshots are in `docs/mobile-audit/`.

## Works
- Viewport meta is present (`index.html:5`). No horizontal overflow in 2D, 3D or the New tab.
- Tapping a room selects it and opens the room menu (`iphone14-03-tap-room.png`).
- Pinch and one-finger pan change the plan viewBox (`pixel7-05-pinch-pan.png`). The map has `touch-action: none`, so no double-tap zoom there.
- Upload input has `accept="image/png,image/jpeg"` (`index.html:177`), the picker offers the camera.
- Layout order is topbar, plan (52vh), tabs, chat. Chip and mic are visible without scrolling.

## Must fix before a phone demo
1. **Chat input zooms the page on iOS.** Inputs are 14 px (`style.css:28`, `129`), iOS zooms on focus below 16 px. Add `@media (max-width:820px){ input,select,textarea{font-size:16px} }`. (`iphone14-01-load.png`)
2. **No audio unlock and no wake lock.** `voice.js:223-227` creates `new Audio()` and calls `play()` only after the fetch, so iOS rejects it. The handler says "tap the speaker on the reply", but no such button exists. No `wakeLock`, `visibilitychange` or hands-free code exists (spec items 4, 6, 9). Fix: create and `play()` a silent WAV in the mic click and Send handler, then reuse that element. Call `navigator.wakeLock?.request('screen')` while listening or guiding and release it on `visibilitychange`.
3. **The room popover covers the plan.** 280x142 px at 390 px width hides about 60% of the plan, zoom buttons and minimap (`iphone14-03-tap-room.png`, `iphone14-04-3d.png`). Dock it as a bottom sheet on small screens in `style.css` near line 69: `.popover{position:fixed;left:8px;right:8px;bottom:8px;max-width:none}`.
4. **Plan area is small.** The topbar takes 107 px in three rows (`style.css:32`, `234`), the plan is 52vh of a 664 px viewport, and five floor tabs eat the left side. Put brand, select and "+ New building" in one row or collapse the topbar.

## Should fix
5. **Touch targets under 44 px:** floor tabs 44x34, 2D/3D switch 44x32, zoom buttons 36x36 (2D) and 32x32 (3D), mic and Send 38 px, chat tabs 40 px, popover buttons 25 px, "Voice on" 24 px, language select 23 px, New building 25 px, building select 22 px, selection chip x 18x18, 3D mode buttons 26 px. Fix: `@media (pointer:coarse){button,select,.tab{min-height:44px}}` and 44 px for `.mic` and `.map-controls` buttons (`style.css:56`, `86`, `106`, `351`).
6. **Mic without SpeechRecognition:** the mic is greyed but still tappable, and the text says "Voice input needs Chrome or Edge" (`iphone14-06-mic-noSR.png`). Real WebKit exposes `webkitSpeechRecognition`, so an iPhone shows the mic as supported. No hands-free switch exists yet. The permission-denied text says "address bar", which is wrong on iOS (`iphone14-06-mic-denied.png`).
7. **Slow network:** on simulated 3G the plan took 8.0 s to draw. 14 requests, 1.33 MB, no compression (three.js 692 KB, building JSON 355 KB, app.js 57 KB, scene3d.js 53 KB, CSS 29 KB). `server.py:272-285` sends `no-store` and no gzip. Load three.js, `scene3d.js` and `view3d.js` (about 800 KB) lazily on the first 3D tap and gzip the JSON.

## Nice to have
8. `touch-action:manipulation` on `html` (`style.css:28`) so double-tap does not zoom the chat.
9. No "thinking" indicator while a reply is pending (spec item 7). The chat log is capped at 30vh.
10. The 3D controls are small and close together on the right edge.
