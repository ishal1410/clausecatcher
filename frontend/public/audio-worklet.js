/**
 * audio-worklet.js — AudioWorkletProcessor that runs on the audio render
 * thread. Takes mono mic input at whatever rate the AudioContext gives it
 * (typically 44100/48000 Hz) and emits fixed 100ms (1600-sample) Int16 PCM
 * chunks at 16000 Hz to the main thread, matching the server's WS protocol
 * ("binary = PCM16 little-endian mono 16000 Hz, ~100 ms chunks").
 *
 * Ported from web/audio-worklet.js. Worklets are loaded via
 * audioContext.audioWorklet.addModule() as a standalone script served from
 * /public — they can't `import` from src/, so downsampleBuffer/
 * floatTo16BitPCM are inlined here rather than imported from
 * src/lib/dsp.ts. Keep this in sync with dsp.ts if that math changes.
 */

const TARGET_RATE = 16000;
const CHUNK_MS = 100;
const OUTPUT_CHUNK_SAMPLES = (TARGET_RATE * CHUNK_MS) / 1000; // 1600

// -- inlined from src/lib/dsp.ts (downsampleBuffer, floatTo16BitPCM) --------
function downsampleBuffer(buffer, inputRate, outputRate = 16000) {
  if (outputRate === inputRate) return Float32Array.from(buffer);
  if (outputRate > inputRate) throw new Error("downsampleBuffer: upsampling not supported");
  const ratio = inputRate / outputRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  let offsetBuffer = 0;
  for (let offsetResult = 0; offsetResult < newLength; offsetResult++) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      accum += buffer[i];
      count++;
    }
    result[offsetResult] = count ? accum / count : 0;
    offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

function floatTo16BitPCM(float32) {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

class MicDownsampler extends AudioWorkletProcessor {
  constructor() {
    super();
    // ponytail: plain array + splice, not a ring buffer — chunks are tiny
    // (~100ms) so this never grows large enough to matter.
    this._native = [];
    this._nativeChunkSize = Math.round((OUTPUT_CHUNK_SAMPLES * sampleRate) / TARGET_RATE);
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      for (let i = 0; i < channel.length; i++) this._native.push(channel[i]);

      while (this._native.length >= this._nativeChunkSize) {
        const nativeChunk = Float32Array.from(this._native.splice(0, this._nativeChunkSize));
        const downsampled = downsampleBuffer(nativeChunk, sampleRate, TARGET_RATE);
        let pcm16 = floatTo16BitPCM(downsampled);

        // Rounding in the resample math can land a sample or two off
        // 1600; the WS protocol wants an exact 100ms chunk, so pad/trim.
        if (pcm16.length !== OUTPUT_CHUNK_SAMPLES) {
          const fixed = new Int16Array(OUTPUT_CHUNK_SAMPLES);
          fixed.set(pcm16.subarray(0, Math.min(pcm16.length, OUTPUT_CHUNK_SAMPLES)));
          pcm16 = fixed;
        }

        this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
      }
    }
    return true; // keep processor alive for the life of the call
  }
}

registerProcessor("mic-downsampler", MicDownsampler);
