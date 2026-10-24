// TODO (position session): "You are here" chip with clear (next ask carries context.here = {clear: true};
// needs a store action `clearHere` — ask the scene session), guide "Step k of n" + "Next" button (sends "next"
// via ask()), destination-only marker text after arrival. Reads state.position / state.guide from the store.
// The 3D markers (blue dot, guide leg line) are drawn by src/scene/Markers.tsx and RouteLine.tsx already.
// Styles: src/ui/Position.css (create it and import here).

import { useTwin } from "../store";

export function Position() {
  const state = useTwin((s) => s.state);
  if (!state?.position && !state?.guide?.active) return null;
  return null; // stub
}
