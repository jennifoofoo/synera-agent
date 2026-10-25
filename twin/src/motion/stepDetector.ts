import type { AccelSample, StepEvent } from "./types";

/** Pedestrian step detection from accelerationIncludingGravity, pure and stateful per instance (no DOM).
 *
 * Signal: |a| minus a slow baseline (gravity), low-passed at ~3 Hz. A step is a peak of that signal with
 * - a peak-to-valley swing above an adaptive threshold (half the recent swings, never below minSwing),
 * - at least minIntervalMs after the previous step,
 * - not inside a shake (energy above ~3 Hz larger than the walking band),
 * - part of a bout: the first `boutSteps` candidates must come at a walking cadence (gaps <= maxIntervalMs)
 *   before any of them counts; they are then released together. A gap > maxIntervalMs ends the bout. */

export interface StepDetectorOptions {
  lowPassHz: number;
  baselineHz: number;
  minSwing: number; // m/s^2, peak to valley
  minIntervalMs: number;
  maxIntervalMs: number;
  boutSteps: number;
  /** high-frequency energy / walking-band energy above this is a shake */
  shakeRatio: number;
}

export const DEFAULT_STEP_OPTIONS: StepDetectorOptions = {
  lowPassHz: 3,
  baselineHz: 0.3,
  minSwing: 1.0,
  minIntervalMs: 300,
  maxIntervalMs: 2000,
  boutSteps: 3,
  shakeRatio: 1.2,
};

const alpha = (dtS: number, cutoffHz: number) => {
  const rc = 1 / (2 * Math.PI * cutoffHz);
  return dtS / (rc + dtS);
};

export class StepDetector {
  private readonly o: StepDetectorOptions;
  private lastT: number | null = null;
  private baseline = 0;
  private low = 0;
  private hfEnergy = 0;
  private lfEnergy = 0;
  private prev = 0;
  private prevPrev = 0;
  private prevT = 0;
  private valley = Infinity;
  private swings: number[] = [];
  private lastStepT: number | null = null;
  private pending: number[] = []; // candidate peaks of a bout not yet confirmed
  private inBout = false;
  private intervals: number[] = [];
  private samples = 0;

  constructor(options: Partial<StepDetectorOptions> = {}) {
    this.o = { ...DEFAULT_STEP_OPTIONS, ...options };
  }

  reset(): void {
    Object.assign(this, new StepDetector(this.o));
  }

  /** Feed one sample; returns the steps it confirmed (usually none or one; a new bout releases several). */
  push(sample: AccelSample): StepEvent[] {
    const { x, y, z, t } = sample;
    if (![x, y, z, t].every(Number.isFinite)) return [];
    const magnitude = Math.hypot(x, y, z);
    if (this.lastT === null) {
      this.lastT = t;
      this.baseline = magnitude;
      this.low = 0;
      return [];
    }
    const dt = (t - this.lastT) / 1000;
    if (dt <= 0) return [];
    this.lastT = t;
    if (dt > 1) {
      // a long gap (tab in background): start over, keep nothing half-finished
      this.baseline = magnitude;
      this.low = 0;
      this.prev = this.prevPrev = 0;
      this.endBout();
      return [];
    }
    this.samples++;
    this.baseline += alpha(dt, this.o.baselineHz) * (magnitude - this.baseline);
    const centred = magnitude - this.baseline;
    this.low += alpha(dt, this.o.lowPassHz) * (centred - this.low);
    const energyAlpha = alpha(dt, 1);
    this.hfEnergy += energyAlpha * (Math.abs(centred - this.low) - this.hfEnergy);
    this.lfEnergy += energyAlpha * (Math.abs(this.low) - this.lfEnergy);

    const out: StepEvent[] = [];
    if (this.lastStepT !== null && t - this.lastStepT > this.o.maxIntervalMs) this.endBout();
    if (this.pending.length && t - this.pending[this.pending.length - 1] > this.o.maxIntervalMs) this.pending = [];

    this.valley = Math.min(this.valley, this.low);
    // peak of the low-passed signal at the previous sample
    if (this.samples > 2 && this.prev > this.prevPrev && this.prev >= this.low) {
      const peakT = this.prevT;
      const swing = this.prev - this.valley;
      if (this.isStep(peakT, swing)) {
        this.swings = [...this.swings.slice(-5), swing];
        this.valley = this.low;
        out.push(...this.accept(peakT));
      }
    }
    this.prevPrev = this.prev;
    this.prev = this.low;
    this.prevT = t;
    return out;
  }

  private threshold(): number {
    if (!this.swings.length) return this.o.minSwing;
    const mean = this.swings.reduce((a, b) => a + b, 0) / this.swings.length;
    return Math.max(this.o.minSwing, 0.5 * mean);
  }

  private isStep(peakT: number, swing: number): boolean {
    if (this.prev <= 0) return false; // a peak below the baseline is a wobble, not a step
    if (swing < this.threshold()) return false;
    const last = this.pending.length ? this.pending[this.pending.length - 1] : this.lastStepT;
    if (last !== null && peakT - last < this.o.minIntervalMs) return false;
    if (this.inBout && this.intervals.length >= 2 && last !== null) {
      // cadence sanity: a peak at well under half the usual interval is a double bump of one step
      const usual = this.intervals.reduce((a, b) => a + b, 0) / this.intervals.length;
      if (peakT - last < 0.5 * usual) return false;
    }
    if (this.hfEnergy > this.o.shakeRatio * this.lfEnergy) {
      // shaking: drop the candidate bout as well, a shake never starts one
      this.pending = [];
      return false;
    }
    return true;
  }

  private accept(peakT: number): StepEvent[] {
    if (this.inBout && this.lastStepT !== null) {
      this.intervals = [...this.intervals.slice(-3), peakT - this.lastStepT];
      this.lastStepT = peakT;
      return [{ t: peakT, cadenceHz: this.cadence() }];
    }
    this.pending.push(peakT);
    if (this.pending.length < this.o.boutSteps) return [];
    const released = this.pending;
    this.pending = [];
    this.inBout = true;
    this.intervals = released.slice(1).map((time, i) => time - released[i]);
    this.lastStepT = released[released.length - 1];
    const cadenceHz = this.cadence();
    return released.map((time) => ({ t: time, cadenceHz }));
  }

  private cadence(): number {
    if (!this.intervals.length) return 0;
    const mean = this.intervals.reduce((a, b) => a + b, 0) / this.intervals.length;
    return mean > 0 ? 1000 / mean : 0;
  }

  private endBout(): void {
    this.inBout = false;
    this.lastStepT = null;
    this.intervals = [];
    this.pending = [];
  }
}

/** All steps in a recorded or synthetic trace. */
export function detectSteps(samples: AccelSample[], options: Partial<StepDetectorOptions> = {}): StepEvent[] {
  const detector = new StepDetector(options);
  return samples.flatMap((sample) => detector.push(sample));
}

export const DEFAULT_STEP_LENGTH_M = 0.7;
const TYPICAL_CADENCE_HZ = 1.8;

/** Step length in metres: `base` at a typical cadence, a bit longer when faster, clamped to 0.5 to 0.9 m. */
export function stepLength(cadenceHz: number, base = DEFAULT_STEP_LENGTH_M, scaleByCadence = true): number {
  if (!scaleByCadence || !Number.isFinite(cadenceHz) || cadenceHz <= 0) return clamp(base, 0.5, 0.9);
  return clamp(base * (1 + 0.25 * (cadenceHz - TYPICAL_CADENCE_HZ)), 0.5, 0.9);
}

export function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}
