/**
 * dsp.test.ts — vitest port of web/dsp.selftest.js. Same assertions, same
 * math, just running under a real test runner instead of the hand-rolled
 * assert-based self-check.
 */
import { describe, expect, it } from 'vitest'
import {
  base64ToInt16Array,
  downsampleBuffer,
  floatTo16BitPCM,
  int16ArrayToBase64,
  int16ToFloat32,
  nextScheduleTime,
  simulateSchedule,
} from './dsp'

function makeSine(freqHz: number, sampleRate: number, durationSec: number, amplitude = 1): Float32Array {
  const n = Math.round(sampleRate * durationSec)
  const buf = new Float32Array(n)
  for (let i = 0; i < n; i++) buf[i] = amplitude * Math.sin((2 * Math.PI * freqHz * i) / sampleRate)
  return buf
}

function peakAbs(buf: Float32Array): number {
  let max = 0
  for (const v of buf) max = Math.max(max, Math.abs(v))
  return max
}

describe('downsampleBuffer', () => {
  it('48kHz->16kHz length is ~1600 for a 100ms chunk', () => {
    const out = downsampleBuffer(makeSine(440, 48000, 0.1), 48000, 16000)
    expect(Math.abs(out.length - 1600)).toBeLessThanOrEqual(5)
  })

  it('preserves amplitude of a speech-band tone', () => {
    const out = downsampleBuffer(makeSine(440, 48000, 0.1, 1.0), 48000, 16000)
    expect(peakAbs(out)).toBeGreaterThan(0.85)
  })

  it('no-op when rates match', () => {
    const input = new Float32Array([0.1, -0.2, 0.3])
    const out = downsampleBuffer(input, 16000, 16000)
    expect(out.length).toBe(3)
    expect(out[1]).toBe(input[1])
  })
})

describe('floatTo16BitPCM / int16ToFloat32', () => {
  it('round-trips within 1 LSB', () => {
    const input = new Float32Array([-1, -0.5, 0, 0.5, 0.999])
    const back = int16ToFloat32(floatTo16BitPCM(input))
    for (let i = 0; i < input.length; i++) {
      expect(Math.abs(back[i] - input[i])).toBeLessThan(1 / 1000)
    }
  })

  it('clamps out-of-range input', () => {
    const pcm = floatTo16BitPCM(new Float32Array([2, -2]))
    expect(pcm[0]).toBe(0x7fff)
    expect(pcm[1]).toBe(-0x8000)
  })
})

describe('base64 round-trip', () => {
  it('Int16Array survives int16ArrayToBase64/base64ToInt16Array', () => {
    const original = new Int16Array([0, 1, -1, 32767, -32768, 12345, -6789])
    const back = base64ToInt16Array(int16ArrayToBase64(original))
    expect(back.length).toBe(original.length)
    for (let i = 0; i < original.length; i++) expect(back[i]).toBe(original[i])
  })
})

describe('nextScheduleTime', () => {
  it('never schedules before now, no gap when queue is ahead', () => {
    expect(nextScheduleTime(5, 3)).toBe(5)
    expect(nextScheduleTime(2, 3)).toBe(3)
  })
})

describe('simulateSchedule', () => {
  it('back-to-back chunks queue gaplessly', () => {
    const starts = simulateSchedule([0.1, 0.1, 0.1], 5)
    starts.forEach((s, i) => expect(Math.abs(s - (5 + i * 0.1))).toBeLessThan(1e-9))
  })
})
