// Platform wording for voice problems (owner: mobile session). Omnibox shows the text; this only words it.

export function isIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  return /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.userAgent.includes("Macintosh") && navigator.maxTouchPoints > 1);
}

function iosOtherBrowser(): boolean {
  return isIOS() && /CriOS|FxiOS|EdgiOS|OPiOS/.test(navigator.userAgent);
}

/** One or two short sentences telling the person what to do when voice input cannot start.
 * `error` is the SpeechRecognition error code (not-allowed, service-not-allowed, audio-capture, network, …)
 * or undefined when the browser has no speech recognition at all. */
export function voiceHint(error?: string): string {
  if (typeof window !== "undefined" && !window.isSecureContext) return "Voice needs a secure link (https). Open the tunnel address instead.";
  const ios = isIOS();
  if (!error) {
    if (iosOtherBrowser()) return "Voice works in Safari. Open this page in Safari, or type your question.";
    if (ios) return "Voice is not available here. Tap the keyboard's mic to dictate, or type your question.";
    return "Voice input needs Chrome or Safari. You can type your question.";
  }
  if (error === "not-allowed") {
    return ios
      ? "Microphone is blocked. Tap ᴀA › Website Settings › Microphone › Allow, then tap the mic again."
      : "Microphone is blocked. Allow it in this site's settings (the icon left of the web address), then tap the mic again.";
  }
  if (error === "service-not-allowed") {
    return ios
      ? "Speech recognition is off. Turn on Settings › General › Keyboard › Enable Dictation, then tap the mic again."
      : "Speech recognition is not allowed in this browser. You can type your question.";
  }
  if (error === "audio-capture") return "No microphone found. Check that no other app is using it.";
  if (error === "network") return "Speech recognition needs a connection. Try again or type.";
  return "Didn't catch that. Tap the mic and speak again.";
}
