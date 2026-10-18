import type {
  AudioAsset,
  AudioEffect,
  FixRecommendation,
  MetricKey,
  PlatformCertification,
  PlatformId,
  ProjectModel,
  Severity,
} from "@audiosure/core";
import { violationKey } from "@audiosure/core";
import { getProfile } from "./profiles.js";

const MB = 1024 * 1024;
const PCM16 = 2;
const CONV_AVG_FFT_FACTOR = 2.0;
const IR_TARGET_SEC = 0.5;

interface ViolationIndex {
  bySeverity: Map<PlatformId, Map<string, Severity>>;
  failing: (metric: string) => PlatformId[];
  warning: (metric: string) => PlatformId[];
  severityFor: (metric: string) => Severity | null;
}

function buildIndex(certs: PlatformCertification[]): ViolationIndex {
  const bySeverity = new Map<PlatformId, Map<string, Severity>>();
  for (const c of certs) {
    const m = new Map<string, Severity>();
    for (const v of c.violations) m.set(v.metric, v.severity);
    bySeverity.set(c.platform, m);
  }
  const collect = (metric: string, sev: Severity) =>
    certs.filter((c) => c.violations.some((v) => v.metric === metric && v.severity === sev)).map((c) => c.platform);
  return {
    bySeverity,
    failing: (metric) => collect(metric, "fail"),
    warning: (metric) => collect(metric, "warn"),
    severityFor: (metric) => {
      let best: Severity | null = null;
      for (const c of certs) {
        for (const v of c.violations) {
          if (v.metric !== metric) continue;
          if (v.severity === "fail") return "fail";
          best = "warn";
        }
      }
      return best;
    },
  };
}

function targetsFor(index: ViolationIndex, metrics: string[], fallbackAll: PlatformId[]): PlatformId[] {
  const set = new Set<PlatformId>();
  for (const m of metrics) {
    for (const p of index.failing(m)) set.add(p);
    for (const p of index.warning(m)) set.add(p);
  }
  return set.size > 0 ? [...set] : fallbackAll;
}

function violationKeysFor(index: ViolationIndex, metrics: string[], platforms: PlatformId[]): string[] {
  const keys: string[] = [];
  for (const p of platforms) {
    for (const m of metrics) {
      if (index.bySeverity.get(p)?.has(m)) {
        keys.push(violationKey(p, m as MetricKey));
      }
    }
  }
  return keys;
}

function priorityFrom(index: ViolationIndex, metrics: string[]): number {
  let p = 4;
  for (const m of metrics) {
    const sev = index.severityFor(m);
    if (sev === "fail") return 1;
    if (sev === "warn") p = Math.min(p, 2);
  }
  return p;
}

function isConvolution(fx: AudioEffect): boolean {
  return /convol/i.test(fx.plugin) || /convol/i.test(fx.name);
}

function irSeconds(fx: AudioEffect): number {
  const p = fx.params["irDurationSec"];
  if (typeof p === "number" && p > 0) return p;
  for (const [k, v] of Object.entries(fx.params)) {
    if (typeof v === "number" && /duration|length|sec/i.test(k)) return v;
  }
  return 0;
}

function assetBitrateKbps(a: AudioAsset): number {
  if (a.durationSec > 0) return (a.sizeBytes * 8) / a.durationSec / 1000;
  return 128;
}

function assetMemoryBytes(a: AudioAsset): number {
  if (a.loadType === "stream") return 0;
  if (a.decodeInMemory) {
    const rate = a.sampleRate || 48000;
    const ch = a.channels || 2;
    const dur = a.durationSec > 0 ? a.durationSec : 1;
    return dur * rate * ch * PCM16;
  }
  return a.sizeBytes;
}

function r2(n: number): number {
  return Math.round(n * 100) / 100;
}

export interface RecommendOptions {
  irTargetSec?: number;
  streamSfxMaxSec?: number;
  sampleRateDowngradeHz?: number;
}

export function recommendFixes(
  model: ProjectModel,
  certs: PlatformCertification[],
  allPlatforms: PlatformId[],
  opts: RecommendOptions = {},
): FixRecommendation[] {
  const index = buildIndex(certs);
  const irTarget = opts.irTargetSec ?? IR_TARGET_SEC;
  const streamSfxMax = opts.streamSfxMaxSec ?? 4;
  const recs: FixRecommendation[] = [];

  const convEffects = model.effects.filter(isConvolution);
  for (const [i, fx] of convEffects.entries()) {
    const ir = irSeconds(fx);
    if (ir <= irTarget + 0.01) continue;
    const savingsBytes = (ir - irTarget) * 48000 * 2 * 4 * (1 + CONV_AVG_FFT_FACTOR);
    const savingsMB = savingsBytes / MB;
    const platforms = targetsFor(index, ["memoryFootprintMB"], allPlatforms);
    recs.push({
      id: `rec-ir-${i}`,
      ruleId: "convolution-ir-too-long",
      title: `Reduce convolution reverb impulse from ${r2(ir)}s to ${r2(irTarget)}s to save ~${r2(savingsMB)}MB`,
      detail:
        `Effect "${fx.name}" (${fx.plugin}) uses a ${r2(ir)}s impulse response. ` +
        `Shortening to ${r2(irTarget)}s cuts IR memory and FFT working buffers by ~${r2(savingsMB)}MB per convolution instance` +
        ` and reduces DSP cost. For a ${ir}s IR, consider an offline-baked short IR or a cheaper algorithmic reverb on memory-constrained targets.`,
      estimatedSavingsMB: r2(savingsMB),
      effort: "low",
      priority: priorityFrom(index, ["memoryFootprintMB"]),
      platformTargets: platforms,
      violationKeys: violationKeysFor(index, ["memoryFootprintMB"], platforms),
    });
  }

  const shortStreamSfx = model.assets
    .filter((a) => a.loadType === "stream" && a.durationSec > 0 && a.durationSec < streamSfxMax && (a.isSfx ?? true) && !a.isMusic)
    .sort((a, b) => assetBitrateKbps(b) - assetBitrateKbps(a));
  for (const [i, a] of shortStreamSfx.slice(0, 6).entries()) {
    const kbps = assetBitrateKbps(a);
    const platforms = targetsFor(index, ["streamingBandwidthKbps", "audioThreadLatencyMs", "memoryFootprintMB"], allPlatforms);
    recs.push({
      id: `rec-stream-${i}`,
      ruleId: "short-sfx-should-be-in-memory",
      title: `Switch from streaming to in-memory for "${a.name}" (${r2(a.durationSec)}s SFX)`,
      detail:
        `"${a.name}" is only ${r2(a.durationSec)}s but is streamed (~${Math.round(kbps)}kbps). ` +
        `Short one-shot SFX gain nothing from streaming and pay stream-seek latency plus I/O jitter. ` +
        `Loading it in memory costs ~${r2(a.sizeBytes / MB)}MB but frees ~${Math.round(kbps)}kbps of streaming bandwidth and removes seek latency.`,
      estimatedSavingsKbps: Math.round(kbps),
      effort: "trivial",
      priority: priorityFrom(index, ["streamingBandwidthKbps"]),
      platformTargets: platforms,
      violationKeys: violationKeysFor(index, ["streamingBandwidthKbps"], platforms),
    });
  }

  const streamBudget = new Map<PlatformId, number>();
  for (const c of certs) {
    const v = c.violations.find((x) => x.metric === "streamingBandwidthKbps");
    if (v) streamBudget.set(c.platform, v.budget);
  }
  if (streamBudget.size > 0) {
    const heaviest = [...model.assets]
      .filter((a) => a.loadType === "stream")
      .sort((a, b) => assetBitrateKbps(b) - assetBitrateKbps(a))
      .slice(0, 3);
    for (const [i, a] of heaviest.entries()) {
      const kbps = assetBitrateKbps(a);
      const strictest = Math.min(...[...streamBudget.values()]);
      const target = Math.max(24, Math.min(64, Math.round(strictest * 0.7)));
      if (kbps <= target) continue;
      const profit = Math.round(kbps - target);
      const platforms = [...streamBudget.keys()];
      recs.push({
        id: `rec-reencode-${i}`,
        ruleId: "reencode-stream-bitrate",
        title: `Re-encode stream "${a.name}" to Opus @ ${target}kbps to save ~${profit}kbps`,
        detail:
          `"${a.name}" streams at ~${Math.round(kbps)}kbps, above the strictest platform budget (${strictest}kbps). ` +
          `Re-encoding to Opus at ${target}kbps saves ~${profit}kbps of streaming bandwidth on ${platforms.join(", ")}. ` +
          `Verify perceived quality on music/ambience before shipping.`,
        estimatedSavingsKbps: profit,
        effort: "medium",
        priority: priorityFrom(index, ["streamingBandwidthKbps"]),
        platformTargets: platforms,
        violationKeys: violationKeysFor(index, ["streamingBandwidthKbps"], platforms),
      });
    }
  }

  const shortSfx48 = model.assets.filter(
    (a) => (a.isSfx ?? true) && !a.isMusic && a.durationSec > 0 && a.durationSec < 2 && a.sampleRate >= 44100 && a.loadType !== "stream",
  );
  if (shortSfx48.length > 0 && index.severityFor("memoryFootprintMB")) {
    const savingsMB =
      shortSfx48.reduce((n, a) => n + (a.decodeInMemory ? (a.durationSec * a.sampleRate * a.channels * PCM16) : a.sizeBytes) * 0.5, 0) / MB;
    const platforms = targetsFor(index, ["memoryFootprintMB"], allPlatforms);
    recs.push({
      id: "rec-downsample",
      ruleId: "downsample-short-sfx",
      title: `Downsample ${shortSfx48.length} short SFX from 48kHz to ${(opts.sampleRateDowngradeHz ?? 22050) / 1000}kHz to save ~${r2(savingsMB)}MB`,
      detail:
        `${shortSfx48.length} SFX clips under 2s play at 48kHz. Halving the rate to 22.05kHz is inaudible for most one-shots ` +
        `(impacts, footsteps, UI) and saves ~${r2(savingsMB)}MB of memory. Keep 48kHz for pitched/musical content.`,
      estimatedSavingsMB: r2(savingsMB),
      effort: "low",
      priority: priorityFrom(index, ["memoryFootprintMB"]),
      platformTargets: platforms,
      violationKeys: violationKeysFor(index, ["memoryFootprintMB"], platforms),
    });
  }

  const decompressed = model.assets.filter((a) => a.decodeInMemory && a.durationSec >= 0.5);
  if (decompressed.length > 0 && index.severityFor("memoryFootprintMB")) {
    let savingsMB = 0;
    for (const a of decompressed) {
      const decoded = a.durationSec * a.sampleRate * a.channels * PCM16;
      savingsMB += Math.max(0, decoded - a.sizeBytes);
    }
    savingsMB /= MB;
    const platforms = targetsFor(index, ["memoryFootprintMB"], allPlatforms);
    recs.push({
      id: "rec-compressed-in-memory",
      ruleId: "switch-to-compressed-in-memory",
      title: `Switch ${decompressed.length} clips from DecompressOnLoad to CompressedInMemory to save ~${r2(savingsMB)}MB`,
      detail:
        `${decompressed.length} clips are fully decompressed into RAM. Switching the long/heavy ones to CompressedInMemory ` +
        `keeps them compressed and decodes on the fly, saving ~${r2(savingsMB)}MB at a small CPU cost. Keep DecompressOnLoad for the hottest one-shots.`,
      estimatedSavingsMB: r2(savingsMB),
      effort: "low",
      priority: priorityFrom(index, ["memoryFootprintMB"]),
      platformTargets: platforms,
      violationKeys: violationKeysFor(index, ["memoryFootprintMB"], platforms),
    });
  }

  const inMemoryAssets = model.assets.filter((a) => a.loadType !== "stream");
  const inMemoryBytes = inMemoryAssets.reduce((n, a) => n + assetMemoryBytes(a), 0);
  if (inMemoryAssets.length > 0 && inMemoryBytes > 16 * MB && index.severityFor("memoryFootprintMB")) {
    const savingsMB = (inMemoryBytes * 0.3) / MB;
    const platforms = targetsFor(index, ["memoryFootprintMB"], allPlatforms);
    const biggestBank = [...model.banks].sort((a, b) => b.memoryBytes - a.memoryBytes)[0];
    recs.push({
      id: "rec-inmemory-bitrate",
      ruleId: "reduce-in-memory-media",
      title: `Re-encode ${inMemoryAssets.length} in-memory clips (${r2(inMemoryBytes / MB)}MB) at lower bitrate to save ~${r2(savingsMB)}MB`,
      detail:
        `In-memory media totals ~${r2(inMemoryBytes / MB)}MB${biggestBank ? ` (largest bank "${biggestBank.name}")` : ""}, driving the memory overage on ${platforms.join(", ")}. ` +
        `Dropping Vorbis/Opus quality by one tier (or moving rarely-heard one-shots to 22.05kHz) typically saves ~30% = ~${r2(savingsMB)}MB ` +
        `with little perceptual cost. Stream the largest one-shot banks if they exceed their working set.`,
      estimatedSavingsMB: r2(savingsMB),
      effort: "medium",
      priority: priorityFrom(index, ["memoryFootprintMB"]),
      platformTargets: platforms,
      violationKeys: violationKeysFor(index, ["memoryFootprintMB"], platforms),
    });
  }

  const voiceViolation = index.failing("peakConcurrentVoices").concat(index.warning("peakConcurrentVoices"));
  const cpuViolation = index.failing("cpuAudioPct").concat(index.warning("cpuAudioPct"));
  const voiceTargets = [...new Set([...voiceViolation, ...cpuViolation])];
  if (voiceTargets.length > 0) {
    const peak = Math.max(...certs.map((c) => c.metrics.peakConcurrentVoices), 1);
    const cap = Math.round(peak * 0.7);
    const strictest = Math.min(...voiceTargets.map((p) => getProfile(p).perVoiceCpuPct));
    const cpuSave = r2(peak * 0.3 * strictest);
    recs.push({
      id: "rec-voice-virtualization",
      ruleId: "voice-virtualization",
      title: `Cap concurrent voices to ${cap} via virtualization to cut audio CPU ~${cpuSave}%`,
      detail:
        `Peak reach is ~${peak} concurrent voices. Virtualizing distant/quiet voices above ${cap} (Wwise voice limiting / FMOD virtual voices) ` +
        `keeps CPU within budget with minimal audible impact. Prioritize music/player-critical sounds and cull ambience tails first.`,
      estimatedSavingsMB: undefined,
      effort: "low",
      priority: priorityFrom(index, ["peakConcurrentVoices", "cpuAudioPct"]),
      platformTargets: voiceTargets,
      violationKeys: violationKeysFor(index, ["peakConcurrentVoices", "cpuAudioPct"], voiceTargets),
    });
  }

  const latencyViolation = [...new Set([...index.failing("audioThreadLatencyMs"), ...index.warning("audioThreadLatencyMs")])];
  if (latencyViolation.length > 0 && convEffects.length > 0) {
    const save = r2(convEffects.length * 0.6);
    recs.push({
      id: "rec-latency-dsp",
      ruleId: "latency-dsp-chain",
      title: `Shorten convolution on the master path to cut ~${save}ms of audio latency`,
      detail:
        `Platforms ${latencyViolation.join(", ")} are near/over their audio-latency budget. Long convolution reverbs and deep DSP chains on the ` +
        `master bus add latency. Move convolution to sends, shorten IRs, and keep the master insert chain shallow.`,
      estimatedLatencyMs: save,
      effort: "medium",
      priority: 1,
      platformTargets: latencyViolation,
      violationKeys: violationKeysFor(index, ["audioThreadLatencyMs"], latencyViolation),
    });
  }

  const batteryViolation = index.failing("batteryDrainMw").concat(index.warning("batteryDrainMw"));
  const batteryTargets = [...new Set(batteryViolation)];
  if (batteryTargets.length > 0) {
    recs.push({
      id: "rec-battery",
      ruleId: "reduce-battery-drain",
      title: `Cut voice count, streaming bitrate, and convolution cost to reduce battery drain`,
      detail:
        `Battery budget is exceeded on ${batteryTargets.join(", ")}. Audio decode and DSP run continuously; ` +
        `the fastest milliwatt wins are fewer concurrent voices, lower streaming bitrate, and cheaper reverb DSP. ` +
        `Consider suspending audio work when the app is backgrounded.`,
      effort: "medium",
      priority: 1,
      platformTargets: batteryTargets,
      violationKeys: violationKeysFor(index, ["batteryDrainMw"], batteryTargets),
    });
  }

  return recs;
}
