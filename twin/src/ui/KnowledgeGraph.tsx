// Knowledge panel (docs/specs/knowledge-graph-view.md): the ego graph of one room from GET /api/graph (JSON-LD with
// Brick/RealEstateCore types) as plain SVG, a time slider that filters the place notes by validFrom/validTo, and the
// Asset Administration Shell export. Opened by the "Knowledge" button in the room card. Desktop: side panel; phone:
// bottom sheet. Layout and time rules live in egoGraph.ts.

import { useEffect, useMemo, useRef, useState } from "react";
import { create } from "zustand";
import { useTwin } from "../store";
import { DAY_MS, HOUR_MS, egoGraph, mainType, momentLabel, timeRange, type EgoNode, type LdNode } from "./egoGraph";
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

/** The entry in the room card. */
export function KnowledgeButton({ roomId }: { roomId: string }) {
  return (
    <button data-testid="knowledge-open" onClick={() => openKnowledge(roomId)}>
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
  const height = phone ? Math.min(340, Math.round(width * 0.92)) : width;
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

  const ego = useMemo(() => (graph ? egoGraph(graph, roomId, { at, showEnded, width, height }) : null), [graph, roomId, at, showEnded, width, height]);
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
        <button className="x" onClick={closeKnowledge} aria-label="Close knowledge graph">
          ×
        </button>
      </div>
      <div className="kg-graph" ref={box}>
        {error && <p className="kg-muted">Graph not available ({error}).</p>}
        {!error && !ego && <p className="kg-muted">Loading graph…</p>}
        {ego && ego.nodes.length === 0 && <p className="kg-muted">This room is not in the graph.</p>}
        {ego && ego.nodes.length > 0 && (
          <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Ego graph of ${room?.label}`} data-testid="knowledge-svg">
            <g className="kg-edges">
              {ego.edges.map((edge) => {
                const from = byId.get(edge.from);
                const to = byId.get(edge.to);
                if (!from || !to) return null;
                return <line key={`${edge.from}>${edge.to}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} className={edge.faded ? "faded" : ""} />;
              })}
            </g>
            {ego.nodes.map((node) => (
              <GraphNode key={node.id} node={node} focused={focus === node.id} onFocus={setFocus} width={width} />
            ))}
          </svg>
        )}
      </div>
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
            <button className="link kg-link" onClick={() => setAt(now)}>
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
                · {fact.anchor}
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

const RADIUS: Record<number, number> = { 0: 22, 1: 7, 2: 10, 3: 12 };

function GraphNode({ node, focused, onFocus, width }: { node: EgoNode; focused: boolean; onFocus: (id: string | null) => void; width: number }) {
  const r = RADIUS[node.ring];
  const cx = width / 2;
  const right = node.x >= cx;
  const select = () => onFocus(focused ? null : node.id);
  const classes = ["kg-node", node.role, node.state === "ended" ? "ended" : "", focused ? "focused" : "", node.hasFacts ? "has-facts" : ""].join(" ");
  // Ring 1 labels only where they matter (things with notes) or on focus; else the circle alone keeps it calm.
  const showLabel = node.ring !== 1 || node.hasFacts || focused || node.role === "more";
  const dx = node.ring === 1 && node.role !== "more" ? (right ? r + 4 : -(r + 4)) : 0;
  return (
    <g
      className={classes}
      transform={`translate(${node.x.toFixed(1)} ${node.y.toFixed(1)})`}
      tabIndex={0}
      role="button"
      aria-label={`${node.text ?? node.label}, ${mainType(node.types)}`}
      data-id={node.id}
      onClick={select}
      onKeyDown={(event) => (event.key === "Enter" || event.key === " ") && select()}
    >
      <title>{`${node.text ?? node.label}\n${node.types.join(", ")}`}</title>
      <circle r={r + 8} className="kg-hit" />
      {node.role === "person" ? <circle r={r} /> : node.role === "more" ? <circle r={r + 6} /> : node.ring === 2 ? <rect x={-r} y={-r} width={2 * r} height={2 * r} rx={node.role === "note" ? 3 : r} /> : <circle r={r} />}
      {node.role === "closure" && <line className="kg-bar" x1={-r} y1={r} x2={r} y2={-r} />}
      {node.ring === 2 && <text className="kg-num-text" dy="0.35em">{node.label}</text>}
      {node.role === "person" && <text className="kg-initial" dy="0.35em">{node.label.slice(0, 1).toUpperCase()}</text>}
      {node.role === "more" && <text className="kg-more-text" dy="0.35em">{node.label}</text>}
      {node.ring === 1 && node.role !== "more" && showLabel && (
        <>
          <text className="kg-label" x={dx} dy="-0.1em" textAnchor={right ? "start" : "end"}>
            {clip(node.label, 16)}
          </text>
          <text className="kg-type" x={dx} dy="1.1em" textAnchor={right ? "start" : "end"}>
            {mainType(node.types)}
          </text>
        </>
      )}
      {node.role === "person" && (
        <text className="kg-label" y={r + 12}>
          {node.label}
        </text>
      )}
    </g>
  );
}

function clip(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
