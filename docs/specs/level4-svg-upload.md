# Level 4: plan with vector file and building.json (contract for the page)

Status: server side done, page (web/static) not changed. Paste the "For Leonie" block into `docs/LEONIE_TODO.md`
(that file lives on main, not on integration).

## What Synera said

- Plans arrive as `floor_<n>.png`, `floor_<n>_plain.png` and `floor_<n>.svg` next to each other, in the kit's drawing style.
- The scale is in the plan's `building.json` (exact field unknown).

## What the server does now

- `build_from_plan` looks for `<stem>.svg` next to the plan image (also without a trailing `_plain`) inside the fixed
  upload folder `agent_output/uploads`. Never from a path of the browser or of a message.
- Valid kit svg: rooms (exact outlines), doors, openings, entrances and room numbers come from the svg. The vision
  model is still called once per floor, only for names and room types (stairs, lifts, kitchen, ...). If that call
  fails the build goes on from the svg alone (rooms named by number) and the card says so.
- Anything else (not a kit svg, other size than the png, scripts or links inside, symlink out of the folder): ignored,
  the old vision pipeline runs, a note on the card says why.
- The card says where each floor was read from (`read from`) and where the scale came from (`scale`).
- Scale order: length the person gave, then a scale field in building.json, then a printed bar, then (svg only) the
  building width in building.json, else the person is asked once. Field names tried: `m_per_px`, `metres_per_pixel`,
  `meters_per_pixel`, `mpp`, `px_per_m`, `pixels_per_metre`, `ppm`, plain `scale` and `resolution` (1 or more means
  pixels per metre, below 1 metres per pixel), nested anywhere up to 5 levels, per floor (`level`) or global.
  See `building_agent/level4/scale_source.py`.
- building.json is found as `<stem>.building.json` next to the plan, else `building.json` in the same folder.

## For Leonie (page)

The upload endpoint stays as it is (raw PNG/JPG body, returns `upload_id`). New, one call per extra file, after the
image upload:

    POST /api/level4/attach?upload_id=<id>&kind=svg             Content-Type: image/svg+xml      body: the svg file
    POST /api/level4/attach?upload_id=<id>&kind=building_json   Content-Type: application/json   body: the building.json

- Same origin only, like the other POSTs. Answers `{upload_id, kind, bytes, rooms?, doors?}` or `{error}` (415 if the
  file is not usable, 413 if too large: svg 20 MB, json 5 MB).
- Match the files by name: drop `floor_0.png`, `floor_0.svg` together, upload the png, then attach the svg with the
  returned id. One building.json per floor upload is fine (attach the same file to every floor).
- If a building.json is attached to a floor, `/api/level4/build` no longer demands `known_length_m` or `scale_bar`
  for that floor. Without it the old rules apply.
- Nothing else changes in `/api/level4/build`, card, save.
