import type { CertificationReport, PlatformId } from "@audiosure/core";
import { runAudit, type AuditOptions, type AuditResult } from "./pipeline.js";

export type RunnerKind = "local" | "cloud-sim";

export interface Runner {
  kind: RunnerKind;
  name: string;
  run(options: AuditOptions): Promise<AuditResult>;
}

export interface RunnerProgress {
  (event: { platform: PlatformId; phase: "queue" | "build" | "profile" | "done"; message: string }): void;
}

export class LocalRunner implements Runner {
  kind: RunnerKind = "local";
  name = "local-runner";
  constructor(private onProgress?: RunnerProgress) {}

  async run(options: AuditOptions): Promise<AuditResult> {
    const start = Date.now();
    for (const platform of options.platforms) {
      this.onProgress?.({ platform, phase: "profile", message: `estimating metrics for ${platform}` });
    }
    const result = await runAudit(options);
    result.report.runner = {
      kind: "local",
      name: this.name,
      durationMs: Date.now() - start,
    };
    return result;
  }
}

export interface CloudRunnerOptions {
  region?: string;
  queueMsPerPlatform?: number;
  buildMsPerPlatform?: number;
  onProgress?: RunnerProgress;
}

/**
 * Simulated cloud runner.
 *
 * Models the build matrix that real console SDK runners perform: submitting
 * per-platform jobs, waiting in a queue, building the audio middleware for the
 * target, and collecting profiler captures. The analysis itself uses the local
 * estimator/parser stack, so results are identical to a local run — the point
 * is to exercise the async, multi-target orchestration path that the hosted
 * product uses. See docs/CLOUD.md for the production integration seam
 * (Sony/Microsoft/Nintendo dev-portal runners).
 */
export class CloudRunnerSim implements Runner {
  kind: RunnerKind = "cloud-sim";
  name: string;
  private onProgress?: RunnerProgress;
  private queueMs: number;
  private buildMs: number;
  private region: string;

  constructor(opts: CloudRunnerOptions = {}) {
    this.region = opts.region ?? "us-west-2";
    this.queueMs = opts.queueMsPerPlatform ?? 400;
    this.buildMs = opts.buildMsPerPlatform ?? 1200;
    this.onProgress = opts.onProgress;
    this.name = `cloud-sim:${this.region}`;
  }

  async run(options: AuditOptions): Promise<AuditResult> {
    const start = Date.now();
    const settled = await Promise.all(
      options.platforms.map(async (platform) => {
        this.onProgress?.({ platform, phase: "queue", message: `queued on ${this.region} runner` });
        await sleep(this.queueMs);
        this.onProgress?.({ platform, phase: "build", message: `building audio middleware for ${platform}` });
        await sleep(this.buildMs);
        this.onProgress?.({ platform, phase: "profile", message: `collecting profiling capture for ${platform}` });
        return platform;
      }),
    );
    void settled;

    const result = await runAudit({ ...options, tier: options.tier });
    result.report.runner = {
      kind: "cloud-sim",
      name: this.name,
      durationMs: Date.now() - start,
    };
    for (const platform of options.platforms) {
      this.onProgress?.({ platform, phase: "done", message: `certification complete for ${platform}` });
    }
    return result;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export type { AuditOptions, AuditResult, CertificationReport };
