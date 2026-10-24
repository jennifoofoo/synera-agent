// "You are here: Kitchen 1.30" above the card, with × to forget it. Shows state.position as the API reports it.
// Owner: the Card/Position session.

import { useState } from "react";
import { useTwin } from "../store";

export function HereChip() {
  const model = useTwin((s) => s.model);
  const buildingKey = useTwin((s) => s.buildingKey);
  const position = useTwin((s) => s.state?.position ?? null);
  const ask = useTwin((s) => s.ask);
  const flyTo = useTwin((s) => s.flyTo);
  const [clearing, setClearing] = useState(false);
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
        You are here: <b>{name}</b>
      </button>
      <button className="x" onClick={() => void clear()} disabled={clearing} aria-label="Forget where I am">
        ×
      </button>
    </div>
  );
}
