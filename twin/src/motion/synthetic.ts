import type { AccelSample } from "./types";

/** Synthetic accelerometer traces for tests and the desktop simulation (`window.__walkSim`). */

const G = 9.81;

/** Deterministic pseudo random numbers (mulberry32) so tests do not flake. */
export function seededRandom(seed = 1): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Roughly normal noise (sum of uniforms). */
export function gaussian(random: () => number): number {
  return random() + random() + random() + random() - 2;
}

export interface TraceOptions {
  durationS: number;
  rateHz?: number;
  startMs?: number;
  noise?: number; // m/s^2, per axis
  seed?: number;
}

/** One sample of walking at `stepsPerSecond`: gravity on z plus a vertical bounce per step and a sway. */
export function walkingSample(tMs: number, stepsPerSecond: number, amplitude = 2.5): AccelSample {
  const phase = 2 * Math.PI * stepsPerSecond * (tMs / 1000);
  return {
    t: tMs,
    x: 0.6 * Math.sin(phase / 2),
    y: 0.4 * Math.cos(phase),
    z: G + amplitude * Math.sin(phase),
  };
}

export function walkingTrace(stepsPerSecond: number, o: TraceOptions): AccelSample[] {
  return trace(o, (t) => walkingSample(t, stepsPerSecond));
}

export function standingTrace(o: TraceOptions): AccelSample[] {
  return trace(o, (t) => ({ t, x: 0, y: 0, z: G }));
}

/** Shaking the phone in the hand: fast and strong. */
export function shakeTrace(o: TraceOptions & { shakeHz?: number; amplitude?: number }): AccelSample[] {
  const hz = o.shakeHz ?? 8;
  const amplitude = o.amplitude ?? 12;
  return trace(o, (t) => {
    const phase = 2 * Math.PI * hz * (t / 1000);
    return { t, x: amplitude * Math.sin(phase), y: 0.5 * amplitude * Math.cos(phase), z: G + amplitude * Math.sin(phase + 1) };
  });
}

function trace(o: TraceOptions, shape: (tMs: number) => AccelSample): AccelSample[] {
  const rate = o.rateHz ?? 50;
  const start = o.startMs ?? 0;
  const random = seededRandom(o.seed ?? 7);
  const noise = o.noise ?? 0.3;
  const samples: AccelSample[] = [];
  const count = Math.round(o.durationS * rate);
  for (let i = 0; i < count; i++) {
    const s = shape(start + (i * 1000) / rate);
    samples.push({
      t: s.t,
      x: s.x + noise * gaussian(random),
      y: s.y + noise * gaussian(random),
      z: s.z + noise * gaussian(random),
    });
  }
  return samples;
}
