# Step-free mode

## Goal
A person who says (voice or text) that they use a wheelchair, walker, crutches or pram, or cannot take stairs
("I'm in a wheelchair", "I use a walker", "I can't take stairs", "I have a pram", "Rollstuhl", "Rollator",
"Gehbehinderung", "keine Treppen") gets only step-free routes for the rest of the session: in the chat and for the
route button on the page. Saying the opposite ("I can take stairs again") turns it off.

## Design
- One flag per conversation: `GuideState.step_free` (agent) mirrored to `web.api.Session.step_free` (page).
- Tool `set_step_free(enabled)` only sets the flag and returns `{step_free}`. The model calls it only when the
  person talks about themselves; a benchmark question that merely contains "wheelchair" stays a one-off
  `step_free=true` argument.
- `find_route`, `give_directions`, `campus_route`: effective step_free = argument OR flag, decided in Python.
  With the flag on they also return `normal_route_length_m` for the comparison.
- `POST /api/route` and `POST /api/round`: step_free = request OR session flag.
- `state_view` has `"step_free": bool`. `POST /api/step_free {building, enabled}` sets it (the page's ✕).
- Page: when `state.step_free` is true a small "Step-free" chip with ✕ shows next to the position chip, reusing the
  `here-chip` classes. ✕ turns the mode off. No new look.
- Prompt: call `set_step_free(true)` and confirm in one sentence; opposite: `set_step_free(false)`. With step-free
  always give the length and compare with the normal route; if a place is not reachable step-free, say so, invent
  nothing.

## Acceptance criteria
1. After `set_step_free(true)` a route over two floors uses a lift and no stairs, even when the model passes
   `step_free=false`; without the flag the route is unchanged.
2. The page route endpoint respects the flag; `state_view` contains `step_free`; the ✕ endpoint turns it off.
3. Live: "I'm in a wheelchair." then a route question to a room on another floor gives lift plus metres plus a
   comparison; "I can take stairs again." then the same question gives the normal route. German "Rollator" works.
4. `scripts/check.sh` green, live suite green, dev benchmark not lower than on `integ/wow`.

## Test cases
- Unit (`tests/test_step_free_mode.py`): tool sets flag; find_route and give_directions with flag avoid stairs;
  without flag unchanged; `route_view` ORs the flag; `state_view["step_free"]`; `/api/step_free` toggles.
- Live (`tests/live/test_step_free_mode.py`): English on/off script, German Rollator script.
