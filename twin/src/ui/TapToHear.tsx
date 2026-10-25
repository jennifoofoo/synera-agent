// "Tap to hear Wanda": shown only when the browser refused to play a spoken reply (iOS after a mic session).
// The tap is a user gesture, so playing it then always works. Logic in voice.ts (playWithRetry, playBlockedReply).

import { useSyncExternalStore } from "react";
import { playBlockedReply, replyBlocked, subscribeReplyBlocked } from "../voice";

export function TapToHear() {
  const blocked = useSyncExternalStore(subscribeReplyBlocked, replyBlocked);
  if (!blocked) return null;
  return (
    <button
      type="button"
      className="tap-to-hear"
      onClick={playBlockedReply}
      style={{
        position: "fixed",
        left: "50%",
        transform: "translateX(-50%)",
        top: "calc(var(--top-inset, 0px) + env(safe-area-inset-top, 0px) + 64px)",
        zIndex: 60,
        padding: "10px 18px",
        minHeight: 44,
        borderRadius: 999,
        border: "none",
        background: "var(--accent, #4f46e5)",
        color: "#fff",
        font: "inherit",
        fontWeight: 600,
        boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
      }}
    >
      Tap to hear Wanda
    </button>
  );
}
