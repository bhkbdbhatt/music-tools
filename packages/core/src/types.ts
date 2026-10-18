export type PlatformId = "pc" | "ps5" | "xbox" | "switch2" | "mobile" | "vr";

export const PLATFORM_IDS: PlatformId[] = ["pc", "ps5", "xbox", "switch2", "mobile", "vr"];

export type EngineKind = "wwise" | "fmod" | "unity" | "unreal";

export type LoadType = "memory" | "stream" | "preload";

export type Severity = "info" | "warn" | "fail";

export type Effort = "trivial" | "low" | "medium" | "high";

export interface AudioAsset {
  id: string;
  name: string;
  path?: string;
  durationSec: number;
  channels: number;
  sampleRate: number;
  codec: string;
  loadType: LoadType;
  sizeBytes: number;
  decodeInMemory?: boolean;
  isMusic?: boolean;
  isSfx?: boolean;
  language?: string;
  bankId?: string;
}

export interface AudioEffect {
  id: string;
  name: string;
  plugin: string;
  params: Record<string, number | string>;
  busId?: string;
}

export interface AudioBus {
  id: string;
  name: string;
  parentId?: string;
  effectIds: string[];
}

export interface AudioEvent {
  id: string;
  name: string;
  bankId?: string;
  assetIds: string[];
  maxInstances?: number;
}

export interface BankInfo {
  id: string;
  name: string;
  sizeBytes: number;
  memoryBytes: number;
  streamIds: string[];
  assetIds: string[];
  language?: string;
}

export interface ProjectModel {
  engine: EngineKind;
  name: string;
  version?: string;
  assets: AudioAsset[];
  effects: AudioEffect[];
  buses: AudioBus[];
  events: AudioEvent[];
  banks: BankInfo[];
  pluginsUsed: string[];
  metadata: Record<string, unknown>;
}

export const METRIC_UNITS = {
  memoryFootprintMB: "MB",
  audioThreadLatencyMs: "ms",
  cpuAudioPct: "%",
  gpuDspPct: "%",
  streamingBandwidthKbps: "kbps",
  batteryDrainMw: "mW",
  peakConcurrentVoices: "voices",
  clipCount: "clips",
} as const;

export type MetricKey = keyof typeof METRIC_UNITS;

export interface MetricsSnapshot {
  platform: PlatformId;
  memoryFootprintMB: number;
  inMemoryMB: number;
  streamedMB: number;
  audioThreadLatencyMs: number;
  cpuAudioPct: number;
  gpuDspPct: number;
  streamingBandwidthKbps: number;
  batteryDrainMw: number;
  peakConcurrentVoices: number;
  clipCount: number;
}

export interface MetricLimit {
  max?: number;
  min?: number;
  warnRatio?: number;
}

export interface PlatformBudget {
  platform: PlatformId;
  displayName: string;
  limits: Partial<Record<MetricKey, MetricLimit>>;
}

export interface BudgetFile {
  $schema?: string;
  platforms: PlatformBudget[];
}

export interface Violation {
  key: string;
  platform: PlatformId;
  metric: MetricKey;
  actual: number;
  budget: number;
  unit: string;
  severity: Severity;
  message: string;
  assetId?: string;
}

export interface FixRecommendation {
  id: string;
  ruleId: string;
  title: string;
  detail: string;
  estimatedSavingsMB?: number;
  estimatedSavingsKbps?: number;
  estimatedLatencyMs?: number;
  effort: Effort;
  priority: number;
  platformTargets: PlatformId[];
  violationKeys: string[];
}

export interface PlatformCertification {
  platform: PlatformId;
  passed: boolean;
  score: number;
  failCount: number;
  warnCount: number;
  metrics: MetricsSnapshot;
  violations: Violation[];
}

export interface RunSummary {
  kind: "local" | "cloud-sim";
  name: string;
  durationMs: number;
}

export interface CertificationReport {
  id: string;
  createdAt: string;
  project: {
    name: string;
    engine: EngineKind;
    inputPath: string;
  };
  runner: RunSummary;
  platforms: PlatformCertification[];
  recommendations: FixRecommendation[];
  overallPass: boolean;
  summary: {
    totalFail: number;
    totalWarn: number;
    passedPlatforms: number;
    totalPlatforms: number;
  };
  tier: TierId;
}

export type TierId = "starter" | "pro" | "studio";

export interface Tier {
  id: TierId;
  name: string;
  priceMonthlyUsd: number;
  maxPlatforms: number | null;
  maxBuildsPerMonth: number | null;
  apiAccess: boolean;
  teamSeats: number | null;
  features: string[];
}

export interface AuditConfig {
  project: {
    name?: string;
    input: string;
    engine?: EngineKind;
  };
  platforms: PlatformId[];
  tier: TierId;
  budgetOverridesPath?: string;
  seed?: number;
  noise?: boolean;
}

export function violationKey(
  platform: PlatformId,
  metric: MetricKey,
  assetId?: string,
): string {
  return `${platform}:${metric}:${assetId ?? "global"}`;
}
