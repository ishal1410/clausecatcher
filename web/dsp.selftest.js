/**
 * dsp.selftest.js — assert-based self-check for dsp.js. No test framework,
 * no network, no mic/server. Run via web/dev-check.html or app.js?selftest=1.
 * Each test returns {name, pass, detail}; runAll() never throws.
 */
import {
  downsampleBuffer,
  floatTo16BitPCM,
  int16ToFloat32,
  int16ArrayToBase64,
  base64ToInt16Array,
  nextScheduleTime,
  simulateSchedule,
} from "./dsp.js";

function test(name, fn) {
  try {
    fn();
    return { name, pass: true };
  } catch (err) {
    return { name, pass: false, detail: err.message };
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

function makeSine(freqHz, sampleRate, durationSec, amplitude = 1) {
  const n = Math.round(sampleRate * durationSec);
  const buf = new Float32Array(n);
  for (let i = 0; i < n; i++) buf[i] = amplitude * Math.sin((2 * Math.PI * freqHz * i) / sampleRate);
  return buf;
}

function peakAbs(buf) {
  let max = 0;
  for (const v of buf) max = Math.max(max, Math.abs(v));
  return max;
}

export function runAll() {
  const results = [];

  results.push(
    test("downsampleBuffer: 48kHz->16kHz length is ~1600 for a 100ms chunk", () => {
      const input = makeSine(440, 48000, 0.1);
      const out = downsampleBuffer(input, 48000, 16000);
      assert(Math.abs(out.length - 1600) <= 5, `expected ~1600 samples, got ${out.length}`);
    }),
  );

  results.push(
    test("downsampleBuffer: preserves amplitude of a speech-band tone", () => {
      const input = makeSine(440, 48000, 0.1, 1.0);
      const out = downsampleBuffer(input, 48000, 16000);
      const peak = peakAbs(out);
      assert(peak > 0.85, `expected peak > 0.85 (box-filter low-pass shouldn't gut a 440Hz tone), got ${peak.toFixed(3)}`);
    }),
  );

  results.push(
    test("downsampleBuffer: no-op when rates match", () => {
      const input = new Float32Array([0.1, -0.2, 0.3]);
      const out = downsampleBuffer(input, 16000, 16000);
      assert(out.length === 3 && out[1] === input[1], "expected identical passthrough");
    }),
  );

  results.push(
    test("floatTo16BitPCM / int16ToFloat32: round-trip within 1 LSB", () => {
      const input = new Float32Array([-1, -0.5, 0, 0.5, 0.999]);
      const pcm = floatTo16BitPCM(input);
      const back = int16ToFloat32(pcm);
      for (let i = 0; i < input.length; i++) {
        assert(Math.abs(back[i] - input[i]) < 1 / 1000, `index ${i}: ${input[i]} -> ${back[i]}`);
      }
    }),
  );

  results.push(
    test("floatTo16BitPCM: clamps out-of-range input", () => {
      const pcm = floatTo16BitPCM(new Float32Array([2, -2]));
      assert(pcm[0] === 0x7fff && pcm[1] === -0x8000, `expected clamped extremes, got ${pcm[0]}, ${pcm[1]}`);
    }),
  );

  results.push(
    test("base64 round-trip: Int16Array survives int16ArrayToBase64/base64ToInt16Array", () => {
      const original = new Int16Array([0, 1, -1, 32767, -32768, 12345, -6789]);
      const b64 = int16ArrayToBase64(original);
      const back = base64ToInt16Array(b64);
      assert(back.length === original.length, `length mismatch: ${back.length} vs ${original.length}`);
      for (let i = 0; i < original.length; i++) {
        assert(back[i] === original[i], `index ${i}: ${original[i]} -> ${back[i]}`);
      }
    }),
  );

  results.push(
    test("nextScheduleTime: never schedules before now, no gap when queue is ahead", () => {
      assert(nextScheduleTime(5, 3) === 5, "queue tail (5) should win over now (3)");
      assert(nextScheduleTime(2, 3) === 3, "now (3) should win when queue tail (2) already passed");
    }),
  );

  results.push(
    test("simulateSchedule: back-to-back chunks queue gaplessly", () => {
      const starts = simulateSchedule([0.1, 0.1, 0.1], 5);
      assert(
        starts.every((s, i) => Math.abs(s - (5 + i * 0.1)) < 1e-9),
        `expected [5, 5.1, 5.2], got [${starts.join(", ")}]`,
      );
    }),
  );

  return results;
}
