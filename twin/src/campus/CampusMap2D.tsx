// The site map (2D), like a map app: pale ground, buildings as light grey footprints with their names, links as
// white paths with their length, the route in blue. Tap a building = enter it; tap a link = its card.
// One finger / mouse drag pans, wheel or pinch zooms. North up, campus metres (x east, y north) -> svg (x, -y).

import { useEffect, useMemo, useRef, useState } from "react";
import type { Point } from "../api/types";
import { useTwin } from "../store";
import { boundsOf, campusPoints, groundRings, linkIcon, routeLine } from "./campusGeometry";
import { steps, useCampus } from "./campusStore";

interface ViewBox {
  cx: number;
  cy: number;
  k: number; // screen px per metre
}

const MOVE_PX = 6;

function path(points: Point[], closed = false): string {
  return points.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(2)} ${(-y).toFixed(2)}`).join(" ") + (closed ? " Z" : "");
}

export function CampusMap2D() {
  const view = useCampus((s) => s.view)!;
  const details = useCampus((s) => s.details);
  const route = useCampus((s) => s.route);
  const step = useCampus((s) => s.step);
  const selectedLink = useCampus((s) => s.selectedLink);
  const enterBuilding = useCampus((s) => s.enterBuilding);
  const selectLink = useCampus((s) => s.selectLink);
  const bottomInset = useTwin((s) => s.bottomInset);
  const dismissReply = useTwin((s) => s.dismissReply);

  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [vb, setVb] = useState<ViewBox | null>(null);
  const moved = useRef(false);
  const pointers = useRef(new Map<number, Point>());
  const gesture = useRef<{ start: ViewBox; mid: Point; dist: number; origin: Point } | null>(null);

  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setSize({ w: element.clientWidth, h: element.clientHeight }));
    observer.observe(element);
    setSize({ w: element.clientWidth, h: element.clientHeight });
    return () => observer.disconnect();
  }, []);

  // The dock (card + input) covers the bottom; frame the site above it.
  const [dockH, setDockH] = useState(90);
  useEffect(() => {
    const dock = document.querySelector<HTMLElement>(".dock");
    if (!dock) return;
    const observer = new ResizeObserver(() => setDockH(Math.round(window.innerHeight - dock.getBoundingClientRect().top)));
    observer.observe(dock);
    return () => observer.disconnect();
  }, []);

  const legs = steps(route);
  const line = useMemo(() => (route?.ok && route.legs ? routeLine(view, route.legs) : []), [view, route]);
  const routeBuildings = new Set(route?.ok ? route.buildings : []);
  const routeLinks = new Set(route?.ok ? route.links_used : []);
  const activeLeg = step !== null ? legs[step] : undefined;

  // Fit everything above the dock and below the top bar, once the outlines are there.
  const loadedCount = Object.keys(details).length;
  const fit = useMemo<ViewBox>(() => {
    const b = boundsOf(campusPoints(view, details));
    const top = 64;
    const bottom = Math.max(bottomInset, dockH, 90) + 16;
    const usableW = Math.max(size.w - Math.min(170, size.w * 0.36), 120); // room for the names beside the outlines
    const usableH = Math.max(size.h - top - bottom, 120);
    const k = Math.min(usableW / Math.max(b.maxX - b.minX, 10), usableH / Math.max(b.maxY - b.minY, 10));
    // centre of the usable area in metres: shift so the map sits between the bars
    const cy = (b.minY + b.maxY) / 2 - (bottom - top) / 2 / k;
    return { cx: (b.minX + b.maxX) / 2, cy, k };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.key, loadedCount, size.w, size.h, bottomInset, dockH]);
  useEffect(() => setVb(null), [fit]);
  const current = vb ?? fit;

  const toWorldAt = (sx: number, sy: number, at: ViewBox): Point => [(sx - size.w / 2) / at.k + at.cx, at.cy - (sy - size.h / 2) / at.k];

  // viewBox in metres (svg y = -north)
  const vw = size.w / current.k;
  const vh = size.h / current.k;
  const viewBox = `${current.cx - vw / 2} ${-current.cy - vh / 2} ${vw} ${vh}`;
  const px = 1 / current.k; // one screen pixel in metres

  const local = (event: { clientX: number; clientY: number }): Point => {
    const rect = box.current!.getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
  };

  const onPointerDown = (event: React.PointerEvent) => {
    pointers.current.set(event.pointerId, local(event));
    moved.current = false;
    startGesture();
  };
  const startGesture = () => {
    const list = [...pointers.current.values()];
    if (!list.length) return (gesture.current = null);
    const mid: Point = [list.reduce((s, p) => s + p[0], 0) / list.length, list.reduce((s, p) => s + p[1], 0) / list.length];
    const dist = list.length > 1 ? Math.hypot(list[0][0] - list[1][0], list[0][1] - list[1][1]) : 0;
    gesture.current = { start: current, mid, dist, origin: toWorldAt(mid[0], mid[1], current) };
  };
  useEffect(() => {
    const move = (event: PointerEvent) => {
      if (!pointers.current.has(event.pointerId) || !gesture.current || !box.current) return;
      pointers.current.set(event.pointerId, local(event));
      const list = [...pointers.current.values()];
      const mid: Point = [list.reduce((s, p) => s + p[0], 0) / list.length, list.reduce((s, p) => s + p[1], 0) / list.length];
      const g = gesture.current;
      if (Math.hypot(mid[0] - g.mid[0], mid[1] - g.mid[1]) > MOVE_PX) moved.current = true;
      let k = g.start.k;
      if (list.length > 1 && g.dist > 0) {
        k = clampK(g.start.k * (Math.hypot(list[0][0] - list[1][0], list[0][1] - list[1][1]) / g.dist));
        moved.current = true;
      }
      // keep the world point under the fingers' midpoint fixed
      setVb({ k, cx: g.origin[0] - (mid[0] - size.w / 2) / k, cy: g.origin[1] + (mid[1] - size.h / 2) / k });
    };
    const up = (event: PointerEvent) => {
      if (!pointers.current.delete(event.pointerId)) return;
      startGesture();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
  });
  const clampK = (k: number) => Math.min(Math.max(k, fit.k * 0.4), fit.k * 12);
  const onWheel = (event: React.WheelEvent) => {
    const [sx, sy] = local(event);
    const origin = toWorldAt(sx, sy, current);
    const k = clampK(current.k * Math.exp(-event.deltaY * 0.0015));
    setVb({ k, cx: origin[0] - (sx - size.w / 2) / k, cy: origin[1] + (sy - size.h / 2) / k });
  };

  const tap = (action: () => void) => (event: React.MouseEvent) => {
    event.stopPropagation();
    if (!moved.current) action();
  };

  const start = line[0];
  const end = line[line.length - 1];
  const labelSize = 13 * px;
  const smallSize = 11.5 * px;

  return (
    <div className="campus-map" ref={box} onPointerDown={onPointerDown} onWheel={onWheel} onClick={tap(() => selectLink(null))}>
      <svg width={size.w} height={size.h} viewBox={viewBox} role="img" aria-label={`Site map of ${view.name}`}>
        {/* buildings */}
        {view.buildings.map((building) => {
          const rings = groundRings(building, details[building.id]);
          const onRoute = routeBuildings.has(building.id);
          const active = activeLeg?.kind === "building" && activeLeg.building_id === building.id;
          return (
            <g
              key={building.id}
              className={`campus-building ${onRoute ? "on-route" : ""} ${active ? "active" : ""} ${building.page_key ? "" : "no-map"}`}
              onClick={tap(() => void enterBuilding(building.id))}
              role="button"
              aria-label={`Open ${building.name}`}
            >
              {rings.map((ring, index) => (
                <path key={index} d={path(ring, true)} vectorEffect="non-scaling-stroke" />
              ))}
            </g>
          );
        })}

        {/* links: white paths with a grey casing; closed ones red */}
        {view.links.map((link) => {
          if (!link.from.world_point || !link.to.world_point) return null;
          const d = path([link.from.world_point, link.to.world_point]);
          const width = Math.max((link.width_m ?? 2.5) * 1, 5 * px);
          const cls = `campus-link ${link.kind} ${link.closed ? "closed" : ""} ${routeLinks.has(link.id) ? "on-route" : ""} ${selectedLink === link.id ? "selected" : ""}`;
          return (
            <g key={link.id} className={cls} onClick={tap(() => (selectLink(link.id), dismissReply()))} role="button" aria-label={`${link.name}, ${Math.round(link.length_m)} m`}>
              <path className="hit" d={d} strokeWidth={22 * px} />
              <path className="casing" d={d} strokeWidth={width + 2.5 * px} />
              <path className="road" d={d} strokeWidth={width} />
            </g>
          );
        })}

        {/* a bigger tap target around each building's centre (small buildings, link ends nearby) */}
        {view.buildings.map((building) =>
          building.world_center ? (
            <circle
              key={building.id}
              className="campus-building-hit"
              cx={building.world_center[0]}
              cy={-building.world_center[1]}
              r={22 * px}
              onClick={tap(() => void enterBuilding(building.id))}
            />
          ) : null,
        )}

        {/* route */}
        {line.length > 1 && (
          <g className="campus-route" pointerEvents="none">
            <path className="casing" d={path(line)} strokeWidth={9 * px} />
            <path className="line" d={path(line)} strokeWidth={6 * px} />
            {activeLeg?.kind === "link" && activeLeg.from.world_point && activeLeg.to.world_point && (
              <path className="active" d={path([activeLeg.from.world_point, activeLeg.to.world_point])} strokeWidth={6 * px} />
            )}
          </g>
        )}

        {/* entrances */}
        {view.buildings.flatMap((building) =>
          building.entrances
            .filter((entrance) => entrance.world_position)
            .map((entrance) => (
              <circle key={entrance.id} className="campus-entrance" cx={entrance.world_position![0]} cy={-entrance.world_position![1]} r={2.6 * px} vectorEffect="non-scaling-stroke" pointerEvents="none" />
            )),
        )}

        {start && (
          <g pointerEvents="none">
            <circle cx={start[0]} cy={-start[1]} r={9 * px} fill="rgba(0,79,171,0.2)" />
            <circle cx={start[0]} cy={-start[1]} r={5.5 * px} fill="#004fab" stroke="#fbfaf8" strokeWidth={2 * px} />
          </g>
        )}
        {end && line.length > 1 && (
          <g pointerEvents="none" transform={`translate(${end[0]} ${-end[1]}) scale(${px})`}>
            <path d="M0 0 C -2 -6 -9 -10 -9 -17 A 9 9 0 1 1 9 -17 C 9 -10 2 -6 0 0 Z" fill="#004fab" stroke="#002478" strokeWidth={1} />
            <circle cx={0} cy={-17} r={3.4} fill="#002478" />
          </g>
        )}

        {/* labels: names on the buildings, length on the links (screen-size text) */}
        {view.links.map((link) => {
          if (!link.from.world_point || !link.to.world_point) return null;
          const mx = (link.from.world_point[0] + link.to.world_point[0]) / 2;
          const my = (link.from.world_point[1] + link.to.world_point[1]) / 2;
          const icon = linkIcon(link.kind);
          const text = `${icon ? icon + " " : ""}${link.name} · ${Math.round(link.length_m)} m${link.level_delta ? ` · ${link.level_delta > 0 ? "+" : ""}${link.level_delta} floor` : ""}${link.closed ? " · closed" : ""}`;
          return (
            <text key={link.id} className={`campus-label link ${link.closed ? "closed" : ""}`} x={mx} y={-my + 16 * px} fontSize={smallSize} textAnchor="middle" pointerEvents="none">
              {text}
            </text>
          );
        })}
        {view.buildings.map((building) =>
          building.world_center ? (
            <text
              key={building.id}
              className="campus-label building"
              x={building.world_center[0]}
              y={-building.world_center[1]}
              fontSize={labelSize}
              textAnchor="middle"
              onClick={tap(() => void enterBuilding(building.id))}
            >
              <tspan x={building.world_center[0]}>{building.name}</tspan>
              <tspan x={building.world_center[0]} dy={15 * px} className="sub" fontSize={smallSize}>
                {building.floor_count === 1 ? "1 floor" : `${building.floor_count} floors`}
              </tspan>
            </text>
          ) : null,
        )}
      </svg>
      {vb && (
        <button className="campus-recenter" onClick={(event) => (event.stopPropagation(), setVb(null))} aria-label="Show the whole site" title="Show the whole site">
          ◎
        </button>
      )}
    </div>
  );
}
