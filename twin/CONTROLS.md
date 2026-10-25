# Camera controls

The single source of this table is `src/scene/controlsTable.ts`. The help card (press `?` or `H`) reads from it, so
change it there first and copy it here.

## Keyboard

Active when no text field, list, chat or autocomplete has focus (those keep their keys). Keys are held keys: motion is
smooth, stepped per frame with the frame time, works with key repeat disabled, and stops on keyup, blur and tab switch.

| Keys | Does |
| --- | --- |
| W A S D, arrows | Move over the floor, relative to the view direction |
| Q / E | Rotate left / right (3D) |
| R / F, + / - | Zoom in / out |
| Shift | 3x faster while moving, zooming or rotating |
| Home, 0 | Reset the view |
| 1 to 9, G | Show floor 1 to 9 (G = ground floor, level 0) |
| T | Switch between 2D and 3D (planner only) |
| L | Open or close the list |
| Esc | Close the open panel |
| ? or H | Help card (closes with Esc or any key) |

## Mouse, trackpad and touch

Works the same in 2D and 3D, Chrome and Safari. 2D has no tilt, so there "tilt" rotates or does nothing.

| Input | Does |
| --- | --- |
| Drag (mouse, or trackpad with the click held) | Grab the map and move it. The point under the pointer stays under it |
| Option / Alt + drag | Up / down tilts (3D), sideways rotates |
| Right drag, Ctrl + drag | Rotate and tilt, like Option + drag |
| Two-finger trackpad swipe | Move the map. Never zooms |
| Pinch, mouse wheel | Zoom towards the pointer. One 100 px wheel notch is a 15 percent step |
| Option / Alt + two-finger swipe or wheel | Sideways rotates, up / down tilts (3D). In 2D both directions rotate |
| Two-finger twist (Safari) | Rotate. Chrome has no twist: use Option + swipe, Option + drag or the compass |
| Compass (end of the floor rail) | Click: north up and straight down. Drag: rotate (3D: up / down tilts). The two arrow buttons below it tilt flatter / steeper (3D) |
| Click | Select a room, only if the pointer moved less than 6 px |
| Double click, double tap | Fly to that room (3D), zoom in 2x at that point (2D) |
| One finger | Move the map |
| Two fingers | 2D: pinch to zoom around the midpoint, the map moves with the fingers, no rotation. 3D: pinch to zoom, twist to rotate, up or down to tilt |

The 3D view never tilts flatter than about 57 degrees from straight down (`MAX_TILT` in `CameraRig.tsx`), for every
input. Room names far from the camera (more than 1.3 times the orbit distance) are hidden in 3D so the horizon does
not fill up with names; marked and selected rooms keep theirs. The first time the 3D view shows on the laptop, a hint
says "Option + drag to tilt" (once, remembered in localStorage).

How a wheel event is told apart (`scene/wheelInput.ts`, unit tested in `wheelInput.test.ts`): ctrl + wheel is a
trackpad pinch (Chrome, Firefox) and zooms; Option / Alt + wheel orbits. Otherwise the device decides, first match
wins: line or page mode is a mouse; an event less than 150 ms after the last one keeps that gesture's device (a swipe
never turns into a zoom halfway, momentum included); a sideways delta is a trackpad; a legacy `wheelDeltaY` of exactly
-3 x `deltaY` is a trackpad, whole multiples of 120 a mouse; a fractional delta is a trackpad; a whole step of 50 px
or more on Y only is a mouse notch, a smaller one a trackpad. Trackpad pans, mouse zooms. Safari pinch and twist come
as `gesturechange` (scale zooms, rotation turns after an 8 degree dead zone). The page never scrolls or zooms while
the pointer is over the canvas.

## Map symbols

The help card (`?`, `H`, or the `?` button under the floor rail on the laptop) also explains the 2D map symbols,
from `POI_LEGEND` in `scene/poiIcons.tsx`: entrance / exit, lift, stairs, toilets, not step-free (a step or
threshold), coffee machine, printer, fire extinguisher, first aid / defibrillator, and the grey shapes (machines,
racks, furniture; darker and named when the directions use them as a landmark). When each appears: `scene/mapZoom.ts`.

## Where it lives

- `scene/cameraMouse.ts`: pan (grab), wheel and gestures, drag never clicks, double click hook.
- `scene/wheelInput.ts`: which wheel event is a pinch, a swipe, a mouse notch or an orbit; the Safari twist.
- `ui/Compass.tsx`: compass and tilt buttons at the end of the floor rail, the one-time tilt hint.
- `scene/cameraKeys.ts`: held keys, typing guard (`isTypingTarget`).
- `scene/CameraRig.tsx`: limits, damping, store requests, floor and view keys, the double click fly-to.
- `ui/KeyHelp.tsx`: the help card.
- `tests/e2e/test_twin_controls.py`: left drag moves the map by the dragged distance, a drag selects nothing.
- `tests/e2e/test_twin_trackpad.py`: trackpad swipe pans, ctrl + wheel zooms, Alt + wheel and Alt + drag rotate and
  tilt, the tilt buttons and the tilt limit, the compass resets north up.
