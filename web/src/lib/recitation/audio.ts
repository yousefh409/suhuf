// web/src/lib/recitation/audio.ts
// AudioWorklet-based mic capture → 16 kHz mono float32 PCM chunks.
// Pattern lifted from recitation/static/index.html into a clean module.

const TARGET_SR = 16000;

export type AudioCapture = {
  chunks: AsyncIterable<Float32Array>;
  stop: () => Promise<void>;
};

export async function startCapture(): Promise<AudioCapture> {
  if (typeof window === "undefined") {
    throw new Error("startCapture must run in the browser");
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
    },
  });

  const ctx = new (window.AudioContext ||
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).webkitAudioContext)();
  const sourceSampleRate = ctx.sampleRate;

  // Inline AudioWorklet processor: pumps mono float32 samples to main thread.
  const processorSrc = `
    class P extends AudioWorkletProcessor {
      process(inputs) {
        const input = inputs[0];
        if (input && input[0]) {
          this.port.postMessage(input[0].slice(0));
        }
        return true;
      }
    }
    registerProcessor("recitation-pcm", P);
  `;
  const blob = new Blob([processorSrc], { type: "application/javascript" });
  const url = URL.createObjectURL(blob);
  await ctx.audioWorklet.addModule(url);
  URL.revokeObjectURL(url);

  const node = new AudioWorkletNode(ctx, "recitation-pcm");
  const source = ctx.createMediaStreamSource(stream);
  source.connect(node);

  const queue: Float32Array[] = [];
  const waiters: Array<(v: Float32Array | null) => void> = [];

  node.port.onmessage = (e: MessageEvent<Float32Array>) => {
    const sample = resample(e.data, sourceSampleRate, TARGET_SR);
    if (waiters.length > 0) {
      const w = waiters.shift()!;
      w(sample);
    } else {
      queue.push(sample);
    }
  };

  let stopped = false;

  const chunks: AsyncIterable<Float32Array> = {
    [Symbol.asyncIterator]() {
      return {
        async next() {
          if (queue.length > 0) {
            return { done: false, value: queue.shift()! };
          }
          if (stopped) return { done: true, value: undefined as unknown as Float32Array };
          const v = await new Promise<Float32Array | null>((resolve) =>
            waiters.push(resolve),
          );
          if (v == null) return { done: true, value: undefined as unknown as Float32Array };
          return { done: false, value: v };
        },
      };
    },
  };

  return {
    chunks,
    stop: async () => {
      stopped = true;
      while (waiters.length) waiters.shift()!(null);
      try { source.disconnect(); } catch {}
      try { node.disconnect(); } catch {}
      stream.getTracks().forEach((t) => t.stop());
      await ctx.close();
    },
  };
}

// Linear-interpolation downsample from sourceSR to targetSR.
function resample(src: Float32Array, sourceSR: number, targetSR: number): Float32Array {
  if (sourceSR === targetSR) return src;
  const ratio = sourceSR / targetSR;
  const outLen = Math.floor(src.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const srcIdx = i * ratio;
    const lo = Math.floor(srcIdx);
    const hi = Math.min(lo + 1, src.length - 1);
    const frac = srcIdx - lo;
    out[i] = src[lo] * (1 - frac) + src[hi] * frac;
  }
  return out;
}
