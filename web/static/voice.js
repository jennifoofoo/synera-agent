// Voice for the chat: push-to-talk in (browser Web Speech API), replies out (ElevenLabs via /api/speak,
// browser voice as fallback). Contract: docs/specs/voice-spike.md, section API. Uses app.js globals.
"use strict";

window.voice = (() => {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;
  const LANGS = { en: "en-US", de: "de-DE" };
  const ANSWER_LINE = /^\s*(?:[-*]\s*)?(?:\*\*)?answer(?:\*\*)?\s*:\s*(.*)$/i;
  // Replies that wait for the person: the understanding card or a plain question at the end.
  const CARD = /i understood|effect on your last route|waiting for the person's yes|ich habe verstanden|shall i|should i|soll ich|confirm|bestätig|\byes\b|\bja\b/i;

  const store = {
    get: (key) => { try { return localStorage.getItem(`voice.${key}`); } catch { return null; } },
    set: (key, value) => { try { localStorage.setItem(`voice.${key}`, value); } catch { /* private mode */ } },
  };

  const v = {
    mode: "idle",          // idle | listening | thinking | speaking
    recognition: null,
    heard: "",
    aborted: false,
    audio: null,
    audioUrl: null,
    token: 0,              // bumps on every stop, so late audio from an old request never plays
    muted: store.get("muted") === "1",
    lang: store.get("lang") === "de" ? "de" : "en",
    fromVoice: false,      // the last question was spoken: listen again after a spoken question back
    warnedServer: false,
  };

  const mic = $("#mic");
  const out = $("#voice-out");
  const stopButton = $("#voice-stop");
  const langSelect = $("#voice-lang");

  // ---------- UI state ----------

  function setMode(mode, status = "") {
    v.mode = mode;
    mic.classList.toggle("listening", mode === "listening");
    mic.setAttribute("aria-pressed", String(mode === "listening"));
    mic.title = mode === "listening" ? "Stop listening and send" : "Speak your question";
    stopButton.hidden = mode !== "speaking" && mode !== "listening";
    stopButton.textContent = mode === "listening" ? "■ Cancel" : "■ Stop";
    $("#chat-input").placeholder = mode === "listening" ? "Listening… speak now" : "e.g. How do I get from the entrance to the lab without stairs?";
    setStatus(status || { listening: "Listening…", speaking: "Speaking…" }[mode] || "");
  }

  function setStatus(text, bad = false) {
    const box = $("#voice-status");
    box.textContent = text;
    box.classList.toggle("bad", bad);
  }

  function refresh() {
    out.setAttribute("aria-pressed", String(!v.muted));
    out.classList.toggle("muted", v.muted);
    out.querySelector(".label").textContent = v.muted ? "Voice off" : "Voice on";
    langSelect.value = v.lang;
    const server = app.status.speech_available;
    out.title = v.muted
      ? "Replies are not read aloud. Click to turn voice on."
      : server
        ? "Replies are read aloud (ElevenLabs). Click to mute."
        : "Replies are read aloud with the browser voice: no ElevenLabs key on the server. Click to mute.";
    const input = !Recognition
      ? "Voice input needs Chrome or Edge, type instead."
      : !window.isSecureContext
        ? "Voice input needs http://127.0.0.1 or localhost."
        : "Tap the mic, speak, and it sends when you pause.";
    const output = server ? "Replies: ElevenLabs voice." : "Replies: browser voice (no ElevenLabs key on the server).";
    $("#voice-note").textContent = `${input} ${output}`;
    mic.classList.toggle("unsupported", !Recognition || !window.isSecureContext);
  }

  // ---------- speech in ----------

  function startListening() {
    if (!Recognition) return explainNoInput("Voice input needs Chrome or Edge (Web Speech API). Type your question instead.");
    if (!window.isSecureContext) return explainNoInput("The microphone only works on http://127.0.0.1 or localhost. Type your question instead.");
    stopPlayback();
    const recognition = new Recognition();
    recognition.lang = LANGS[v.lang];
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;
    v.recognition = recognition;
    v.heard = "";
    v.aborted = false;
    recognition.onresult = (event) => {
      v.heard = [...event.results].map((result) => result[0].transcript).join(" ").trim();
      $("#chat-input").value = v.heard;
    };
    recognition.onerror = (event) => {
      const messages = {
        "not-allowed": "Microphone blocked: allow it in the address bar, then try again.",
        "service-not-allowed": "Microphone blocked: allow it in the address bar, then try again.",
        "no-speech": "I didn't hear anything. Tap the mic and try again.",
        "audio-capture": "No microphone found.",
        network: "Voice input needs internet (the browser sends the audio to its speech service). Type instead.",
        "language-not-supported": "This browser cannot recognise that language.",
      };
      if (event.error !== "aborted") setStatus(messages[event.error] || `Voice input failed (${event.error}).`, true);
      v.aborted = true;
    };
    recognition.onend = () => {
      if (v.recognition !== recognition) return;
      v.recognition = null;
      const text = v.heard;
      const failed = v.aborted;
      if (v.mode === "listening") setMode("idle", failed ? $("#voice-status").textContent : "");
      if (failed || !text) {
        if (!failed && !text) setStatus("I didn't catch that. Tap the mic and try again.", true);
        return;
      }
      $("#chat-input").value = "";
      v.fromVoice = true;
      sendChat(text);
    };
    try {
      recognition.start();
      setMode("listening");
    } catch (error) {
      v.recognition = null;
      setStatus(`Voice input failed: ${error.message}`, true);
    }
  }

  function stopListening(send) {
    if (!v.recognition) return;
    if (send) v.recognition.stop();
    else {
      v.aborted = true;
      v.recognition.abort();
      $("#chat-input").value = "";
    }
    if (!send) setMode("idle");
  }

  function explainNoInput(text) {
    setStatus(text, true);
    $("#chat-input").focus();
  }

  // ---------- speech out ----------

  // What the server should shorten: the reply, or only the value when the reply is just "Answer: ...".
  function textForSpeech(reply) {
    const lines = String(reply).split("\n");
    const prose = lines.filter((line) => line.trim() && !ANSWER_LINE.test(line));
    if (prose.length) return reply;
    const answer = lines.map((line) => line.match(ANSWER_LINE)).find(Boolean);
    return answer ? answer[1].trim() : "";
  }

  // Browser-voice fallback: the same rules as web/speech.py spoken_version, in short.
  function shortForBrowser(reply) {
    const prose = [];
    const steps = [];
    for (const raw of String(reply).split("\n")) {
      if (ANSWER_LINE.test(raw) || /^\s*\|/.test(raw) || /^\s*(?:-{3,}|\*{3,})\s*$/.test(raw)) continue;
      const line = raw.replace(/^\s*#{1,6}\s*/, "").replace(/\*\*|__|`/g, "").trim();
      const step = line.match(/^\d+[.)]\s+(.*)$/);
      if (step) steps.push(/[.!?]$/.test(step[1]) ? step[1] : step[1] + ".");
      else if (line) prose.push(line.replace(/^[-*+]\s+/, ""));
    }
    let text = [prose.join(" "), ...steps.slice(0, 3)].join(" ");
    if (steps.length > 3) {
      const more = steps.length - 3;
      text += v.lang === "de" ? ` Und ${more} weitere Schritte, siehe Bildschirm.` : ` And ${more} more step${more > 1 ? "s" : ""}, see the screen.`;
    }
    text = text
      .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/\s*\[[^\]]*\]/g, "")
      .replace(/\b(?:proc|osm|resplan|swiss)(?:-[A-Za-z0-9]+)+\b/g, "")
      .replace(/\s*\(\s*[,;]?\s*\)/g, "")
      .replace(/(\d)\s*(?:m2|m²)(?!\w)/g, v.lang === "de" ? "$1 Quadratmeter" : "$1 square metres")
      .replace(/(\d)\s*m(?![\w²])/g, v.lang === "de" ? "$1 Meter" : "$1 metres")
      .replace(/\s+([,.;:!?])/g, "$1")
      .replace(/\s{2,}/g, " ")
      .trim();
    if (text.length <= 400) return text;
    const cut = text.slice(0, 400);
    const end = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("? "), cut.lastIndexOf("! "));
    return end > 80 ? cut.slice(0, end + 1) : cut.replace(/\s+\S*$/, "") + ".";
  }

  async function speak(reply, { force = false } = {}) {
    if (v.muted && !force) return finished(reply);
    const text = textForSpeech(reply);
    if (!text) return finished(reply);
    stopPlayback();
    const token = ++v.token;
    setMode("speaking", "Preparing voice…");
    if (app.status.speech_available) {
      try {
        const response = await fetch("/api/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, lang: v.lang }),
        });
        if (token !== v.token) return;
        if (response.ok) return playAudio(await response.blob(), reply, token);
        if (response.status === 400) return finished(reply);
        const payload = await response.json().catch(() => ({}));
        if (response.status === 503) {
          app.status.speech_available = false;
          refresh();
        }
        if (!v.warnedServer) setStatus(`${payload.error || "Voice service failed"} Using the browser voice.`, true);
        v.warnedServer = true;
      } catch {
        if (token !== v.token) return;
      }
    }
    browserSpeak(reply, token);
  }

  async function playAudio(blob, reply, token) {
    if (token !== v.token) return;
    v.audioUrl = URL.createObjectURL(blob);
    v.audio = new Audio(v.audioUrl);
    v.audio.onended = () => { if (token === v.token) { releaseAudio(); finished(reply); } };
    v.audio.onerror = () => { if (token === v.token) { releaseAudio(); browserSpeak(reply, token); } };
    try {
      await v.audio.play();
      if (token === v.token) setMode("speaking");
    } catch (error) {
      if (token !== v.token) return;
      releaseAudio();
      setMode("idle");
      setStatus(error.name === "NotAllowedError" ? "The browser blocked autoplay: tap 🔊 on the reply to hear it." : "Could not play the voice.", true);
    }
  }

  function browserSpeak(reply, token) {
    if (token !== v.token) return;
    if (!synth) {
      setMode("idle");
      return setStatus("No voice output in this browser. The reply is in the chat.", true);
    }
    const utterance = new SpeechSynthesisUtterance(shortForBrowser(reply));
    utterance.lang = LANGS[v.lang];
    const voices = synth.getVoices().filter((voice) => voice.lang?.toLowerCase().startsWith(v.lang));
    utterance.voice = voices.find((voice) => voice.localService) || voices[0] || null;
    utterance.onend = () => { if (token === v.token) finished(reply); };
    utterance.onerror = () => { if (token === v.token) setMode("idle"); };
    synth.cancel();
    synth.speak(utterance);
    setMode("speaking");
  }

  function releaseAudio() {
    if (v.audio) { v.audio.onended = v.audio.onerror = null; v.audio.pause(); }
    if (v.audioUrl) URL.revokeObjectURL(v.audioUrl);
    v.audio = null;
    v.audioUrl = null;
  }

  function stopPlayback() {
    v.token += 1;
    releaseAudio();
    if (synth && (synth.speaking || synth.pending)) synth.cancel();
    if (v.mode === "speaking") setMode("idle");
  }

  // After the reply: listen again only if the question was spoken and the reply waits for an answer
  // (the mic stays off while the reply plays, so the speaker never talks into it).
  function finished(reply) {
    if (v.mode === "speaking") setMode("idle");
    const again = v.fromVoice && waitsForAnswer(reply);
    v.fromVoice = false;
    if (again) startListening();
  }

  function waitsForAnswer(reply) {
    const prose = String(reply).split("\n").filter((line) => line.trim() && !ANSWER_LINE.test(line)).join(" ").trim();
    return /\?\s*$/.test(prose);
  }

  // ---------- hooks from app.js ----------

  function beforeSend() {
    stopPlayback();
    document.querySelectorAll(".msg .quick").forEach((row) => row.remove());
  }

  function onReply(reply, message) {
    if (message) decorate(reply, message);
    speak(reply);
  }

  // Agent message: a replay button, and Yes/No buttons under a card or question that waits for a yes.
  function decorate(reply, message) {
    const say = document.createElement("button");
    say.type = "button";
    say.className = "say";
    say.title = "Read this reply aloud";
    say.setAttribute("aria-label", "Read this reply aloud");
    say.textContent = "🔊";
    say.onclick = () => { v.fromVoice = false; speak(reply, { force: true }); };
    message.appendChild(say);
    if (waitsForAnswer(reply) && CARD.test(reply)) {
      const row = document.createElement("div");
      row.className = "quick";
      for (const [label, cls] of v.lang === "de" ? [["Ja", ""], ["Nein", "secondary"]] : [["Yes", ""], ["No", "secondary"]]) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `small ${cls}`;
        button.textContent = label;
        button.onclick = () => { v.fromVoice = false; sendChat(label); };
        row.appendChild(button);
      }
      message.appendChild(row);
    }
  }

  function stop() {
    stopListening(false);
    stopPlayback();
    v.fromVoice = false;
    setMode("idle");
  }

  // ---------- wiring ----------

  mic.onclick = () => {
    if (v.mode === "listening") return stopListening(true);
    startListening();
  };
  stopButton.onclick = () => {
    v.fromVoice = false;
    if (v.mode === "listening") stopListening(false);
    else stopPlayback();
  };
  out.onclick = () => {
    v.muted = !v.muted;
    store.set("muted", v.muted ? "1" : "0");
    if (v.muted) stopPlayback();
    refresh();
  };
  langSelect.onchange = () => {
    v.lang = langSelect.value === "de" ? "de" : "en";
    store.set("lang", v.lang);
  };
  // Typing a question means the person is not talking: no auto-listening after the reply.
  $("#chat-form").addEventListener("submit", () => { if (v.mode !== "listening") v.fromVoice = false; }, true);
  if (synth) synth.getVoices(); // loads the voice list early (Chrome fills it asynchronously)
  refresh();

  return { beforeSend, onReply, refresh, stop, setMode, speak, shortForBrowser, textForSpeech, waitsForAnswer };
})();
