// One card above the input, never two: the selected room/thing (3 actions) or the last reply.
// PLACEHOLDER (scaffold). Owner: the Card/Position session, see ARCHITECTURE.md.

import { floorLabel } from "../model/model";
import { prettyType } from "../model/palette";
import { useTwin } from "../store";

export function Card() {
  const model = useTwin((s) => s.model);
  const selection = useTwin((s) => s.selection);
  const select = useTwin((s) => s.select);
  const state = useTwin((s) => s.state);
  const chat = useTwin((s) => s.chat);
  const route = useTwin((s) => s.route);
  const setClosed = useTwin((s) => s.setClosed);
  const armHere = useTwin((s) => s.armHere);
  const hereArmed = useTwin((s) => s.hereArmed);
  const dismissReply = useTwin((s) => s.dismissReply);
  const replyShown = useTwin((s) => s.replyShown);
  if (!model) return null;

  if (selection) {
    const floor = model.floorById.get(selection.floor_id);
    const space = model.spaceById.get(selection.kind === "space" ? selection.id : selection.space_id ?? "");
    const asset = selection.kind === "asset" ? model.assetById.get(selection.id) : null;
    const connector = selection.kind === "connector" ? model.connectorById.get(selection.id) : null;
    const title = asset?.name ?? connector?.name ?? space?.name ?? selection.id;
    const line = asset
      ? `${prettyType(asset.type)} · ${space?.name ?? ""} · ${floor ? floorLabel(floor) : ""}`
      : connector
        ? `${connector.kind} · ${connector.floor_ids.length} floors`
        : space
          ? `${prettyType(space.room_type)} · ${space.area_m2} m² · ${floor ? floorLabel(floor) : ""}`
          : "";
    const closableId = connector?.id ?? (selection.kind === "space" ? space?.id : undefined);
    const isClosed = closableId ? state?.closed.includes(closableId) : false;
    const roomId = space?.id;
    const from = state?.position?.space_id ?? state?.route?.start;
    return (
      <div className="card" role="dialog" aria-label={title}>
        <div className="card-head">
          <strong>{title}</strong>
          <button className="x" onClick={() => select(null)} aria-label="Close">
            ×
          </button>
        </div>
        <div className="card-line">{line}</div>
        <div className="card-actions">
          {roomId && (
            <button disabled={!from || from === roomId} title={from ? "Route from where you are" : "Say where you are first (I'm here)"} onClick={() => void route(from!, roomId)}>
              Route here
            </button>
          )}
          {roomId && (
            <button className={hereArmed ? "active" : ""} onClick={() => armHere(!hereArmed)} title="Goes with your next message">
              I'm here
            </button>
          )}
          {closableId && (
            <button className={isClosed ? "" : "danger"} onClick={() => void setClosed(closableId, !isClosed)}>
              {isClosed ? "Reopen" : "Close"}
            </button>
          )}
        </div>
      </div>
    );
  }

  const last = chat[chat.length - 1];
  if (!last || !replyShown) return null;
  return (
    <div className="card card-reply" aria-live="polite">
      <div className="card-head">
        <span className="card-who">{last.role === "agent" ? "Building" : "You"}</span>
        <button className="x" onClick={dismissReply} aria-label="Dismiss">
          ×
        </button>
      </div>
      <div className="card-text">{last.text}</div>
      {last.note && <div className="card-note">{last.note}</div>}
    </div>
  );
}
