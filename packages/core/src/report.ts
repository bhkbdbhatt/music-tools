import { randomUUID } from "node:crypto";
import type {
  CertificationReport,
  EngineKind,
  FixRecommendation,
  MetricsSnapshot,
  PlatformBudget,
  PlatformCertification,
  PlatformId,
  RunSummary,
  Severity,
  TierId,
  Violation,
} from "./types.js";
import { METRIC_UNITS, violationKey } from "./types.js";

const SEVERITY_RANK: Record<Severity, number> = { fail: 2, warn: 1, info: 0 };

export function evaluateLimits(
  platform: PlatformId,
  budget: PlatformBudget,
  metrics: MetricsSnapshot,
): Violation[] {
  const out: Violation[] = [];
  for (const [metric, limit] of Object.entries(budget.limits)) {
    const key = metric as keyof typeof METRIC_UNITS;
    const actual = metrics[key];
    if (typeof actual !== "number" || Number.isNaN(actual)) continue;
    const unit = METRIC_UNITS[key];
    const warnRatio = limit.warnRatio ?? 0.8;

    if (limit.max !== undefined && actual > limit.max) {
      const ratio = actual / limit.max;
      const severity: Severity = ratio > 1 ? "fail" : "warn";
      out.push({
        key: violationKey(platform, key),
        platform,
        metric: key,
        actual: round2(actual),
        budget: limit.max,
        unit,
        severity,
        message:
          severity === "fail"
            ? `${budget.displayName}: ${metric} ${fmt(actual)}${unit} exceeds budget ${limit.max}${unit}`
            : `${budget.displayName}: ${metric} ${fmt(actual)}${unit} at ${Math.round(ratio * 100)}% of ${limit.max}${unit} budget`,
      });
    }
    if (limit.min !== undefined && actual < limit.min) {
      out.push({
        key: violationKey(platform, key),
        platform,
        metric: key,
        actual: round2(actual),
        budget: limit.min,
        unit,
        severity: "fail",
        message: `${budget.displayName}: ${metric} ${fmt(actual)}${unit} below required minimum ${limit.min}${unit}`,
      });
    }
  }
  return out;
}

export function scorePlatform(violations: Violation[]): number {
  let score = 100;
  for (const v of violations) {
    if (v.severity === "fail") score -= 15;
    else if (v.severity === "warn") score -= 5;
    else score -= 1;
  }
  return Math.max(0, Math.min(100, score));
}

export function buildPlatformCertification(
  platform: PlatformId,
  budget: PlatformBudget,
  metrics: MetricsSnapshot,
): PlatformCertification {
  const violations = evaluateLimits(platform, budget, metrics);
  const failCount = violations.filter((v) => v.severity === "fail").length;
  const warnCount = violations.filter((v) => v.severity === "warn").length;
  return {
    platform,
    passed: failCount === 0,
    score: scorePlatform(violations),
    failCount,
    warnCount,
    metrics,
    violations,
  };
}

export function buildReport(input: {
  project: { name: string; engine: EngineKind; inputPath: string };
  runner: RunSummary;
  platforms: PlatformCertification[];
  recommendations: FixRecommendation[];
  tier: TierId;
  id?: string;
  createdAt?: string;
}): CertificationReport {
  const totalFail = input.platforms.reduce((n, p) => n + p.failCount, 0);
  const totalWarn = input.platforms.reduce((n, p) => n + p.warnCount, 0);
  const passedPlatforms = input.platforms.filter((p) => p.passed).length;
  const sorted = [...input.recommendations].sort(
    (a, b) => a.priority - b.priority || a.id.localeCompare(b.id),
  );
  return {
    id: input.id ?? randomUUID(),
    createdAt: input.createdAt ?? new Date().toISOString(),
    project: input.project,
    runner: input.runner,
    platforms: input.platforms,
    recommendations: sorted,
    overallPass: input.platforms.every((p) => p.passed),
    summary: {
      totalFail,
      totalWarn,
      passedPlatforms,
      totalPlatforms: input.platforms.length,
    },
    tier: input.tier,
  };
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}

export function maxSeverity(violations: Violation[]): Severity | null {
  let best: Severity | null = null;
  for (const v of violations) {
    if (!best || SEVERITY_RANK[v.severity] > SEVERITY_RANK[best]) best = v.severity;
  }
  return best;
}
