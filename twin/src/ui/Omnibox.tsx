// The one input: "Ask or search…". Typing shows hits (rooms, things, stairs/lifts, floors); Enter on a hit
// flies there, Enter on a sentence asks the building. The reply shows in the Card. Voice in via the mic.
// PLACEHOLDER (scaffold): works, but plain. Owner: the ChatBar/Search session, see ARCHITECTURE.md.

import { useMemo, useState } from "react";
import Fuse from "fuse.js";
import { floorLabel } from "../model/model";
import { prettyType } from "../model/palette";
import { useTwin } from "../store";
import { listenOnce, speak, speechInputAvailable } from "../voice";

interface Hit {
  id: string;
  kind: "room" | "thing" | "connector" | "floor";
  title: string;
  subtitle: string;
  floorId: string;
}

export function Omnibox() {
  const model = useTwin((s) => s.model);
  const ask = useTwin((s) => s.ask);
  const busy = useTwin((s) => s.chatBusy);
  const flyTo = useTwin((s) => s.flyTo);
  const select = useTwin((s) => s.select);
  const focusFloor = useTwin((s) => s.focusFloor);
  const requestCamera = useTwin((s) => s.requestCamera);
  const speechAvailable = useTwin((s) => s.speechAvailable);
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);

  const hits = useMemo<Hit[]>(() => {
    if (!model) return [];
    const floorName = (id: string) => (model.floorById.get(id) ? floorLabel(model.floorById.get(id)!) : "");
    return [
      ...model.floors.map<Hit>((floor) => ({ id: floor.id, kind: "floor", title: floorLabel(floor), subtitle: `${floor.spaces.length} rooms`, floorId: floor.id })),
      ...model.building.spaces
        .filter((space) => space.name)
        .map<Hit>((space) => ({
          id: space.id,
          kind: model.connectorBySpace.has(space.id) ? "connector" : "room",
          title: space.name,
          subtitle: `${prettyType(space.room_type)} · ${floorName(space.floor_id)}`,
          floorId: space.floor_id,
        })),
      ...model.building.assets.map<Hit>((asset) => ({
        id: asset.id,
        kind: "thing",
        title: asset.name,
        subtitle: `${prettyType(asset.type)} · ${model.spaceById.get(asset.space_id)?.name ?? ""} · ${floorName(asset.floor_id)}`,
        floorId: asset.floor_id,
      })),
    ];
  }, [model]);
  const fuse = useMemo(() => new Fuse(hits, { keys: ["title"], threshold: 0.3, ignoreLocation: true }), [hits]);
  const looksLikeQuestion = text.trim().split(/\s+/).length > 3 || /[?]/.test(text);
  const results = useMemo(() => (text.trim() && !looksLikeQuestion ? fuse.search(text, { limit: 6 }).map((r) => r.item) : []), [fuse, text, looksLikeQuestion]);

  const go = (hit: Hit) => {
    setText("");
    if (hit.kind === "floor") {
      focusFloor(hit.floorId);
      requestCamera({ kind: "floor", floorId: hit.floorId });
      return;
    }
    const asset = model?.assetById.get(hit.id);
    const connector = model?.connectorBySpace.get(hit.id);
    if (asset) select({ kind: "asset", id: hit.id, floor_id: hit.floorId, space_id: asset.space_id });
    else if (connector) select({ kind: "connector", id: connector.id, floor_id: hit.floorId, space_id: hit.id });
    else select({ kind: "space", id: hit.id, floor_id: hit.floorId });
    flyTo(hit.id);
  };

  const submit = async (message: string, voice = false) => {
    setText("");
    const reply = await ask(message, voice);
    if (reply && voice) void speak(reply.reply, speechAvailable);
  };

  return (
    <div className="omnibox">
      {results.length > 0 && (
        <ul className="hits" role="listbox">
          {results.map((hit, index) => (
            <li key={hit.id}>
              <button className={index === 0 ? "first" : ""} onClick={() => go(hit)}>
                <span className="hit-title">{hit.title}</span>
                <span className="hit-sub">{hit.subtitle}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="omnibox-input"
        onSubmit={(event) => {
          event.preventDefault();
          if (!text.trim()) return;
          if (results.length && !looksLikeQuestion) go(results[0]);
          else void submit(text.trim());
        }}
      >
        <button
          type="button"
          className={`mic ${listening ? "listening" : ""}`}
          disabled={!speechInputAvailable()}
          title={speechInputAvailable() ? "Speak" : "Voice input needs Chrome or Safari"}
          aria-label="Speak"
          onClick={() => {
            if (listening) return;
            setListening(true);
            listenOnce(
              "en-US",
              (heard) => void submit(heard, true),
              () => setListening(false),
            );
          }}
        >
          {listening ? "●" : "🎤"}
        </button>
        <input value={text} onChange={(event) => setText(event.target.value)} placeholder={busy ? "Thinking…" : "Ask or search…"} aria-label="Ask or search" disabled={busy} autoComplete="off" />
      </form>
    </div>
  );
}
