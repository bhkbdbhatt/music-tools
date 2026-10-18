import type {
  AudioAsset,
  AudioEffect,
  MetricsSnapshot,
  PlatformId,
  ProjectModel,
} from "@audiosure/core";
import { mulberry32 } from "@audiosure/parsers";
import { getProfile } from "./profiles.js";

export interface EstimateOptions {
  seed?: number;
  noise?: boolean;
}

const MB = 1024 * 1024;
const PCM_BYTES_PER_SAMPLE = 2;

function decodedBytes(asset: AudioAsset): number {
  const rate = asset.sampleRate || 48000;
  const ch = asset.channels || 2;
  const dur = asset.durationSec > 0 ? asset.durationSec : 1;
  return dur * rate * ch * PCM_BYTES_PER_SAMPLE;
}

function assetMemoryBytes(asset: AudioAsset): number {
  if (asset.loadType === "stream") return 0;
  if (asset.decodeInMemory) return decodedBytes(asset);
  return asset.sizeBytes;
}

function isConvolution(fx: AudioEffect): boolean {
  return /convol/i.test(fx.plugin) || /convol/i.test(fx.name);
}

function irSeconds(fx: AudioEffect): number {
  const p = fx.params["irDurationSec"];
  if (typeof p === "number" && p > 0) return p;
  for (const [k, v] of Object.entries(fx.params)) {
    if (typeof v === "number" && /duration|length|sec|ir/i.test(k)) return v;
  }
  return 0;
}

export function estimateMetrics(
  model: ProjectModel,
  platform: PlatformId,
  opts: EstimateOptions = {},
): MetricsSnapshot {
  const profile = getProfile(platform);
  const assets = model.assets;
  const streams = assets.filter((a) => a.loadType === "stream");
  const memoryAssets = assets.filter((a) => a.loadType !== "stream");
  const convEffects = model.effects.filter(isConvolution);
  const otherEffects = model.effects.filter((e) => !isConvolution(e));

  const audioSources = Number(model.metadata["audioSourceCount"] ?? 0);
  const explicitVoices = model.events.reduce((n, e) => n + (e.maxInstances ?? 1), 0);
  let voices = 6 + explicitVoices * 0.35 + audioSources * 0.15 + streams.length * 0.5;
  voices = Math.round(Math.min(profile.maxVoices, Math.max(1, voices)));

  let memoryBytes = 0;
  for (const a of memoryAssets) memoryBytes += assetMemoryBytes(a);
  memoryBytes += streams.length * profile.streamBufferKB * 1024;
  memoryBytes += model.banks.length * profile.bankOverheadKB * 1024;
  memoryBytes += voices * profile.perVoiceMemKB * 1024;
  for (const fx of convEffects) {
    const ir = irSeconds(fx) || 0.5;
    memoryBytes += ir * 48000 * 2 * 4 * (1 + profile.convFftFactor);
  }
  memoryBytes += otherEffects.length * profile.genericFxKB * 1024;

  let streamingKbps = 0;
  for (const a of streams) {
    const bitrate = a.durationSec > 0 ? (a.sizeBytes * 8) / a.durationSec / 1000 : 128;
    const weight = a.isMusic || /ambien|bgm|theme/i.test(a.name) ? 1 : 0.25;
    streamingKbps += bitrate * weight;
  }

  let cpu = profile.baseCpuPct
    + voices * profile.perVoiceCpuPct
    + streams.length * profile.perStreamCpuPct
    + convEffects.length * profile.convCpuPct
    + otherEffects.length * profile.perFxCpuPct;
  cpu = Math.min(60, cpu);

  let gpu = convEffects.length * profile.convGpuPct + otherEffects.length * profile.genericGpuPct;

  let latency = profile.baseLatencyMs + convEffects.length * profile.convLatencyMs;
  if (streams.length > 0) latency += profile.streamSeekLatencyMs;
  if (voices > 0.85 * profile.maxVoices) latency += profile.voiceContentionMs;

  let battery = 0;
  if (profile.hasBattery) {
    battery = profile.batteryBaseMw + cpu * profile.batteryPerCpuMw + streamingKbps * profile.batteryPerKbpsMw;
  }

  let metrics: MetricsSnapshot = {
    platform,
    memoryFootprintMB: memoryBytes / MB,
    inMemoryMB: memoryBytes / MB,
    streamedMB: streams.reduce((n, a) => n + a.sizeBytes, 0) / MB,
    audioThreadLatencyMs: latency,
    cpuAudioPct: cpu,
    gpuDspPct: gpu,
    streamingBandwidthKbps: streamingKbps,
    batteryDrainMw: battery,
    peakConcurrentVoices: voices,
    clipCount: assets.length,
  };

  if (opts.noise) {
    const rnd = mulberry32(opts.seed ?? 1337);
    const jitter = (v: number) => v * (1 + (rnd() - 0.5) * 0.08);
    metrics = {
      ...metrics,
      memoryFootprintMB: jitter(metrics.memoryFootprintMB),
      audioThreadLatencyMs: jitter(metrics.audioThreadLatencyMs),
      cpuAudioPct: jitter(metrics.cpuAudioPct),
      gpuDspPct: jitter(metrics.gpuDspPct),
      streamingBandwidthKbps: jitter(metrics.streamingBandwidthKbps),
      batteryDrainMw: jitter(metrics.batteryDrainMw),
      inMemoryMB: jitter(metrics.inMemoryMB),
      streamedMB: jitter(metrics.streamedMB),
    };
  }

  return roundMetrics(metrics);
}

function roundMetrics(m: MetricsSnapshot): MetricsSnapshot {
  return {
    ...m,
    memoryFootprintMB: round(m.memoryFootprintMB),
    inMemoryMB: round(m.inMemoryMB),
    streamedMB: round(m.streamedMB),
    audioThreadLatencyMs: round(m.audioThreadLatencyMs),
    cpuAudioPct: round(m.cpuAudioPct),
    gpuDspPct: round(m.gpuDspPct),
    streamingBandwidthKbps: round(m.streamingBandwidthKbps),
    batteryDrainMw: round(m.batteryDrainMw),
  };
}

function round(n: number): number {
  return Math.round(n * 100) / 100;
}
