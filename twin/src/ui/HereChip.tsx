// "You are here: Kitchen 1.30" above the card, with × to forget it. Shows state.position as the API reports it.
// The map shows only the blue dot (no text), so this bar is the one place that names the position.
// Owner: the Card/Position session.

import { useEffect, useState } from "react";
import { useTwin } from "../store";

const HINT_KEY = "twin.here.dragHint";
const hintSeen = (): boolean => {
  try {
    return localStorage.getItem(HINT_KEY) === "1";
  } catch {
    return false;
  }
};
/** The dot was dragged (or the hint was shown long enough): never show the hint again. */
export const markHereHintSeen = () => {
  try {
    localStorage.setItem(HINT_KEY, "1");
  } catch {
    /* private mode: the hint just shows again next time */
  }
  window.dispatchEvent(new Event(HINT_KEY));
};

export function HereChip() {
  const model = useTwin((s) => s.model);
  const buildingKey = useTwin((s) => s.buildingKey);
  const position = useTwin((s) => s.state?.position ?? null);
  const ask = useTwin((s) => s.ask);
  const flyTo = useTwin((s) => s.flyTo);
  const [clearing, setClearing] = useState(false);
  // First time a position shows: a short line that the dot can be dragged (off the map, so it covers nothing).
  const [hint, setHint] = useState(false);
  const known = !!position;
  useEffect(() => {
    if (!known || hintSeen()) return;
    setHint(true);
    const hide = () => setHint(false);
    window.addEventListener(HINT_KEY, hide);
    const timer = setTimeout(() => {
      hide();
      markHereHintSeen();
    }, 7000);
    return () => {
      clearTimeout(timer);
      window.removeEventListener(HINT_KEY, hide);
    };
  }, [known]);
  if (!model || !buildingKey || !position) return null;
  const space = model.spaceById.get(position.space_id);
  const name = space?.name || model.connectorBySpace.get(position.space_id)?.name || position.space_id;

  // The position only changes through the server: context.here {clear: true} travels with one chat message; the agent's reply shows in the card.
  const clear = async () => {
    setClearing(true);
    try {
      await ask("Forget where I am.", false, { here: { clear: true } });
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="here-chip" role="status">
      <button className="here-name" onClick={() => flyTo(position.space_id)} title="Show me">
        <span className="here-dot" aria-hidden />
        <span className="here-text">
          <span>
            You are here: <b>{name}</b>
          </span>
          {hint && <small className="here-hint">Drag the blue dot to correct it</small>}
        </span>
      </button>
      <button className="x" onClick={() => void clear()} disabled={clearing} aria-label="Forget where I am">
        ×
      </button>
    </div>
  );
}
