# Walk with me (motion module)

Moves the phone's dot along the known route without GPS. It counts steps from the accelerometer (pedestrian dead reckoning) and puts each step onto the route polyline. A switch on the page turns it on, and it is off by default.

Honesty rule (same as `docs/specs/auto-pace.md`): every position this module exposes is an estimate. Each one has `estimated: true`. The UI and the agent say "about", "estimated" or "should be near". They never say "you are at" and never claim we see where the person is. The dot gets a halo, not a pin.

Status: wired into the step guide. The glue is `src/walkWithMe.ts` (store `useWalkMotion`), the switch sits in the guide sheet (`ui/Walk.tsx`), the estimated dot is `scene/HerePin.tsx` (`HereDot`). The module itself is unchanged.

## Files
| File | What |
|---|---|
| `sensors.ts` | `motionSupport()`, `requestMotionPermission()`, `listenToSensors()`. Feature detection and the iOS permission prompt. Never throws. |
| `stepDetector.ts` | `StepDetector`, `detectSteps(samples)`, `stepLength(cadenceHz, base?, scale?)`. Pure. |
| `heading.ts` | `headingFromOrientation()`, `HeadingSmoother` (circular mean), `modelBearing`, `modelToCompass`, `angleDiff`. Pure. |
| `legs.ts` | `legsFromRoute(route)` for `/api/route` or `state.route`, and `legsFromSegments(guide.leg.segments)`. |
| `routeMatcher.ts` | `RouteMatcher`: distance along the route, connector stops, arrival, resets, turnaround, calibration. Pure. |
| `walkWithMe.ts` | `createWalkWithMe()`: connects sensors, detector and matcher, has the events and the dev hook `window.__walkSim`. |
| `synthetic.ts` | Synthetic walking, standing and shaking traces for the tests and the simulation. |
| `demo.ts`, `../../motion-demo.html` | Dev demo page, served by `npm run dev` only. Not part of the build. |

## API
```ts
import { createWalkWithMe, requestMotionPermission, motionSupport } from "../motion";

motionSupport(): MotionStatus  // "unsupported" | "needs-https" | "needs-permission" | "denied" | "ready" | "active"
requestMotionPermission(): Promise<MotionStatus>  // call INSIDE the tap handler (iOS)

const walk = createWalkWithMe({ stepLengthM?: 0.7, scaleByCadence?: true, headingCheck?: true,
                                matcher?: { northOffsetDeg?: 0, turnaroundDeg?: 100, turnaroundSteps?: 3 } });
walk.on("position", (p: WalkPosition) => ...)   // every step, next, reset
walk.on("legEnded", ({ legIndex, end, connector, position }) => ...)  // end: "connector" | "pass"
walk.on("arrived", ({ position }) => ...)
walk.on("status", (s: MotionStatus) => ...)
walk.on("step", ({ t, cadenceHz, lengthM }) => ...)
walk.start(route | legs): MotionStatus  // subscribe first: a route that starts in a stairwell ends leg 0 immediately
walk.next()                                // through the stairs/lift, or the person said "next"
walk.resetTo({ point, floorId? } | { distanceAlong }, { calibrate?: boolean })  // "I'm here", drag, voice
walk.confirmLegEnd()                       // "I'm at the stairs": snap to the leg end and recalibrate
walk.position(): WalkPosition | null
walk.calibrationFactor(): number
walk.stop()
walk.simulate(stepsPerSecond)             // synthetic steps through the real detector; window.__walkSim(n) in dev
```
`WalkPosition` = `{ estimated: true, point: [x, y], floorId, legIndex, legCount, alongLegM, legLengthM, alongRouteM, routeLengthM, distanceLeftM, legLeftM, atConnector, arrived, offRoute, steps }`. Points are model metres (+y north), the same as the route line.

Legs: `legsFromRoute` cuts the route at every `floor_change`. Those legs end with `"connector"`, and the matcher waits there because floors are not detected. Two segments on the same floor (walk to outside) are joined by `"pass"`. The last leg ends with `"arrival"`. Route length here counts walking only. Stairs and lifts count 0 m, so it is shorter than `route.length_m`.

`northOffsetDeg` is the compass bearing of the model's +y axis. It is 0 when the data's north is real north. A rotated building needs the real value, otherwise the turnaround check must be off (`headingCheck: false`).

## How it is wired (`src/walkWithMe.ts`)
1. Switch "Walk with me" in the guide sheet, next to "All N steps". Default off, remembered per viewer in `localStorage` (`twin.walkWithMe`, try/catch). The tap calls `requestMotionPermission()` first, inside the gesture. The status shows for 4 s in plain words: "on", "off", "needs https", "motion permission denied", "not supported here".
2. While the switch is on and the guide runs (`walkStep !== null`, route ok), one module instance follows `state.route`. Listeners are attached before `start()`. Switched on mid-walk, the estimate starts at the current step.
3. `position`: `useWalkMotion.estimate` only. `HereDot` draws it as the blue dot with a soft ring (radius grows with 10 % of the metres since the last confirmation, at least 1.5 m) and a small "estimated" label. It is never written to `state.position`, never sent as `here`, never put into a request.
4. Steps follow the estimate: the route's step lines are mapped onto the route metres (`buildPlan`: each floor stretch is shared out over its "Walk about N m" lines in proportion to N). When the estimate passes the end of a line, the guide moves on like the Next button, and the existing speech says the new line. It only moves forward by itself.
5. `legEnded` at stairs or a lift: the guide shows the "Take/Use …" line and waits ("Waiting here. Tap Next once you are through."). Next, "next" by voice or "Hey Wanda, next" moves the step past the ride, and that calls `walk.next()`.
6. `arrived`: "You should be about there." (shown, and spoken when voice is on). While the switch is on, the step line "You have arrived at X" becomes "X should be about here", and hands-free "how far" says "About N metres left".
7. Corrections: "I'm here", dragging the dot, or a position set by voice (any real change of `state.position`) calls `resetTo({ point, floorId }, { calibrate: true })`; the step follows the estimate both ways then. Next/Back by hand move the estimate to the start of that step (no calibration).
8. Distance left in the sheet is the module's `distanceLeftM` ("about N m left") while it runs.
9. Stops on End route, Done, Esc, building change, a new route, switch off and guide stop.
10. One driver: `walkWithMeDriving()` is true while the estimate moves the guide. A time-based auto-pace timer (`docs/specs/auto-pace.md`) must not start while it is true. The twin has no such timer yet, so nothing else advances the steps today.
11. `window.__walkSim(stepsPerSecond)` is installed in every build (not only dev): synthetic steps through the real detector into the running walk, `__walkSim(0)` stops. `window.__walkMotion` is the store, for tests.

## Limits
- Drift is about 5 to 10 % of the distance walked (step length varies). Every connector and every "I'm here" resets it, and confirmations recalibrate the step length (factor clamped 0.7 to 1.3).
- Floors are not detected: the dot waits at every stair/lift until `next()`.
- The heading check needs an absolute compass. iOS gives `webkitCompassHeading`, Android Chrome gives `deviceorientationabsolute`. Steel and machines in a factory bend the compass, so the check only stops advancing after 3 steps against the route and never moves the dot elsewhere.
- iOS needs the permission tap, and every browser needs https (`scripts/tunnel.sh` or `scripts/tunnel-twin.sh`). Desktop Chrome may report `needs-permission` and then never send data. After 3 s without samples the status becomes `unsupported`.
- The phone in a pocket or bag works for steps. Swinging it in the hand gives weaker peaks, and shaking is filtered out.
- Background tabs get no sensor events. A gap over 1 s resets the detector.

## Tests
`npm run test` (vitest) covers synthetic traces (2 Hz walking with noise, slow and fast, standing still = 0 steps, shake bursts ≤ 2), the matcher (advance, stop at connector, pass, arrival, reset, turnaround, calibration) and a real dev route from `/api/route` (fixture in `__fixtures__`). `MOTION_API=http://127.0.0.1:8765 npm run test` also fetches the route live.

Wired UI: `uv run pytest -m e2e tests/e2e/test_walk_with_me.py` (fake chat server, no API key) and `src/walkWithMe.test.ts` (steps follow the estimate).

Dev demo: `uv run python -m web` and `cd twin && npm run dev`, then open `http://localhost:5180/motion-demo.html`. Click "Load route", then "Next" at the first stairs, then `window.__walkSim(2)` in the console (or the Sim buttons). Click the plan for "I'm here".

## Try it
Desktop, no phone: open the twin, pick a route, "Guide me", switch "Walk with me" on, then `__walkSim(2)` in the console. The dot walks the route, the step moves on, it waits at stairs until Next.

Phone: `scripts/build_twin.sh`, then `scripts/tunnel.sh` (needs `brew install cloudflared`; the link is public while it runs, share it with nobody, Ctrl+C when done). Open the https link on the phone. Motion sensors need https; on plain http the switch says "needs https".

## 10-minute real-phone test
1. `scripts/tunnel.sh` and open the https link on the phone (the app itself; the module-only demo is `/motion-demo.html` with `scripts/tunnel-twin.sh` in dev).
2. Load a route that is about 30 to 60 m on one floor, plus one with stairs.
3. Route, "Guide me", switch "Walk with me" on. On iOS, allow both prompts. The sheet must say "on" ("not supported here" after 3 s means no sensor events).
4. Stand still for 30 s with the phone in your hand: steps stay 0.
5. Shake the phone for 3 s: at most 2 steps.
6. Walk 20 steps at normal pace and count them yourself: the app's count should be within ±2.
7. Walk a straight corridor of known length: the "m left" should be within 10 %. Note the difference.
8. At the stairs: the dot stops, the sheet shows the stairs line and "Waiting here". Walk the stairs, then tap Next (or say "Hey Wanda, next"): the dot is at the start of the next floor.
9. Turn around and walk 5 steps back: `offRoute` appears and the dot stops. Turn again and it moves on.
10. Tap the plan where you really are and press "I'm here" (or drag the dot): the dot jumps there and the step follows. Walk on and check that the drift is smaller.
11. Phone in a trouser pocket, repeat step 6.
12. At the end the sheet says "You should be about there.", never "you have arrived". Switch off and back on: it remembers the switch.
Write down the step count error, distance error, iOS/Android and the browser.
