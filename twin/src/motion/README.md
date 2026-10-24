# Walk with me (motion module)

Moves the phone's dot along the known route without GPS. It counts steps from the accelerometer (pedestrian dead reckoning) and puts each step onto the route polyline. A switch on the page turns it on, and it is off by default.

Honesty rule (same as `docs/specs/auto-pace.md`): every position this module exposes is an estimate. Each one has `estimated: true`. The UI and the agent say "about", "estimated" or "should be near". They never say "you are at" and never claim we see where the person is. The dot gets a halo, not a pin.

Status: this is a standalone module with tests and a dev demo. **It is not wired into `ui/Walk.tsx` or `store.ts` yet.**

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

## How the UI should wire it (later step, Walk.tsx / store.ts)
1. Switch "Walk with me" (default off), shown during a route. On tap: `const s = await requestMotionPermission()`. Call it directly in the handler and do not await anything before it. Show the result: `needs-https` means "open the https link", `denied` means "motion access is off in Settings", `unsupported` means "this device has no motion sensor".
2. `walk.start(state.route)`. Subscribe before that.
3. `position`: move the blue dot to `p.point` on `p.floorId`, with a halo, labelled "estimated". Show `about N m left`. Do **not** send it to the server as `here`. It is not a position fact.
4. `legEnded` with `end === "connector"`: guidance says the next step ("Take Stairs 1 up"). If `guide` is active, send "next" as usual. After the person confirms (tap "Next" or says "next" / "I'm upstairs"), call `walk.next()`.
5. `arrived`: say "You should be about there" and let the person confirm. Never say "you have arrived".
6. "I'm here" click or drag, or a spoken position (`state.position` changes during the walk): `walk.resetTo({ point, floorId }, { calibrate: true })`.
7. `offRoute`: show a quiet hint ("Looks like you turned around?"). Do not reroute automatically.
8. End route, switch off or building swap: `walk.stop()`.

## Limits
- Drift is about 5 to 10 % of the distance walked (step length varies). Every connector and every "I'm here" resets it, and confirmations recalibrate the step length (factor clamped 0.7 to 1.3).
- Floors are not detected: the dot waits at every stair/lift until `next()`.
- The heading check needs an absolute compass. iOS gives `webkitCompassHeading`, Android Chrome gives `deviceorientationabsolute`. Steel and machines in a factory bend the compass, so the check only stops advancing after 3 steps against the route and never moves the dot elsewhere.
- iOS needs the permission tap, and every browser needs https (`scripts/tunnel.sh` or `scripts/tunnel-twin.sh`). Desktop Chrome may report `needs-permission` and then never send data. After 3 s without samples the status becomes `unsupported`.
- The phone in a pocket or bag works for steps. Swinging it in the hand gives weaker peaks, and shaking is filtered out.
- Background tabs get no sensor events. A gap over 1 s resets the detector.

## Tests
`npm run test` (vitest) covers synthetic traces (2 Hz walking with noise, slow and fast, standing still = 0 steps, shake bursts ≤ 2), the matcher (advance, stop at connector, pass, arrival, reset, turnaround, calibration) and a real dev route from `/api/route` (fixture in `__fixtures__`). `MOTION_API=http://127.0.0.1:8765 npm run test` also fetches the route live.

Dev demo: `uv run python -m web` and `cd twin && npm run dev`, then open `http://localhost:5180/motion-demo.html`. Click "Load route", then "Next" at the first stairs, then `window.__walkSim(2)` in the console (or the Sim buttons). Click the plan for "I'm here".

## 10-minute real-phone test
1. `scripts/tunnel-twin.sh` (or `scripts/tunnel.sh`) and open the https link on the phone, at `/motion-demo.html` in dev.
2. Load a route that is about 30 to 60 m on one floor, plus one with stairs.
3. Tap "Use phone sensors". On iOS, allow both prompts. The status must turn `active` (if it shows `unsupported` after 3 s, there are no sensor events).
4. Stand still for 30 s with the phone in your hand: steps stay 0.
5. Shake the phone for 3 s: at most 2 steps.
6. Walk 20 steps at normal pace and count them yourself: the app's count should be within ±2.
7. Walk a straight corridor of known length: the "m left" should be within 10 %. Note the difference.
8. At the stairs: the dot stops and the log says `legEnded`. Walk the stairs, then tap Next: the dot is at the start of the next floor.
9. Turn around and walk 5 steps back: `offRoute` appears and the dot stops. Turn again and it moves on.
10. Tap the plan where you really are ("I'm here"): the dot jumps there and the calibration factor changes. Walk on and check that the drift is smaller.
11. Phone in a trouser pocket, repeat step 6.
Write down the step count error, distance error, iOS/Android and the browser.
