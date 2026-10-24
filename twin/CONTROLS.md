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

| Input | Does |
| --- | --- |
| Left drag, middle drag | Grab the map and move it (2D and 3D). The point under the pointer stays under it, no damping |
| Right drag, Ctrl or Alt + left drag | Rotate (3D also tilts, 2D rotates only; Home turns the plan north up) |
| Wheel, trackpad pinch | Zoom towards the pointer. One 100 px wheel notch is a 15 percent step |
| Two-finger trackpad scroll | Move the map. Alt + scroll zooms instead (for a mouse that is taken for a trackpad) |
| Click | Select a room, only if the pointer moved less than 6 px |
| Double click | Fly to that room (3D), zoom in (2D) |
| One finger | Move the map |
| Two fingers | Pinch to zoom, twist to rotate, up or down to tilt (3D) |

How a wheel event is told apart: line-mode events and pixel steps of 50 px or more that are whole multiples of 120
(legacy `wheelDeltaY`) are mouse notches and zoom. Small, fractional or sideways steps, and any stream of them, are a
trackpad scroll and pan. Safari pinch (`gesturechange`) and Chrome pinch (ctrl + wheel) zoom. The page never scrolls
or zooms while the pointer is over the canvas.

## Map symbols

The help card (`?`, `H`, or the `?` button under the floor rail on the laptop) also explains the 2D map symbols,
from `POI_LEGEND` in `scene/poiIcons.tsx`: entrance / exit, lift, stairs, toilets, not step-free (a step or
threshold), coffee machine, printer, fire extinguisher, first aid / defibrillator, and the grey shapes (machines,
racks, furniture; darker and named when the directions use them as a landmark). When each appears: `scene/mapZoom.ts`.

## Where it lives

- `scene/cameraMouse.ts`: pan (grab), wheel and gestures, drag never clicks, double click hook.
- `scene/cameraKeys.ts`: held keys, typing guard (`isTypingTarget`).
- `scene/CameraRig.tsx`: limits, damping, store requests, floor and view keys, the double click fly-to.
- `ui/KeyHelp.tsx`: the help card.
- `tests/e2e/test_twin_controls.py`: left drag moves the map by the dragged distance, a drag selects nothing.
