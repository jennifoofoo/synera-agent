// Knowledge panel (docs/specs/knowledge-graph-view.md): the ego graph of one room from GET /api/graph (JSON-LD with
// Brick/RealEstateCore types) as plain SVG, a time slider that filters the place notes by validFrom/validTo, and the
// Asset Administration Shell export. Opened by the "Knowledge" button in the room card. Desktop: side panel; phone:
// bottom sheet. Layout and time rules live in egoGraph.ts.

import { useEffect, useMemo, useRef, useState } from "react";
import { create } from "zustand";
import { useNotes } from "../notes/notesStore";
import { useTwin } from "../store";
import { ASSET_R, DAY_MS, FACT_R, HOUR_MS, LINE_H, PERSON_R, ROOM_R, TYPE_H, egoGraph, mainType, momentLabel, timeRange, type EgoNode, type LdNode } from "./egoGraph";
import "./KnowledgeGraph.css";

interface KnowledgeState {
  roomId: string | null;
  buildingKey: string | null;
}

const useKnowledge = create<KnowledgeState>(() => ({ roomId: null, buildingKey: null }));

export function openKnowledge(roomId: string): void {
  const { buildingKey, profile, select } = useTwin.getState();
  useKnowledge.setState({ roomId, buildingKey });
  if (profile === "worker") select(null); // one bottom sheet at a time on the phone
}

export function closeKnowledge(): void {
  useKnowledge.setState({ roomId: null });
}

/** The entry in the room card: for the planner on a laptop (never the technician's phone), and only for a room that
 * has at least one note or issue (now or in its history), else there is nothing to show. */
export function KnowledgeButton({ roomId }: { roomId: string }) {
  const planner = useTwin((s) => s.profile === "planner");
  const hasNotes = useNotes((s) => s.notes.some((note) => note.kind !== "closure" && note.anchor.space_id === roomId));
  if (!planner || !hasNotes) return null;
  return (
    <button type="button" data-testid="knowledge-open" onClick={() => openKnowledge(roomId)}>
      Knowledge
    </button>
  );
}

function useWidth(ref: React.RefObject<HTMLElement>, fallback: number): number {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

export function KnowledgeGraph() {
  const roomId = useKnowledge((s) => s.roomId);
  const openedFor = useKnowledge((s) => s.buildingKey);
  const buildingKey = useTwin((s) => s.buildingKey);
  if (!roomId || !buildingKey || openedFor !== buildingKey) return null;
  return <Panel key={`${buildingKey}|${roomId}`} roomId={roomId} buildingKey={buildingKey} />;
}

function Panel({ roomId, buildingKey }: { roomId: string; buildingKey: string }) {
  const phone = useTwin((s) => s.profile === "worker");
  const [now] = useState(() => Date.now());
  const [graph, setGraph] = useState<LdNode[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [at, setAt] = useState(now);
  const [showEnded, setShowEnded] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const width = useWidth(box, phone ? 340 : 400);
  const key = encodeURIComponent(buildingKey);
  const until = timeRange(null, now).max;

  useEffect(() => {
    let alive = true;
    // One fetch at the end of the slider: it holds every fact valid up to then; the slider filters on the client.
    fetch(`/api/graph?key=${key}&at=${encodeURIComponent(new Date(until).toISOString())}`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`))))
      .then((data: { "@graph"?: LdNode[] }) => alive && setGraph(data["@graph"] ?? []))
      .catch((reason: Error) => alive && setError(reason.message));
    return () => {
      alive = false;
    };
  }, [key, until]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && closeKnowledge();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const ego = useMemo(() => (graph ? egoGraph(graph, roomId, { at, showEnded, width }) : null), [graph, roomId, at, showEnded, width]);
  const range = timeRange(ego?.oldest ?? null, now);
  const room = ego?.nodes[0];
  const facts = ego?.nodes.filter((node) => node.ring === 2) ?? [];
  const focused = ego?.nodes.find((node) => node.id === focus) ?? null;
  const byId = new Map(ego?.nodes.map((node) => [node.id, node]));
  const safeKey = buildingKey.replace(/[^A-Za-z0-9._-]+/g, "-");

  return (
    <section className={`kg-panel ${phone ? "kg-sheet" : ""}`} role="dialog" aria-label="Knowledge graph" data-testid="knowledge-panel">
      <div className="kg-head">
        <div className="kg-title">
          <span className="tiny-label">Knowledge graph</span>
          <strong>{room?.label ?? "…"}</strong>
        </div>
        <button type="button" className="x" onClick={closeKnowledge} aria-label="Close knowledge graph">
          ×
        </button>
      </div>
      <div className="kg-graph" ref={box}>
        {error && <p className="kg-muted">Graph not available ({error}).</p>}
        {!error && !ego && <p className="kg-muted">Loading graph…</p>}
        {ego && ego.nodes.length === 0 && <p className="kg-muted">This room is not in the graph.</p>}
        {ego && ego.nodes.length > 0 && (
          <svg width={ego.view.width} height={Math.ceil(ego.view.height)} viewBox={`${ego.view.x} ${ego.view.y.toFixed(1)} ${ego.view.width} ${ego.view.height.toFixed(1)}`} role="img" aria-label={`Ego graph of ${room?.label}`} data-testid="knowledge-svg">
            <g className="kg-edges">
              {ego.edges.map((edge) => {
                const from = byId.get(edge.from);
                const to = byId.get(edge.to);
                if (!from || !to) return null;
                return <line key={`${edge.from}>${edge.to}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} className={edge.faded ? "faded" : ""} />;
              })}
            </g>
            {ego.nodes.map((node) => (
              <GraphNode key={node.id} node={node} focused={focus === node.id} onFocus={setFocus} />
            ))}
          </svg>
        )}
      </div>
      {ego && focus === "more" && ego.moreItems.length > 0 && (
        <p className="kg-more-list" data-testid="knowledge-more-list">
          <span className="kg-muted">Also here: </span>
          {groupLabels(ego.moreItems.map((item) => item.label)).join(", ")}
        </p>
      )}
      <div className="kg-focus" aria-live="polite">
        {focused ? (
          <>
            <span className="kg-tag">{mainType(focused.types) || "more"}</span>
            <span className="kg-focus-name">{focused.role === "more" ? `${ego?.more} more things in this room` : (focused.text ?? focused.label)}</span>
          </>
        ) : (
          room && (
            <>
              <span className="kg-tag" data-testid="knowledge-room-type">
                {mainType(room.types)}
              </span>
              <span className="kg-focus-name kg-muted">Brick / RealEstateCore · tap a node</span>
            </>
          )
        )}
      </div>
      <div className="kg-time">
        <div className="kg-time-row">
          <span className="tiny-label">Time</span>
          <strong data-testid="knowledge-time">{momentLabel(at, now)}</strong>
          {Math.abs(at - now) >= HOUR_MS && (
            <button type="button" className="link kg-link" onClick={() => setAt(now)}>
              Back to now
            </button>
          )}
        </div>
        <input
          type="range"
          aria-label="Time"
          data-testid="knowledge-slider"
          min={range.min}
          max={range.max}
          step={HOUR_MS}
          value={Math.min(Math.max(at, range.min), range.max)}
          onChange={(event) => setAt(Number(event.target.value))}
        />
        <div className="kg-time-ends kg-muted">
          <span>{momentLabel(range.min, now)}</span>
          <span>+{Math.round((range.max - now) / DAY_MS)} days</span>
        </div>
      </div>
      <ol className="kg-facts" data-testid="knowledge-facts">
        {facts.length === 0 && <li className="kg-muted">No notes here at this time.</li>}
        {facts.map((fact) => (
          <li key={fact.id} className={fact.state === "ended" ? "ended" : ""} data-kind={fact.role}>
            <span className={`kg-num ${fact.role}`}>{fact.number}</span>
            <span className="kg-fact-text">
              {fact.text}
              <span className="kg-muted">
                {" "}
                {fact.role === "event" ? "· Event " : ""}· {fact.anchor}
                {fact.person ? ` · ${fact.person}` : ""}
                {fact.state === "ended" ? " · ended" : ""}
              </span>
            </span>
          </li>
        ))}
      </ol>
      <div className="kg-foot">
        <label className="kg-check">
          <input type="checkbox" checked={showEnded} onChange={(event) => setShowEnded(event.target.checked)} />
          Show ended
        </label>
        <a className="kg-link" data-testid="knowledge-aas" href={`/api/graph?key=${key}&format=aas`} download={`${safeKey}-aas.json`}>
          Export as AAS
        </a>
      </div>
    </section>
  );
}

const RADIUS: Record<number, number> = { 0: ROOM_R, 1: ASSET_R, 2: FACT_R, 3: PERSON_R };

/** "Door to Hall, Door to Hall, Chair" -> ["Door to Hall x2", "Chair"] (first appearance order). */
function groupLabels(labels: string[]): string[] {
  const counts = new Map<string, number>();
  for (const label of labels) counts.set(label, (counts.get(label) ?? 0) + 1);
  return [...counts].map(([label, count]) => (count > 1 ? `${label} ×${count}` : label));
}

function GraphNode({ node, focused, onFocus }: { node: EgoNode; focused: boolean; onFocus: (id: string | null) => void }) {
  const r = RADIUS[node.ring];
  const select = () => onFocus(focused ? null : node.id);
  const classes = ["kg-node", node.role, node.state === "ended" ? "ended" : "", focused ? "focused" : "", node.hasFacts ? "has-facts" : ""].join(" ");
  // Ring 1 labels sit beside the node on the outside (left of the left half, right of the right half), up to two lines,
  // never cut; the small type line only where it matters (things with notes) or on focus.
  const right = node.side !== "left";
  const dx = right ? r + 5 : -(r + 5);
  const anchor = right ? "start" : "end";
  const rows: Array<{ text: string; cls: string }> = (node.lines ?? []).map((text) => ({ text, cls: "kg-label" }));
  if (node.ring === 1 && node.role !== "more" && (node.hasFacts || focused)) rows.push({ text: mainType(node.types), cls: "kg-type" });
  const heights = rows.map((row) => (row.cls === "kg-type" ? TYPE_H : LINE_H));
  const total = heights.reduce((sum, h) => sum + h, 0);
  let cursor = -total / 2;
  const placed = rows.map((row, i) => {
    const y = cursor + heights[i] / 2;
    cursor += heights[i];
    return { ...row, y };
  });
  return (
    <g
      className={classes}
      transform={`translate(${node.x.toFixed(1)} ${node.y.toFixed(1)})`}
      tabIndex={0}
      role="button"
      aria-label={`${node.text ?? node.label}, ${mainType(node.types) || "more"}`}
      data-id={node.id}
      onClick={select}
      onKeyDown={(event) => (event.key === "Enter" || event.key === " ") && select()}
    >
      <title>{`${node.text ?? node.label}\n${node.types.join(", ")}`}</title>
      <circle r={r + 8} className="kg-hit" />
      {node.ring === 2 ? <rect x={-r} y={-r} width={2 * r} height={2 * r} rx={node.role === "note" ? 3 : r} /> : <circle r={r} />}
      {node.role === "closure" && <line className="kg-bar" x1={-r} y1={r} x2={r} y2={-r} />}
      {node.ring === 2 && <text className="kg-num-text" dy="0.35em">{node.label}</text>}
      {node.role === "person" && <text className="kg-initial" dy="0.35em">{node.label.slice(0, 1).toUpperCase()}</text>}
      {node.ring === 1 &&
        placed.map((row) => (
          <text key={`${row.cls}${row.text}`} className={row.cls} x={dx} y={row.y} dy="0.35em" style={{ textAnchor: anchor }}>
            {row.text}
          </text>
        ))}
      {node.role === "person" &&
        (node.lines ?? []).map((line, i) => (
          <text key={line} className="kg-label" y={r + 10 + i * LINE_H}>
            {line}
          </text>
        ))}
    </g>
  );
}
