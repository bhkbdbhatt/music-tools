import { promises as fs } from "node:fs";
import path from "node:path";
import type { PlatformBudget, ProjectModel } from "@audiosure/core";
import {
  checkBuildLimit,
  checkPlatformLimit,
  DEFAULT_BUDGETS,
  getTier,
} from "@audiosure/core";
import { CloudRunnerSim, LocalRunner, runAudit, type AuditResult, type Runner } from "@audiosure/engine";
import { detectEngine, parseProject } from "@audiosure/parsers";
import { loadConfig, parsePlatforms, resolveTier, saveConfig, defaultConfig } from "./config.js";
import { buildsThisMonth, recordBuild } from "./usage.js";
import { saveReport } from "./store.js";
import { renderHtml, renderJson, renderMarkdown } from "./reporters.js";
import { generateAllFixtures } from "./fixtures.js";
import { PLATFORM_IDS, type PlatformId, type TierId } from "@audiosure/core";

export interface CertifyOptions {
  input?: string;
  engine?: string;
  platforms?: string;
  runner?: string;
  tier?: string;
  out?: string;
  seed?: number;
  noise?: boolean;
  captures?: string;
  quiet?: boolean;
}

const DEFAULT_OUT = "reports";

export async function cmdInit(cwd: string, input = "."): Promise<number> {
  const engine = await detectEngine(path.resolve(cwd, input));
  const config = defaultConfig();
  config.project.input = input;
  if (engine) config.project.engine = engine;
  config.project.name = path.basename(path.resolve(cwd, input));
  const p = await saveConfig(cwd, config);
  console.log(`Wrote ${path.relative(cwd, p)}`);
  console.log(`  input:     ${config.project.input}`);
  console.log(`  engine:    ${engine ?? "(auto-detect)"}`);
  console.log(`  platforms: ${config.platforms.join(", ")}`);
  console.log(`  tier:      ${config.tier}`);
  console.log(`\nNext: audiosure certify`);
  return 0;
}

export async function cmdAnalyze(
  input: string,
  engine: string | undefined,
  json: boolean,
): Promise<number> {
  const model = await parseProject(input, engine as never);
  if (json) {
    console.log(JSON.stringify(model, null, 2));
    return 0;
  }
  printModel(model);
  return 0;
}

function printModel(model: ProjectModel): void {
  const inMemory = model.assets.filter((a) => a.loadType !== "stream");
  const streamed = model.assets.filter((a) => a.loadType === "stream");
  console.log(`Engine:     ${model.engine}`);
  console.log(`Project:    ${model.name}`);
  console.log(`Assets:     ${model.assets.length} (${inMemory.length} in-memory, ${streamed.length} streamed)`);
  console.log(`Banks:      ${model.banks.length}`);
  console.log(`Events:     ${model.events.length}`);
  console.log(`Effects:    ${model.effects.length}`);
  console.log(`Plugins:    ${model.pluginsUsed.join(", ") || "(none)"}`);
  console.log(`Metadata:   ${JSON.stringify(model.metadata)}`);
  if (model.effects.length) {
    console.log("\nEffects:");
    for (const fx of model.effects) {
      console.log(`  - ${fx.name} [${fx.plugin}] ${JSON.stringify(fx.params)}`);
    }
  }
}

export async function cmdCertify(cwd: string, opts: CertifyOptions): Promise<number> {
  const config = await loadConfig(cwd);
  const input = opts.input ?? config?.project.input;
  if (!input) {
    console.error("No input project. Pass a path or run `audiosure init`.");
    return 2;
  }
  const tier: TierId = resolveTier(opts.tier ?? config?.tier);
  const platforms = parsePlatforms(opts.platforms ?? config?.platforms.join(",") ?? "all");
  const engine = opts.engine ?? config?.project.engine;
  const out = path.resolve(cwd, opts.out ?? DEFAULT_OUT);

  const platformGate = checkPlatformLimit(tier, platforms.length);
  if (!platformGate.allowed) {
    console.error(`Tier limit: ${platformGate.reason}`);
    return 3;
  }
  const used = await buildsThisMonth(cwd);
  const buildGate = checkBuildLimit(tier, used);
  if (!buildGate.allowed) {
    console.error(`Tier limit: ${buildGate.reason}`);
    return 3;
  }

  const captures = opts.captures ? await readCaptures(path.resolve(cwd, opts.captures)) : undefined;

  const runner: Runner =
    (opts.runner ?? "local") === "cloud"
      ? new CloudRunnerSim({
          onProgress: opts.quiet ? undefined : (e) => console.log(`  [${e.platform}] ${e.message}`),
        })
      : new LocalRunner();

  const labels: PlatformId[] = platforms;
  if (!opts.quiet) {
    console.log(`audiosure certify — ${input}`);
    console.log(`  engine:    ${engine ?? "(auto)"}`);
    console.log(`  runner:    ${runner.kind}`);
    console.log(`  platforms: ${labels.join(", ")}`);
    console.log(`  tier:      ${getTier(tier).name} (${used} builds used this month)`);
    console.log("");
  }

  let result: AuditResult;
  try {
    result = await runner.run({ input, engine: engine as never, platforms: labels, tier, captures, seed: opts.seed, noise: opts.noise });
  } catch (err) {
    console.error(`Audit failed: ${(err as Error).message}`);
    return 4;
  }

  const paths = await saveReport(out, result.report);
  await recordBuild(cwd, { platforms: labels, input, passed: result.report.overallPass });

  const r = result.report;
  console.log(`Summary: ${r.overallPass ? "CERTIFIED PASS" : "NOT CERTIFIED (FAIL)"}`);
  for (const p of r.platforms) {
    console.log(`  ${p.passed ? "PASS" : "FAIL"}  ${p.platform.padEnd(8)} score ${String(p.score).padStart(3)}  ${p.failCount} fail / ${p.warnCount} warn`);
  }
  console.log("");
  console.log(`Recommendations: ${r.recommendations.length}`);
  for (const rec of r.recommendations.slice(0, 5)) {
    console.log(`  - ${rec.title}`);
  }
  if (r.recommendations.length > 5) console.log(`  ...and ${r.recommendations.length - 5} more (see report)`);
  console.log("");
  console.log(`Reports written to ${path.relative(cwd, path.dirname(paths.json))}/`);
  console.log(`  json: ${path.relative(cwd, paths.json)}`);
  console.log(`  md:   ${path.relative(cwd, paths.md)}`);
  console.log(`  html: ${path.relative(cwd, paths.html)}`);

  return r.overallPass ? 0 : 1;
}

async function readCaptures(file: string): Promise<import("@audiosure/engine").ProfilerCapture[]> {
  const text = await fs.readFile(file, "utf8");
  const parsed = JSON.parse(text) as { captures?: unknown[] } | unknown[];
  const arr = Array.isArray(parsed) ? parsed : (parsed.captures ?? []);
  return arr as import("@audiosure/engine").ProfilerCapture[];
}

export async function cmdReport(file: string, format: string, out?: string): Promise<number> {
  const { loadReport } = await import("./store.js");
  const report = await loadReport(file);
  let content: string;
  if (format === "json") content = renderJson(report);
  else if (format === "html") content = renderHtml(report);
  else content = renderMarkdown(report);
  if (out) {
    await fs.writeFile(path.resolve(out), content, "utf8");
    console.log(`Wrote ${out}`);
  } else {
    console.log(content);
  }
  return 0;
}

export async function cmdBudget(action: string, platform: string | undefined, overridesPath?: string): Promise<number> {
  const budgets = await loadBudgets(overridesPath);
  if (action === "show") {
    const list = platform ? budgets.filter((b) => b.platform === platform) : budgets;
    if (!list.length) {
      console.error(`Unknown platform: ${platform}. Valid: ${PLATFORM_IDS.join(", ")}`);
      return 2;
    }
    for (const b of list) {
      console.log(`${b.platform} — ${b.displayName}`);
      for (const [metric, limit] of Object.entries(b.limits)) {
        const parts: string[] = [];
        if (limit.max !== undefined) parts.push(`max ${limit.max}`);
        if (limit.min !== undefined) parts.push(`min ${limit.min}`);
        console.log(`  ${metric.padEnd(26)} ${parts.join(", ")}  (warn @ ${Math.round((limit.warnRatio ?? 0.8) * 100)}%)`);
      }
    }
    return 0;
  }
  if (action === "validate") {
    if (!overridesPath) {
      console.error("Provide --file <budgets.json> to validate.");
      return 2;
    }
    const raw = JSON.parse(await fs.readFile(path.resolve(overridesPath), "utf8")) as { platforms?: unknown };
    if (!Array.isArray(raw.platforms)) {
      console.error("Invalid budget file: missing platforms[] array.");
      return 1;
    }
    const ids = new Set(PLATFORM_IDS);
    let bad = 0;
    for (const p of raw.platforms as Array<{ platform?: string }>) {
      if (!p.platform || !ids.has(p.platform as PlatformId)) {
        console.error(`Unknown platform in overrides: ${p.platform}`);
        bad++;
      }
    }
    if (bad) return 1;
    console.log(`Budget file OK (${(raw.platforms as unknown[]).length} platform overrides).`);
    return 0;
  }
  console.error(`Unknown budget action: ${action} (use show|validate)`);
  return 2;
}

async function loadBudgets(overridesPath?: string): Promise<PlatformBudget[]> {
  if (!overridesPath) return DEFAULT_BUDGETS;
  const raw = JSON.parse(await fs.readFile(path.resolve(overridesPath), "utf8")) as { platforms: PlatformBudget[] };
  const byId = new Map(DEFAULT_BUDGETS.map((b) => [b.platform, b]));
  for (const ov of raw.platforms) {
    const base = byId.get(ov.platform);
    byId.set(ov.platform, base ? { ...base, limits: { ...base.limits, ...ov.limits } } : ov);
  }
  return [...byId.values()];
}

export async function cmdFixtures(outDir: string): Promise<number> {
  const res = await generateAllFixtures(outDir);
  console.log(`Generated fixtures in ${res.root}`);
  for (const p of res.projects) console.log(`  - ${path.relative(outDir, p)}`);
  console.log(`\nTry: audiosure certify --input ${path.relative(process.cwd(), res.projects[0])} --platforms all`);
  return 0;
}
