import type { BudgetFile, PlatformBudget, PlatformId } from "./types.js";

/**
 * Default platform budgets.
 *
 * These are opinionated industry-plausible defaults, tuned to the budgets
 * named in product requirements (PS5 audio memory < 256MB, mobile latency
 * < 20ms, Switch 2 streaming < 48kbps). Every value is overridable per
 * project via `.audiosure/budgets.json`.
 */
export const DEFAULT_BUDGETS: PlatformBudget[] = [
  {
    platform: "pc",
    displayName: "PC (Steam/Epic)",
    limits: {
      memoryFootprintMB: { max: 512, warnRatio: 0.85 },
      audioThreadLatencyMs: { max: 30, warnRatio: 0.8 },
      cpuAudioPct: { max: 12, warnRatio: 0.75 },
      gpuDspPct: { max: 6, warnRatio: 0.75 },
      streamingBandwidthKbps: { max: 512, warnRatio: 0.8 },
      peakConcurrentVoices: { max: 128, warnRatio: 0.8 },
    },
  },
  {
    platform: "ps5",
    displayName: "PlayStation 5",
    limits: {
      memoryFootprintMB: { max: 256, warnRatio: 0.85 },
      audioThreadLatencyMs: { max: 18, warnRatio: 0.8 },
      cpuAudioPct: { max: 6, warnRatio: 0.75 },
      gpuDspPct: { max: 4, warnRatio: 0.75 },
      streamingBandwidthKbps: { max: 1024, warnRatio: 0.85 },
      peakConcurrentVoices: { max: 96, warnRatio: 0.8 },
    },
  },
  {
    platform: "xbox",
    displayName: "Xbox Series X|S",
    limits: {
      memoryFootprintMB: { max: 256, warnRatio: 0.85 },
      audioThreadLatencyMs: { max: 18, warnRatio: 0.8 },
      cpuAudioPct: { max: 6, warnRatio: 0.75 },
      gpuDspPct: { max: 4, warnRatio: 0.75 },
      streamingBandwidthKbps: { max: 1024, warnRatio: 0.85 },
      peakConcurrentVoices: { max: 96, warnRatio: 0.8 },
    },
  },
  {
    platform: "switch2",
    displayName: "Nintendo Switch 2",
    limits: {
      memoryFootprintMB: { max: 128, warnRatio: 0.8 },
      audioThreadLatencyMs: { max: 25, warnRatio: 0.8 },
      cpuAudioPct: { max: 10, warnRatio: 0.75 },
      gpuDspPct: { max: 5, warnRatio: 0.75 },
      streamingBandwidthKbps: { max: 48, warnRatio: 0.75 },
      peakConcurrentVoices: { max: 64, warnRatio: 0.8 },
    },
  },
  {
    platform: "mobile",
    displayName: "Mobile (iOS/Android)",
    limits: {
      memoryFootprintMB: { max: 96, warnRatio: 0.8 },
      audioThreadLatencyMs: { max: 20, warnRatio: 0.75 },
      cpuAudioPct: { max: 8, warnRatio: 0.7 },
      gpuDspPct: { max: 2, warnRatio: 0.7 },
      streamingBandwidthKbps: { max: 128, warnRatio: 0.8 },
      batteryDrainMw: { max: 150, warnRatio: 0.8 },
      peakConcurrentVoices: { max: 48, warnRatio: 0.8 },
    },
  },
  {
    platform: "vr",
    displayName: "VR Headset (Quest-class)",
    limits: {
      memoryFootprintMB: { max: 192, warnRatio: 0.85 },
      audioThreadLatencyMs: { max: 10, warnRatio: 0.7 },
      cpuAudioPct: { max: 8, warnRatio: 0.7 },
      gpuDspPct: { max: 6, warnRatio: 0.75 },
      streamingBandwidthKbps: { max: 256, warnRatio: 0.8 },
      batteryDrainMw: { max: 400, warnRatio: 0.8 },
      peakConcurrentVoices: { max: 64, warnRatio: 0.8 },
    },
  },
];

export function getBudget(platform: PlatformId): PlatformBudget {
  const found = DEFAULT_BUDGETS.find((b) => b.platform === platform);
  if (!found) throw new Error(`No default budget for platform: ${platform}`);
  return found;
}

export function mergeBudgets(overrides?: BudgetFile): PlatformBudget[] {
  if (!overrides?.platforms?.length) return DEFAULT_BUDGETS;
  const byId = new Map(DEFAULT_BUDGETS.map((b) => [b.platform, b]));
  for (const ov of overrides.platforms) {
    const base = byId.get(ov.platform);
    if (!base) {
      byId.set(ov.platform, ov);
      continue;
    }
    byId.set(ov.platform, {
      ...base,
      displayName: ov.displayName ?? base.displayName,
      limits: { ...base.limits, ...ov.limits },
    });
  }
  return PLATFORM_ORDER.map((p) => byId.get(p)!).filter(Boolean);
}

const PLATFORM_ORDER: PlatformId[] = ["pc", "ps5", "xbox", "switch2", "mobile", "vr"];
