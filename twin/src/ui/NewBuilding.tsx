// Level 4: "New building…" from floor plan images. One sheet to add the plans, a progress line while they are read,
// then the draft in the 3D scene with its problems in red, a few taps to fix, and a confirm card to save.
// Mount <NewBuilding /> once in App; open it with useNewBuilding.getState().open().

import { useEffect, useRef, useState } from "react";
import { prettyType } from "../model/palette";
import { useTwin } from "../store";
import "./NewBuilding.css";
import { findingsLine, useNewBuilding } from "./newBuildingStore";

const ROOM_TYPES = [
  "office",
  "meeting_room",
  "kitchen",
  "toilet",
  "storage",
  "technical_room",
  "corridor",
  "lobby",
  "stairwell",
  "lift",
  "generic_room",
];

export function NewBuilding() {
  const step = useNewBuilding((s) => s.step);
  if (step === "closed") return null;
  if (step === "form") return <PlanSheet />;
  if (step === "reading") return <Reading />;
  if (step === "saved") return <Saved />;
  return <Review />;
}

/** The one sheet: images, floor numbers, one known length, a name. */
function PlanSheet() {
  const { floors, along, length, name, error, busy, progress } = useNewBuilding();
  const { addFiles, removeFloor, setLevel, setAlong, setLength, setName, read, close } = useNewBuilding.getState();
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="nb-backdrop" onClick={(event) => event.target === event.currentTarget && !busy && close()}>
      <div className="nb-sheet" role="dialog" aria-label="New building">
        <div className="nb-head">
          <strong>New building</strong>
          <button className="x" onClick={close} aria-label="Close" disabled={busy}>
            ×
          </button>
        </div>
        <p className="nb-hint">Add a photo or image of each floor plan. It takes about 15 seconds per floor.</p>

        {floors.map((floor) => (
          <div className="nb-floor" key={floor.id}>
            <img src={floor.url} alt="" />
            <div className="nb-floor-level">
              <span>Floor</span>
              <button onClick={() => setLevel(floor.id, floor.level - 1)} aria-label="Lower floor number" disabled={busy}>
                −
              </button>
              <b>{floor.level}</b>
              <button onClick={() => setLevel(floor.id, floor.level + 1)} aria-label="Higher floor number" disabled={busy}>
                +
              </button>
            </div>
            <button className="x" onClick={() => removeFloor(floor.id)} aria-label="Remove this plan" disabled={busy}>
              ×
            </button>
          </div>
        ))}
        <button className="nb-add" onClick={() => input.current?.click()} disabled={busy}>
          + {floors.length ? "Add another floor" : "Add floor plan"}
        </button>
        <input
          ref={input}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(event) => {
            if (event.target.files?.length) addFiles(event.target.files);
            event.target.value = "";
          }}
        />

        <div className="nb-label">One length you know</div>
        <div className="nb-seg" role="radiogroup" aria-label="Which length">
          {(
            [
              ["building_width", "Building width"],
              ["door", "A door"],
              ["scale_bar", "Scale bar on plan"],
            ] as const
          ).map(([value, label]) => (
            <button key={value} role="radio" aria-checked={along === value} className={along === value ? "on" : ""} onClick={() => setAlong(value)}>
              {label}
            </button>
          ))}
        </div>
        {along !== "scale_bar" && (
          <label className="nb-length">
            <input
              inputMode="decimal"
              placeholder={along === "door" ? "0.9" : "e.g. 40"}
              value={length}
              onChange={(event) => setLength(event.target.value)}
              aria-label="Length in metres"
            />
            <span>m</span>
          </label>
        )}
        <p className="nb-why">A plan has no real size. One length sets the scale for every room and route.</p>

        <input className="nb-name" placeholder="Name (optional)" value={name} onChange={(event) => setName(event.target.value)} maxLength={60} />

        {error && <p className="nb-error">{error}</p>}
        <button className="nb-primary" onClick={() => void read()} disabled={busy || !floors.length}>
          {busy ? progress || "Uploading…" : floors.length > 1 ? `Read ${floors.length} plans` : "Read plan"}
        </button>
      </div>
    </div>
  );
}

/** A slim line at the top while the plans are read in the background; the building stays usable. */
function Reading() {
  const progress = useNewBuilding((s) => s.progress);
  return (
    <div className="nb-bar nb-reading" role="status">
      <span className="nb-spinner" aria-hidden />
      <span>{progress || "Reading…"}</span>
    </div>
  );
}

/** The draft is in the scene: one findings sentence, tap fixes, scale, save. */
function Review() {
  const { preview, note, error, busy, doorFrom, step } = useNewBuilding();
  const { fix, startDoor, askSave, startOver, close } = useNewBuilding.getState();
  const selection = useTwin((s) => s.selection);
  const model = useTwin((s) => s.model);
  const select = useTwin((s) => s.select);
  const [scaleOpen, setScaleOpen] = useState(false);
  const [scale, setScale] = useState("");

  const spaceId = selection ? (selection.kind === "space" ? selection.id : selection.space_id ?? null) : null;
  const space = spaceId ? model?.spaceById.get(spaceId) : undefined;

  // second tap while adding a door: the door goes between the two rooms
  useEffect(() => {
    if (!doorFrom || !spaceId || spaceId === doorFrom) return;
    select(null);
    void fix({ action: "add_door", ref: doorFrom, other_ref: spaceId });
  }, [doorFrom, spaceId, fix, select]);

  if (!preview) return null;
  if (step === "card") return <ConfirmCard />;
  const problems = (preview.findings ?? []).some((finding) => finding.level === "error");
  const label = (id: string) => {
    const item = model?.spaceById.get(id);
    return item?.ref ?? item?.name ?? id;
  };
  const notes = [...new Set(preview.scales?.map((item) => item.note))];
  const scaleNote = notes.length > 1 ? preview.scales?.map((item) => `floor ${item.level}: ${item.note}`).join(" · ") : notes[0];

  return (
    <div className="nb-bar nb-review" role="region" aria-label="Draft building">
      <div className="nb-head">
        <strong>Draft · {preview.draft?.name ?? "New building"}</strong>
        <button className="x" onClick={close} aria-label="Close draft (it is kept)">
          ×
        </button>
      </div>
      <p className={problems ? "nb-findings bad" : "nb-findings"}>{findingsLine(preview)}</p>

      {doorFrom ? (
        <div className="nb-step">
          Tap the second room for the door from <b>{label(doorFrom)}</b>.{" "}
          <button onClick={() => startDoor(null)}>Cancel</button>
        </div>
      ) : space ? (
        <div className="nb-step nb-room">
          <b>{space.ref ?? space.name}</b>
          <span className="nb-muted">{prettyType(space.room_type)}</span>
          <button onClick={() => startDoor(space.id)} disabled={busy}>
            Add a door…
          </button>
          <select
            value=""
            onChange={(event) => event.target.value && void fix({ action: "set_room_type", ref: space.id, room_type: event.target.value })}
            disabled={busy}
            aria-label="Set room type"
          >
            <option value="">Set type…</option>
            {ROOM_TYPES.map((type) => (
              <option key={type} value={type}>
                {prettyType(type)}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <p className="nb-muted nb-tip">Tap a room to set its type or add a door. Or just ask below.</p>
      )}

      {scaleOpen ? (
        <form
          className="nb-step"
          onSubmit={(event) => {
            event.preventDefault();
            const metres = Number(scale.replace(",", "."));
            if (metres > 0) void fix({ action: "set_scale", known_length_m: metres, along: "building_width" }).then(() => setScaleOpen(false));
          }}
        >
          Building width
          <input className="nb-small" inputMode="decimal" autoFocus value={scale} onChange={(event) => setScale(event.target.value)} aria-label="Building width in metres" />
          m <button type="submit" disabled={busy}>Apply</button>
          <button type="button" onClick={() => setScaleOpen(false)}>Cancel</button>
        </form>
      ) : (
        scaleNote && (
          <p className="nb-muted nb-scale">
            Scale: {scaleNote}.{" "}
            <button className="nb-link" onClick={() => setScaleOpen(true)}>
              Change
            </button>
          </p>
        )
      )}

      {note && <p className="nb-note">{note}</p>}
      {error && <p className="nb-error">{error}</p>}
      <div className="nb-actions">
        <button className="nb-link" onClick={() => void startOver()} disabled={busy}>
          Start over
        </button>
        <button className="nb-primary" onClick={() => void askSave()} disabled={busy}>
          Save building…
        </button>
      </div>
    </div>
  );
}

/** The backend saves only after this card and a clear yes as the very next step. */
function ConfirmCard() {
  const { preview, card, busy, acceptProblems, error } = useNewBuilding();
  const { answer, setAcceptProblems } = useNewBuilding.getState();
  if (!preview || !card) return null;
  const canSave = card["can be saved"] !== false;
  return (
    <div className="nb-bar nb-review nb-card" role="dialog" aria-label="Save this building?">
      <strong>Save “{preview.draft?.name ?? "New building"}”?</strong>
      <p>{findingsLine(preview)}</p>
      {!canSave && (
        <label className="nb-anyway">
          <input type="checkbox" checked={acceptProblems} onChange={(event) => setAcceptProblems(event.target.checked)} />
          Save anyway, with the problems in red
        </label>
      )}
      {error && <p className="nb-error">{error}</p>}
      <div className="nb-actions">
        <button onClick={() => void answer(false)} disabled={busy}>
          Not yet
        </button>
        <button className="nb-primary" onClick={() => void answer(true)} disabled={busy || (!canSave && !acceptProblems)}>
          Yes, save
        </button>
      </div>
    </div>
  );
}

function Saved() {
  const building = useTwin((s) => s.building);
  return (
    <div className="nb-bar nb-review" role="status">
      <div className="nb-head">
        <strong>Saved · {building?.name}</strong>
        <button className="x" onClick={() => useNewBuilding.setState({ step: "closed" })} aria-label="Close">
          ×
        </button>
      </div>
      <p className="nb-muted">It is in the building list now. Ask a route or a question below.</p>
    </div>
  );
}
