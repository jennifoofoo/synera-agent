// Audio loudness as a 0..1 number, for the Talk button ring (see ui/Omnibox). Everything here degrades to a no-op:
// no Web Audio, no mic permission, a suspended context. Never throws.

type AudioCtor = new () => AudioContext;

const FRAME_MS = 33; // ~30 fps
let shared: AudioContext | null = null;

/** One lazily created context, shared by both helpers. Call first from inside a tap (iOS starts it suspended). */
function context(): AudioContext | null {
  if (shared && shared.state !== "closed") return shared;
  const w = window as unknown as { AudioContext?: AudioCtor; webkitAudioContext?: AudioCtor };
  const Ctor = w.AudioContext ?? w.webkitAudioContext;
  if (!Ctor) return null;
  try {
    shared = new Ctor();
  } catch {
    shared = null;
  }
  return shared;
}

/** Poll an analyser at ~30 fps: smoothed RMS (fast attack, slow release). Returns the stop function. */
function pollLevel(analyser: AnalyserNode, onLevel: (v: number) => void): () => void {
  const data = new Uint8Array(analyser.fftSize);
  let raf = 0;
  let last = 0;
  let smooth = 0;
  let stopped = false;
  const tick = (now: number) => {
    if (stopped) return;
    raf = requestAnimationFrame(tick);
    if (now - last < FRAME_MS) return;
    last = now;
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (const byte of data) {
      const v = (byte - 128) / 128;
      sum += v * v;
    }
    const target = Math.min(1, Math.sqrt(sum / data.length) * 4); // speech RMS is small, scale it up
    smooth += (target - smooth) * (target > smooth ? 0.6 : 0.2);
    onLevel(smooth);
  };
  raf = requestAnimationFrame(tick);
  return () => {
    stopped = true;
    cancelAnimationFrame(raf);
  };
}

/** Microphone loudness. Call inside a tap. Returns a stop function (a no-op when the mic is unavailable). */
export function startMicLevel(onLevel: (v: number) => void): () => void {
  let stop = () => {};
  let cancelled = false;
  const media = typeof navigator !== "undefined" ? navigator.mediaDevices : undefined;
  if (!media?.getUserMedia) return stop;
  void (async () => {
    try {
      const ctx = context();
      if (!ctx) return;
      void ctx.resume().catch(() => {});
      const stream = await media.getUserMedia({ audio: true });
      if (cancelled) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser); // not to the destination: no feedback
      const stopPoll = pollLevel(analyser, onLevel);
      stop = () => {
        stopPoll();
        stream.getTracks().forEach((track) => track.stop());
        try {
          source.disconnect();
        } catch {
          /* already gone */
        }
      };
    } catch {
      /* denied or unsupported: no ring */
    }
  })();
  return () => {
    cancelled = true;
    stop();
    stop = () => {};
  };
}

const sources = new WeakMap<HTMLMediaElement, MediaElementAudioSourceNode>();

/** Loudness of what an audio element plays. Attaches only when the context is running (a suspended context would
 * mute the element on iOS). The source is created once per element and stays connected to the speakers. */
export function startAudioElementLevel(audio: HTMLMediaElement, onLevel: (v: number) => void): () => void {
  let stop = () => {};
  let cancelled = false;
  void (async () => {
    try {
      const ctx = context();
      if (!ctx) return;
      await ctx.resume().catch(() => {});
      if (cancelled || ctx.state !== "running") return;
      let source = sources.get(audio);
      if (!source) {
        source = ctx.createMediaElementSource(audio);
        sources.set(audio, source);
        source.connect(ctx.destination); // the element is silent unless reconnected
      }
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      const stopPoll = pollLevel(analyser, onLevel);
      const node = source;
      stop = () => {
        stopPoll();
        try {
          node.disconnect(analyser);
        } catch {
          /* already gone */
        }
      };
    } catch {
      /* no Web Audio: the caller keeps the synthetic breathing */
    }
  })();
  return () => {
    cancelled = true;
    stop();
    stop = () => {};
  };
}
