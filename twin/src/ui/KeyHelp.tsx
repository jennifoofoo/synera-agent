import { useEffect } from "react";
import { KEY_CONTROLS, MOUSE_CONTROLS, useKeyHelp } from "../scene/controlsTable";
import "./KeyHelp.css";

/** Small keyboard and mouse help card (? or H). Closes with Esc or any other key. Laptop and tablet only. */
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
  return (
    <div className="keyhelp" role="dialog" aria-label="Keyboard and mouse help" onPointerDown={() => setOpen(false)}>
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
      <p>Press any key to close</p>
    </div>
  );
}
