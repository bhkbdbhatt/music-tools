import { promises as fs } from "node:fs";
import path from "node:path";
import type { CertificationReport } from "@audiosure/core";
import { renderHtml, renderJson, renderMarkdown } from "./reporters.js";

export interface ReportIndexEntry {
  id: string;
  createdAt: string;
  project: string;
  engine: string;
  runner: string;
  overallPass: boolean;
  platforms: Array<{ platform: string; passed: boolean; score: number; fails: number; warns: number }>;
}

export async function saveReport(outDir: string, report: CertificationReport): Promise<{
  json: string;
  md: string;
  html: string;
  latestJson: string;
}> {
  const abs = path.resolve(outDir);
  await fs.mkdir(abs, { recursive: true });

  const jsonPath = path.join(abs, `${report.id}.json`);
  const mdPath = path.join(abs, `${report.id}.md`);
  const htmlPath = path.join(abs, `${report.id}.html`);

  await fs.writeFile(jsonPath, renderJson(report) + "\n", "utf8");
  await fs.writeFile(mdPath, renderMarkdown(report), "utf8");
  await fs.writeFile(htmlPath, renderHtml(report), "utf8");

  const latestJson = path.join(abs, "latest.json");
  await fs.writeFile(latestJson, renderJson(report) + "\n", "utf8");
  await fs.writeFile(path.join(abs, "latest.md"), renderMarkdown(report), "utf8");
  await fs.writeFile(path.join(abs, "latest.html"), renderHtml(report), "utf8");

  await appendIndex(abs, report);

  return { json: jsonPath, md: mdPath, html: htmlPath, latestJson };
}

async function appendIndex(abs: string, report: CertificationReport): Promise<void> {
  const indexPath = path.join(abs, "index.json");
  let entries: ReportIndexEntry[] = [];
  try {
    entries = JSON.parse(await fs.readFile(indexPath, "utf8")) as ReportIndexEntry[];
  } catch {
    entries = [];
  }
  const entry: ReportIndexEntry = {
    id: report.id,
    createdAt: report.createdAt,
    project: report.project.name,
    engine: report.project.engine,
    runner: report.runner.name,
    overallPass: report.overallPass,
    platforms: report.platforms.map((p) => ({
      platform: p.platform,
      passed: p.passed,
      score: p.score,
      fails: p.failCount,
      warns: p.warnCount,
    })),
  };
  entries = [entry, ...entries.filter((e) => e.id !== entry.id)].slice(0, 200);
  await fs.writeFile(indexPath, JSON.stringify(entries, null, 2) + "\n", "utf8");
}

export async function listReports(outDir: string): Promise<ReportIndexEntry[]> {
  try {
    return JSON.parse(await fs.readFile(path.join(path.resolve(outDir), "index.json"), "utf8")) as ReportIndexEntry[];
  } catch {
    return [];
  }
}

export async function loadReport(file: string): Promise<CertificationReport> {
  const abs = path.resolve(file);
  const st = await fs.stat(abs).catch(() => null);
  const target = st?.isDirectory() ? path.join(abs, "latest.json") : abs;
  return JSON.parse(await fs.readFile(target, "utf8")) as CertificationReport;
}
