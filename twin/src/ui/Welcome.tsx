import { useEffect, useMemo, useState } from "react";
import { useCampus } from "../campus/campusStore";
import { spaceGroup } from "../model/palette";
import { useTwin } from "../store";
import "./Welcome.css";

/** First screen: a welcome card with questions this building can actually answer. Gone for good after the first interaction. */
export function Welcome() {
  const model = useTwin((s) => s.model);
  const name = useTwin((s) => s.building?.name);
  const chatCount = useTwin((s) => s.chat.length);
  const routed = useTwin((s) => !!s.state?.route?.ok);
  const selected = useTwin((s) => s.selection !== null);
  const onSite = useCampus((s) => s.mode === "site");
  const [phase, setPhase] = useState<"open" | "leaving" | "gone">("open");

  const chips = useMemo(() => {
    if (!model) return [];
    const spaces = [...model.spaceById.values()];
    const group = (s: (typeof spaces)[number]) => spaceGroup(s.type, s.room_type);
    const out: string[] = [];
    if (spaces.some((s) => group(s) === "sanitary")) out.push("Where is the nearest toilet?");
    if (spaces.some((s) => group(s) === "food")) out.push("Where can I get a coffee?");
    const named = (g: string) => spaces.find((s) => group(s) === g && s.name.trim() && s.type !== "corridor");
    const place = named("production") ?? named("meeting");
    if (place) out.push(`Where is ${place.name}?`);
    const lift = [...model.connectorById.values()].find((c) => c.kind === "lift" && c.name.trim());
    if (lift) out.push(`What if ${lift.name} is closed?`);
    return out.slice(0, 4);
  }, [model]);

  useEffect(() => {
    if (chatCount > 0 || routed || selected) setPhase((p) => (p === "open" ? "leaving" : p));
  }, [chatCount, routed, selected]);
  useEffect(() => {
    if (phase !== "open") return;
    const dismiss = () => setPhase((p) => (p === "open" ? "leaving" : p));
    const onDown = (event: PointerEvent) => {
      if (event.target instanceof Element && event.target.closest("canvas")) dismiss();
    };
    const onFocus = (event: FocusEvent) => {
      if (event.target instanceof Element && event.target.closest(".omnibox-input")) dismiss();
    };
    window.addEventListener("pointerdown", onDown, { capture: true });
    window.addEventListener("focusin", onFocus);
    window.addEventListener("wheel", dismiss, { passive: true });
    return () => {
      window.removeEventListener("wheel", dismiss);
      window.removeEventListener("pointerdown", onDown, { capture: true });
      window.removeEventListener("focusin", onFocus);
    };
  }, [phase]);
  useEffect(() => {
    if (phase !== "leaving") return;
    const timer = window.setTimeout(() => setPhase("gone"), 220);
    return () => window.clearTimeout(timer);
  }, [phase]);

  if (!model || phase === "gone" || onSite || chips.length === 0) return null;
  return (
    <div className={`welcome ${phase === "leaving" ? "leaving" : ""}`}>
      <div className="welcome-card" role="dialog" aria-label="Welcome">
        <h1 className="welcome-title">Hi, I'm Wanda. Welcome to {name ?? "the building"}.</h1>
        <p className="welcome-sub">What can I help you find?</p>
        <div className="welcome-chips">
          {chips.map((text) => (
            <button
              key={text}
              type="button"
              className="welcome-chip"
              // The card lets the map through everywhere but its chips; a scroll over a chip still zooms the map.
              onWheel={(event) => document.querySelector("canvas")?.dispatchEvent(new WheelEvent("wheel", event.nativeEvent))}
              onClick={() => {
                setPhase("leaving");
                void useTwin.getState().ask(text);
              }}
            >
              {text}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
