// Pins of place knowledge (notes and issues) on the focused floor. Labels.tsx lays them out with everything else
// (collision-free, right after the points of interest); this file decides which pins exist and draws one.
// Shown when the "Notes & photos" layer is on, or for the facts Wanda's last reply was about (highlighted).

import { useMemo } from "react";
import type { FloorModel, BuildingModel } from "../model/model";
import { groupFactPins, pinFacts, type FactPinGroup } from "../model/facts";
import { useTwin } from "../store";
import { useFacts } from "../ui/factsStore";
import "./FactPins.css";

/** Pin size (px), see .fact-pin. */
export const FACT_PIN_PX = 22;

/** The pin groups of a floor that are visible now. */
export function useFactPins(floor: FloorModel, model: BuildingModel): FactPinGroup[] {
  const facts = useTwin((s) => s.state?.facts);
  const layer = useFacts((s) => s.layer);
  const highlighted = useFacts((s) => s.highlighted);
  return useMemo(() => {
    const wanted = new Set(highlighted);
    const shown = pinFacts(facts).filter((fact) => layer || wanted.has(fact.id));
    return groupFactPins(model, shown).filter((group) => group.floor_id === floor.id);
  }, [facts, layer, highlighted, model, floor.id]);
}

/** Where a pin may sit relative to its spot (screen px), in order of preference. A pin for a whole room sits just
 * above the room name (which stays readable), a pin on a thing or point sits on it, else beside. */
export function pinSpots(group: FactPinGroup): [number, number][] {
  const r = FACT_PIN_PX + 4;
  return group.roomOnly ? [[0, -21], [0, 21], [r + 12, 0], [-(r + 12), 0]] : [[0, 0], [0, -r], [r, 0], [-r, 0], [0, r]];
}

export function FactPin({ group, dx, dy }: { group: FactPinGroup; dx: number; dy: number }) {
  const open = useFacts((s) => s.openPin);
  const isOpen = useFacts((s) => s.pin?.id === group.id);
  const highlighted = useFacts((s) => group.facts.some((fact) => s.highlighted.includes(fact.id)));
  const issue = group.facts.some((fact) => fact.kind === "issue");
  const photo = group.facts.some((fact) => !!fact.photo);
  const first = group.facts[0];
  const title = group.facts.length === 1 ? `${issue ? "Problem" : "Note"}: ${first.text}` : `${group.facts.length} notes: ${group.facts.map((f) => f.text).join("; ")}`;
  return (
    <button
      type="button"
      className={`fact-pin ${issue ? "fact-issue" : "fact-note"} ${highlighted || isOpen ? "fact-hot" : ""} zoom-fade`}
      style={{ transform: `translate(${dx}px, ${dy}px)` }}
      data-zoom-kind="fact"
      data-testid="fact-pin"
      data-fact-ids={group.facts.map((fact) => fact.id).join(" ")}
      data-fact-kind={issue ? "issue" : "note"}
      data-photo={photo || undefined}
      title={title}
      aria-label={title}
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        open(group);
      }}
    >
      {issue ? <IssueGlyph /> : <NoteGlyph />}
      {photo && <span className="fact-photo-corner" aria-hidden />}
      {group.facts.length > 1 && <span className="fact-count">{group.facts.length}</span>}
    </button>
  );
}

/** Speech bubble (note). */
export function NoteGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path d="M5 5h14a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 19 16h-8l-4.5 3.5V16H5a1.5 1.5 0 0 1-1.5-1.5v-8A1.5 1.5 0 0 1 5 5z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

/** Exclamation mark (open problem). */
export function IssueGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path d="M12 5.5v8" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" />
      <circle cx="12" cy="18" r="1.7" fill="currentColor" />
    </svg>
  );
}
