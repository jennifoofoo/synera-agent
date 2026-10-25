import { useEffect } from "react";
import { KEY_CONTROLS, MOUSE_CONTROLS, useKeyHelp } from "../scene/controlsTable";
import { PoiBadge, POI_LEGEND } from "../scene/poiIcons";
import { AllFloorsIcon, ResetViewIcon } from "./FloorRail";
import * as palette from "../model/palette";

/** Room colours from palette.ts (LEGEND_GROUPS, added by the room-colours branch); none while it is not merged. */
function roomColours(): { label: string; colour: string }[] {
  const groups = (palette as Record<string, unknown>).LEGEND_GROUPS;
  if (!Array.isArray(groups)) return [];
  return groups.flatMap((group: unknown) => {
    const g = group as Record<string, unknown>;
    const label = g.label ?? g.name ?? g.title;
    const colour = g.colour ?? g.color ?? g.fill;
    return typeof label === "string" && typeof colour === "string" ? [{ label, colour }] : [];
  });
}
import "./KeyHelp.css";

/** Small help card (? or H, or the ? button under the floor rail): controls and the map symbols. Closes with Esc or
 * any other key. Laptop and tablet only. */
export function KeyHelp() {
  const open = useKeyHelp((s) => s.open);
  const setOpen = useKeyHelp((s) => s.setOpen);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (["Shift", "Control", "Alt", "Meta"].includes(event.key) || event.metaKey || event.ctrlKey) return;
      event.preventDefault();
      event.stopPropagation(); // the key closes the card and does nothing else
      setOpen(false);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, setOpen]);

  if (!open) return null;
  const rooms = roomColours();
  return (
    <>
    <div className="keyhelp-backdrop" onPointerDown={() => setOpen(false)} aria-hidden />
    <div className="keyhelp" role="dialog" aria-label="Keyboard and mouse help">
      <button type="button" className="x keyhelp-close" aria-label="Close help" onClick={() => setOpen(false)}>
        ×
      </button>
      <h2>Controls</h2>
      <table>
        <tbody>
          {KEY_CONTROLS.map((row) => (
            <tr key={row.keys}>
              <th>{row.keys}</th>
              <td>{row.does}</td>
            </tr>
          ))}
          {MOUSE_CONTROLS.map((row) => (
            <tr key={row.keys} className="mouse">
              <th>{row.keys}</th>
              <td>{row.does}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2 className="keyhelp-symbols">Map symbols</h2>
      <ul className="keyhelp-legend">
        {POI_LEGEND.map((row) => (
          <li key={row.kind}>
            <PoiBadge kind={row.kind} title={row.label} />
            <span>{row.label}</span>
          </li>
        ))}
        <li data-legend="closed">
          <PoiBadge kind="lift" title="Closed" closed />
          <span>Closed (routes go around it; a closed door gets a red bar)</span>
        </li>
        <li>
          <span className="keyhelp-icon">
            <AllFloorsIcon />
          </span>
          <span>All floors (3D, beside the floor numbers)</span>
        </li>
        <li>
          <span className="keyhelp-icon">
            <ResetViewIcon />
          </span>
          <span>Reset view: the whole building</span>
        </li>
        <li className="wide">
          <span className="keyhelp-shape" aria-hidden />
          <span>Machine, rack or furniture (darker and named: a landmark of your route)</span>
        </li>
      </ul>
      {rooms.length > 0 && (
        <>
          <h3 className="keyhelp-sub">Room colours</h3>
          <ul className="keyhelp-legend">
            {rooms.map((row) => (
              <li key={row.label}>
                <span className="keyhelp-room" style={{ background: row.colour }} aria-hidden />
                <span>{row.label}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p>Press any key or click outside to close</p>
    </div>
    </>
  );
}
