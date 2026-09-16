/**
 * dsp.ts — pure audio-math helpers shared by public/audio-worklet.js (mic
 * capture, runs in AudioWorkletGlobalScope) and useSession.ts (playback,
 * runs on window). No DOM, no network globals used here — that's what makes
 * these testable without a live mic or server.
 *
 * Ported 1:1 from web/dsp.js (behavior unchanged, just typed). The worklet
 * itself can't import this module (worklets load as a standalone file from
 * /public), so public/audio-worklet.js inlines its own copy of
 * downsampleBuffer/floatTo16BitPCM — keep the two in sync if this changes.
 */

/**
 * Downsample a Float32 buffer from inputRate to outputRate using box-filter
 * decimation (average the input samples that fall in each output sample's
 * window). The averaging acts as a crude low-pass filter, which is enough
 * to avoid harsh aliasing for speech-band content.
 * ponytail: not a proper windowed-sinc resampler; good enough for 16kHz
 * speech capture. Upgrade to a real FIR resampler if audio quality on a
 * device with an unusual native rate turns out to matter.
 */
export function downsampleBuffer(buffer: Float32Array, inputRate: number, outputRate = 16000): Float32Array {
  if (outputRate === inputRate) return Float32Array.from(buffer)
  if (outputRate > inputRate) throw new Error('downsampleBuffer: upsampling not supported')
  const ratio = inputRate / outputRate
  const newLength = Math.round(buffer.length / ratio)
  const result = new Float32Array(newLength)
  let offsetBuffer = 0
  for (let offsetResult = 0; offsetResult < newLength; offsetResult++) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio)
    let accum = 0
    let count = 0
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      accum += buffer[i]
      count++
    }
    result[offsetResult] = count ? accum / count : 0
    offsetBuffer = nextOffsetBuffer
  }
  return result
}

/** Float32 [-1, 1] -> Int16 PCM, clamped. */
export function floatTo16BitPCM(float32: Float32Array): Int16Array {
  const out = new Int16Array(float32.length)
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}

/** Int16 PCM -> Float32 [-1, 1], for playback via AudioBuffer. */
export function int16ToFloat32(int16: Int16Array): Float32Array {
  const out = new Float32Array(int16.length)
  for (let i = 0; i < int16.length; i++) {
    out[i] = int16[i] < 0 ? int16[i] / 0x8000 : int16[i] / 0x7fff
  }
  return out
}

/** Int16Array -> base64 string. Requires btoa (window context only). */
export function int16ArrayToBase64(int16: Int16Array): string {
  const bytes = new Uint8Array(int16.buffer, int16.byteOffset, int16.byteLength)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary)
}

/** base64 string -> Int16Array. Requires atob (window context only). */
export function base64ToInt16Array(b64: string): Int16Array {
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  // byteOffset 0 and byteLength is always even here (PCM16), so this is safe.
  return new Int16Array(bytes.buffer)
}

/** Gapless scheduling: next chunk starts at max(queue tail, "now"). */
export function nextScheduleTime(nextStartTime: number, currentTime: number): number {
  return Math.max(nextStartTime, currentTime)
}

/**
 * Pure simulation of gapless playback scheduling, for testing the math
 * without a real AudioContext. durationsSec: array of chunk durations in
 * seconds. Returns the start time (seconds) assigned to each chunk.
 */
export function simulateSchedule(durationsSec: number[], currentTime = 0): number[] {
  let nextStart = currentTime
  const starts: number[] = []
  for (const d of durationsSec) {
    const start = nextScheduleTime(nextStart, currentTime)
    starts.push(start)
    nextStart = start + d
  }
  return starts
}

/** RMS (0-1) of a PCM16 chunk, for the agent/mic level visualizers. */
export function rmsLevel(int16: Int16Array): number {
  if (int16.length === 0) return 0
  let sumSq = 0
  for (let i = 0; i < int16.length; i++) {
    const v = int16[i] / 0x8000
    sumSq += v * v
  }
  return Math.min(1, Math.sqrt(sumSq / int16.length))
}
