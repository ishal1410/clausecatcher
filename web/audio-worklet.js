/**
 * audio-worklet.js — AudioWorkletProcessor that runs on the audio render
 * thread. Takes mono mic input at whatever rate the AudioContext gives it
 * (typically 44100/48000 Hz) and emits fixed 100ms (1600-sample) Int16 PCM
 * chunks at 16000 Hz to the main thread, matching the server's WS protocol
 * ("binary = PCM16 little-endian mono 16000 Hz, ~100 ms chunks").
 *
 * Downsampling itself lives in dsp.js (shared + unit-testable from
 * dev-check.html) — this file is just the buffering/chunking glue.
 */
import { downsampleBuffer, floatTo16BitPCM } from "./dsp.js";

const TARGET_RATE = 16000;
const CHUNK_MS = 100;
const OUTPUT_CHUNK_SAMPLES = (TARGET_RATE * CHUNK_MS) / 1000; // 1600

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
