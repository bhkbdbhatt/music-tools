import type {
  BankInfo,
  CertificationReport,
  EngineKind,
  PlatformBudget,
  PlatformId,
  ProjectModel,
  TierId,
} from "@audiosure/core";
import { buildPlatformCertification, buildReport, getBudget, mergeBudgets } from "@audiosure/core";
import { parseProject } from "@audiosure/parsers";
import { estimateMetrics, type EstimateOptions } from "./estimator.js";
import { applyCaptures, type ProfilerCapture } from "./captures.js";
import { recommendFixes } from "./recommender.js";

export interface AuditOptions {
  input: string;
  engine?: EngineKind;
  platforms: PlatformId[];
  budgetOverrides?: PlatformBudget[];
  captures?: ProfilerCapture[];
  seed?: number;
  noise?: boolean;
  tier?: TierId;
  projectName?: string;
  estOptions?: EstimateOptions;
}

export interface AuditResult {
  report: CertificationReport;
  model: ProjectModel;
}

export async function runAudit(opts: AuditOptions): Promise<AuditResult> {
  const model = await parseProject(opts.input, opts.engine);
  const budgets = opts.budgetOverrides?.length ? mergeBudgets({ platforms: opts.budgetOverrides }) : undefined;
  const captures = opts.captures ?? [];

  const platforms = opts.platforms;
  const certs = platforms.map((platform) => {
    const budget: PlatformBudget = budgets?.find((b) => b.platform === platform) ?? getBudget(platform);
    const estimated = estimateMetrics(model, platform, opts.estOptions ?? { seed: opts.seed, noise: opts.noise });
    const { metrics } = applyCaptures(estimated, captures);
    return buildPlatformCertification(platform, budget, metrics);
  });

  const recommendations = recommendFixes(model, certs, platforms);

  const report = buildReport({
    project: {
      name: opts.projectName ?? model.name,
      engine: model.engine,
      inputPath: opts.input,
    },
    runner: { kind: "local", name: "local-runner", durationMs: 0 },
    platforms: certs,
    recommendations,
    tier: opts.tier ?? "pro",
  });

  return { report, model };
}

export function summarizeBanks(banks: BankInfo[]): { count: number; totalMB: number; memoryMB: number } {
  return {
    count: banks.length,
    totalMB: round(banks.reduce((n, b) => n + b.sizeBytes, 0) / (1024 * 1024)),
    memoryMB: round(banks.reduce((n, b) => n + b.memoryBytes, 0) / (1024 * 1024)),
  };
}

function round(n: number): number {
  return Math.round(n * 100) / 100;
}
