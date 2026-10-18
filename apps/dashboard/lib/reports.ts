import fs from "node:fs";
import path from "node:path";
import type { CertificationReport } from "@audiosure/core";

export interface RunEntry {
  id: string;
  createdAt: string;
  project: string;
  engine: string;
  runner: string;
  overallPass: boolean;
  platforms: Array<{ platform: string; passed: boolean; score: number; fails: number; warns: number }>;
  dir: string;
  tier?: string;
}

export function reportsDir(): string {
  const env = process.env.AUDIOSURE_REPORTS;
  if (env) return path.resolve(env);
  return path.resolve(process.cwd(), "..", "..", "reports");
}

function findIndexFiles(dir: string, out: string[] = []): string[] {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    const abs = path.join(dir, e.name);
    if (e.isDirectory()) findIndexFiles(abs, out);
    else if (e.name === "index.json") out.push(abs);
  }
  return out;
}

export function listRuns(): RunEntry[] {
  const root = reportsDir();
  const files = findIndexFiles(root);
  const runs: RunEntry[] = [];
  for (const file of files) {
    const dir = path.dirname(file);
    try {
      const entries = JSON.parse(fs.readFileSync(file, "utf8")) as Omit<RunEntry, "dir">[];
      for (const e of entries) runs.push({ ...e, dir });
    } catch {
      continue;
    }
  }
  return runs.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export function getRun(id: string): { entry: RunEntry; report: CertificationReport } | null {
  const runs = listRuns();
  const entry = runs.find((r) => r.id === id);
  if (!entry) return null;
  const file = path.join(entry.dir, `${id}.json`);
  try {
    const report = JSON.parse(fs.readFileSync(file, "utf8")) as CertificationReport;
    return { entry, report };
  } catch {
    return null;
  }
}

export function listRunsRaw(): Array<Record<string, unknown>> {
  return listRuns() as unknown as Array<Record<string, unknown>>;
}
