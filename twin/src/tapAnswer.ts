// A tap on the map (2D or 3D). Normally it selects (the room card opens). While Wanda waits for "where are you?"
// (store.awaitingPlace) the tap answers instead: the position is set on screen like "I'm here" on the card (exact
// spot included) and "I'm here." goes to the agent at once with context.here, so the original question continues.

import { useTwin, type Selection } from "./store";
import { speak } from "./voice";
import { followUpAfterSpeech } from "./handsFree";

export function tapMap(selection: Selection, screen?: [number, number]): void {
  const state = useTwin.getState();
  const awaiting = state.awaitingPlace;
  // The From/To panel and a Level 4 draft use taps for themselves; then the tap is an ordinary selection.
  if (!awaiting || state.directions || state.draft || !state.model) return state.select(selection, screen);
  const spaceId = selection.kind === "space" ? selection.id : selection.space_id;
  const space = spaceId ? state.model.spaceById.get(spaceId) : undefined;
  if (!space) return state.select(selection, screen);
  const point = selection.kind === "space" || selection.kind === "point" ? (selection.point ?? null) : null;
  useTwin.setState({ awaitingPlace: null, selection: null, popover: null });
  state.setHere({ space_id: space.id, floor_id: selection.floor_id ?? space.floor_id, point });
  void answer(awaiting.voice);
}

async function answer(voice: boolean): Promise<void> {
  const reply = await useTwin.getState().ask("I'm here.", voice);
  if (!voice || !reply) return;
  const { voiceOut, handsFree, speechAvailable } = useTwin.getState();
  if (voiceOut || handsFree) void speak(reply.reply, speechAvailable);
  followUpAfterSpeech();
}
