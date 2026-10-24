// One input with ONE inline completion: the best matching place appears as grey ghost text after what was typed.
// Enter, → , Tab or a tap on the grey text accepts it (onPick). A short list of matches only on a laptop, with ↓.
// Used by the Omnibox and the directions From/To fields. Owner: chat/search session.

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type RefObject } from "react";
import Fuse from "fuse.js";
import { floorLabel } from "../model/model";
import { prettyType } from "../model/palette";
import { useTwin } from "../store";
import "./Autocomplete.css";

export type PlaceKind = "room" | "connector" | "thing" | "floor";

export interface PlaceHit {
  id: string;
  kind: PlaceKind;
  title: string;
  subtitle: string;
  /** The room itself for rooms and stairs/lifts, the containing room for things, null for floors. */
  spaceId: string | null;
  floorId: string;
  ref: string;
  type: string;
}

const KIND_LABEL: Record<PlaceKind, string> = { room: "Room", thing: "Thing", connector: "Stairs/lift", floor: "Floor" };
const KIND_RANK: Record<PlaceKind, number> = { room: 0, connector: 1, thing: 2, floor: 3 };
const ALL_KINDS: PlaceKind[] = ["room", "connector", "thing", "floor"];

const coarsePointer = () => typeof window !== "undefined" && !!window.matchMedia?.("(pointer: coarse)").matches;

/** Every searchable place of the open building, optionally only some kinds, with a fuse index. */
export function usePlaces(kinds: PlaceKind[] = ALL_KINDS) {
  const model = useTwin((s) => s.model);
  const kindsKey = kinds.join(",");
  const places = useMemo<PlaceHit[]>(() => {
    if (!model) return [];
    const wanted = new Set(kindsKey.split(","));
    const floorName = (id: string) => {
      const floor = model.floorById.get(id);
      return floor ? floorLabel(floor) : "";
    };
    const result: PlaceHit[] = [];
    if (wanted.has("floor"))
      for (const floor of model.floors)
        result.push({
          id: floor.id,
          kind: "floor",
          title: floorLabel(floor),
          subtitle: `${floor.spaces.length} rooms`,
          spaceId: null,
          floorId: floor.id,
          ref: floor.id,
          type: "floor level",
        });
    for (const space of model.building.spaces) {
      if (!space.name) continue;
      const kind: PlaceKind = model.connectorBySpace.has(space.id) ? "connector" : "room";
      if (!wanted.has(kind)) continue;
      result.push({
        id: space.id,
        kind,
        title: space.name,
        subtitle: [prettyType(space.room_type), floorName(space.floor_id)].filter(Boolean).join(" · "),
        spaceId: space.id,
        floorId: space.floor_id,
        ref: [space.ref, space.id].filter(Boolean).join(" "),
        type: `${space.room_type} ${space.type}`.replace(/_/g, " "),
      });
    }
    if (wanted.has("thing"))
      for (const asset of model.building.assets)
        result.push({
          id: asset.id,
          kind: "thing",
          title: asset.name,
          subtitle: [prettyType(asset.type), model.spaceById.get(asset.space_id)?.name, floorName(asset.floor_id)]
            .filter(Boolean)
            .join(" · "),
          spaceId: asset.space_id,
          floorId: asset.floor_id,
          ref: asset.id,
          type: `${asset.type} ${asset.category ?? ""}`.replace(/_/g, " "),
        });
    return result;
  }, [model, kindsKey]);
  const fuse = useMemo(
    () =>
      new Fuse(places, {
        keys: [
          { name: "title", weight: 0.6 },
          { name: "ref", weight: 0.25 },
          { name: "type", weight: 0.15 },
        ],
        threshold: 0.32,
        ignoreLocation: true,
      }),
    [places],
  );
  return { places, fuse };
}

const startsWith = (hit: PlaceHit, lower: string) => hit.title.toLowerCase().startsWith(lower);
const better = (a: PlaceHit, b: PlaceHit) =>
  KIND_RANK[a.kind] < KIND_RANK[b.kind] || (KIND_RANK[a.kind] === KIND_RANK[b.kind] && a.title.length < b.title.length);

/** The one best completion: a title that starts with the text wins (rooms first, then shorter), else fuse's best. */
export function bestPlace(places: PlaceHit[], fuse: Fuse<PlaceHit>, text: string): PlaceHit | null {
  const lower = text.trim().toLowerCase();
  if (!lower) return null;
  let best: PlaceHit | null = null;
  for (const hit of places) if (startsWith(hit, lower) && (!best || better(hit, best))) best = hit;
  return best ?? fuse.search(lower, { limit: 1 })[0]?.item ?? null;
}

export interface AutocompleteProps {
  value: string;
  onChange: (text: string) => void;
  /** Enter, → , Tab or a tap on the grey text (or a list row). The value is not changed; the parent decides. */
  onPick: (hit: PlaceHit) => void;
  placeholder?: string;
  /** Which places to offer; default all. */
  kinds?: PlaceKind[];
  /** Enter when there is no completion (the Omnibox asks the agent). */
  onEnter?: (text: string) => void;
  /** True when this text should get no completion (e.g. a sentence in the Omnibox). */
  noCompletion?: (text: string) => boolean;
  /** Where the laptop list (↓) opens; never on touch screens. */
  listPlacement?: "above" | "below";
  maxHits?: number;
  onEscape?: () => void;
  inputRef?: RefObject<HTMLInputElement>;
  autoFocus?: boolean;
  ariaLabel?: string;
  readOnly?: boolean;
  className?: string;
  enterKeyHint?: "search" | "send" | "go" | "done" | "next";
  onFocus?: () => void;
  onBlur?: () => void;
}

export function Autocomplete({
  value,
  onChange,
  onPick,
  placeholder,
  kinds,
  onEnter,
  noCompletion,
  listPlacement = "below",
  maxHits = 6,
  onEscape,
  inputRef: outerRef,
  autoFocus,
  ariaLabel,
  readOnly,
  className,
  enterKeyHint,
  onFocus,
  onBlur,
}: AutocompleteProps) {
  const { places, fuse } = usePlaces(kinds);
  const ownRef = useRef<HTMLInputElement>(null);
  const inputRef = outerRef ?? ownRef;
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useMemo(() => `ac-list-${Math.random().toString(36).slice(2, 8)}`, []);

  const text = value;
  const query = text.trim();
  const skip = !query || readOnly || !!noCompletion?.(query);
  const completion = useMemo(() => (skip ? null : bestPlace(places, fuse, query)), [skip, places, fuse, query]);
  const rows = useMemo(() => {
    if (!open || !query) return [];
    const found = fuse.search(query, { limit: maxHits }).map((result) => result.item);
    return completion ? [completion, ...found.filter((hit) => hit.id !== completion.id)].slice(0, maxHits) : found;
  }, [open, query, fuse, maxHits, completion]);
  const showList = open && rows.length > 0 && !readOnly && !coarsePointer();

  // Ghost text after the typed text: the rest of the title, or "→ title" when the match is not a prefix.
  const ghost = completion
    ? completion.title.toLowerCase().startsWith(text.toLowerCase())
      ? completion.title.slice(text.length)
      : `  → ${completion.title}`
    : "";
  const showGhost = !!ghost && !showList;

  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus, inputRef]);

  // A tap outside closes the list.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("pointerdown", onDown);
    return () => window.removeEventListener("pointerdown", onDown);
  }, [open]);

  // The ghost sits exactly over the input: copy its font and padding (phone CSS changes them).
  const [ghostStyle, setGhostStyle] = useState<CSSProperties>({});
  useLayoutEffect(() => {
    const input = inputRef.current;
    if (!showGhost || !input) return;
    const css = getComputedStyle(input);
    setGhostStyle({ font: css.font, letterSpacing: css.letterSpacing, padding: css.padding });
  }, [showGhost, inputRef]);

  const accept = (hit: PlaceHit) => {
    setOpen(false);
    onPick(hit);
  };

  return (
    <div className={`ac ${className ?? ""}`} ref={rootRef}>
      {showGhost && (
        <div className="ac-ghost" aria-hidden style={ghostStyle}>
          <span className="ac-typed">{text}</span>
          <span className="ac-suggest" onPointerDown={(event) => event.preventDefault()} onClick={() => completion && accept(completion)}>
            {ghost}
          </span>
        </div>
      )}
      <input
        ref={inputRef}
        value={text}
        onChange={(event) => onChange(event.target.value)}
        onFocus={onFocus}
        onBlur={onBlur}
        onKeyDown={(event) => {
          const input = event.currentTarget;
          const atEnd = input.selectionStart === input.value.length && input.selectionEnd === input.value.length;
          if (event.key === "Enter") {
            if (event.nativeEvent.isComposing) return;
            event.preventDefault();
            if (showList && rows[active]) accept(rows[active]);
            else if (completion) accept(completion);
            else if (query) onEnter?.(query);
          } else if ((event.key === "ArrowRight" || event.key === "Tab") && atEnd && completion && !showList && !event.shiftKey) {
            event.preventDefault();
            accept(completion);
          } else if (event.key === "ArrowDown" && query && !coarsePointer()) {
            event.preventDefault();
            if (!open) {
              setOpen(true);
              setActive(0);
            } else if (rows.length) setActive((index) => (index + 1) % rows.length);
          } else if (event.key === "ArrowUp" && showList) {
            event.preventDefault();
            setActive((index) => (index - 1 + rows.length) % rows.length);
          } else if (event.key === "Escape") {
            if (open) setOpen(false);
            else if (text) onChange("");
            else input.blur();
            onEscape?.();
          }
        }}
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder}
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="inline"
        role="combobox"
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        spellCheck={false}
        enterKeyHint={enterKeyHint}
        readOnly={readOnly}
      />
      {showList && (
        <ul className={`ac-list ac-${listPlacement}`} role="listbox" id={listId}>
          {rows.map((hit, index) => (
            <li key={hit.id} role="option" aria-selected={index === active}>
              <button
                type="button"
                className={`ac-row ${index === active ? "active" : ""}`}
                onPointerEnter={() => setActive(index)}
                onPointerDown={(event) => event.preventDefault()}
                onClick={() => accept(hit)}
              >
                <span className="ac-title">{hit.title}</span>
                <span className="ac-sub">
                  <span className="ac-kind">{KIND_LABEL[hit.kind]}</span>
                  {hit.subtitle && ` · ${hit.subtitle}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
