#!/usr/bin/env node
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Command } from "commander";
import {
  cmdAnalyze,
  cmdBudget,
  cmdCertify,
  cmdFixtures,
  cmdInit,
  cmdReport,
} from "./commands.js";

const pkgDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const repoRoot = path.resolve(pkgDir, "..", "..");

const program = new Command();

program
  .name("audiosure")
  .description("Cross-platform game audio certification: budgets, profiling, fix reports")
  .version("0.1.0");

program
  .command("init")
  .description("Create .audiosure.json in the current directory")
  .argument("[input]", "project path to audit", ".")
  .action(async (input: string) => {
    process.exitCode = await cmdInit(process.cwd(), input);
  });

program
  .command("analyze")
  .description("Parse a project and print the extracted audio model")
  .argument("<input>", "Wwise, FMOD, Unity, or Unreal project path")
  .option("--engine <engine>", "force engine: wwise|fmod|unity|unreal")
  .option("--json", "output raw JSON model")
  .action(async (input: string, opts: { engine?: string; json?: boolean }) => {
    process.exitCode = await cmdAnalyze(input, opts.engine, !!opts.json);
  });

program
  .command("certify")
  .description("Run the full certification pipeline and write pass/fail reports")
  .argument("[input]", "project path (defaults to .audiosure.json)")
  .option("--input <path>", "project path (overrides positional)")
  .option("--platforms <list>", "comma list or 'all' (pc,ps5,xbox,switch2,mobile,vr)")
  .option("--engine <engine>", "force engine: wwise|fmod|unity|unreal")
  .option("--runner <runner>", "local | cloud", "local")
  .option("--tier <tier>", "starter | pro | studio")
  .option("--out <dir>", "report output directory", "reports")
  .option("--captures <file>", "profiler capture JSON to override estimates")
  .option("--seed <n>", "seed for simulated run variance", (v) => Number(v))
  .option("--noise", "add deterministic run-to-run variance")
  .option("-q, --quiet", "suppress progress output")
  .action(async (input: string | undefined, opts) => {
    process.exitCode = await cmdCertify(process.cwd(), {
      input: opts.input ?? input,
      engine: opts.engine,
      platforms: opts.platforms,
      runner: opts.runner,
      tier: opts.tier,
      out: opts.out,
      captures: opts.captures,
      seed: opts.seed,
      noise: !!opts.noise,
      quiet: !!opts.quiet,
    });
  });

program
  .command("report")
  .description("Re-render a saved report")
  .argument("<file>", "report json (or a directory with latest.json)")
  .option("--format <format>", "md | json | html", "md")
  .option("--out <file>", "write to file instead of stdout")
  .action(async (file: string, opts: { format?: string; out?: string }) => {
    process.exitCode = await cmdReport(file, opts.format ?? "md", opts.out);
  });

const budget = program.command("budget").description("Inspect and validate platform budgets");
budget
  .command("show")
  .argument("[platform]", "pc|ps5|xbox|switch2|mobile|vr")
  .option("--file <path>", "budget overrides JSON")
  .action(async (platform: string | undefined, opts: { file?: string }) => {
    process.exitCode = await cmdBudget("show", platform, opts.file);
  });
budget
  .command("validate")
  .option("--file <path>", "budget overrides JSON to validate")
  .action(async (opts: { file?: string }) => {
    process.exitCode = await cmdBudget("validate", undefined, opts.file);
  });

const fixtures = program.command("fixtures").description("Generate demo projects");
fixtures
  .command("generate")
  .option("--out <dir>", "output directory", "fixtures")
  .action(async (opts: { out?: string }) => {
    process.exitCode = await cmdFixtures(path.resolve(process.cwd(), opts.out ?? "fixtures"));
  });

program
  .command("dash")
  .description("Start the web dashboard against the reports directory")
  .option("--reports <dir>", "reports directory", "reports")
  .option("--no-start", "just print the command to run")
  .action(async (opts: { reports?: string; start?: boolean }) => {
    const reportsDir = path.resolve(process.cwd(), opts.reports ?? "reports");
    if (opts.start === false) {
      console.log(`AUDIOSURE_REPORTS="${reportsDir}" pnpm --filter @audiosure/dashboard dev`);
      return;
    }
    console.log(`Starting dashboard (reports: ${reportsDir})...`);
    const child = spawn("pnpm", ["--filter", "@audiosure/dashboard", "dev"], {
      cwd: repoRoot,
      stdio: "inherit",
      shell: true,
      env: { ...process.env, AUDIOSURE_REPORTS: reportsDir },
    });
    child.on("exit", (code) => (process.exitCode = code ?? 0));
  });

program.parseAsync(process.argv).catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
