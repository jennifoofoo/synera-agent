// TODO (phone session, branch claude/twin-phone): phone glue, replaces this stub. Renders only on worker:
// Back + Search 44 px header buttons, CSS vars --vvh/--vvtop/--dock-h, html.keyboard-open, audio unlock on the
// first tap, wake lock while state.guide.active, bottom-sheet card. Rules: twin/MOBILE.md. Styles: Phone.css.

import { useTwin } from "../store";

export function Phone() {
  const profile = useTwin((s) => s.profile);
  if (profile !== "worker") return null;
  return null; // stub
}
