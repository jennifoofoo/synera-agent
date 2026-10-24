# Building Twin (3D)

Our own 3D twin of a kit building over the existing JSON API: React + three.js (react-three-fiber), built from
scratch. One screen: the building, one input ("Ask or search…"), one card.

## Start (dev)

From the repo root, two terminals:

```bash
uv run python -m web
```

```bash
cd twin && npm install && npm run dev
```

Open http://localhost:5180. Vite proxies `/api/*` to the Python server on 127.0.0.1:8765 (set `TWIN_API` to use
another one). `?building=dev/proc-factory-dev-003` opens a building directly.

## Build

`npm run build` → `twin/dist/`; `npm run preview` serves that build on http://localhost:5181 with the same `/api` proxy
(use this for timing: the dev server loads ~170 unbundled modules on every reload).
It writes `twin/dist/` (index.html + assets, all relative). To serve it from the Python server later:
copy `dist/` to `web/static/twin/` (or point the server at it) and open `/twin/`; the API calls are same-origin
`/api/...`, nothing else to configure.

## Dependencies (all permissive)

react, react-dom (MIT) · three (MIT) · @react-three/fiber, drei, postprocessing (MIT) · postprocessing (Zlib) ·
n8ao (ISC) · three-mesh-bvh (MIT) · zustand (MIT) · fuse.js (Apache-2.0) · cmdk (MIT) · vite, typescript (MIT).
No GPL/AGPL code; xeokit and indoor3D were looked at for the look only.

See `ARCHITECTURE.md` for the module boundaries and the store.
