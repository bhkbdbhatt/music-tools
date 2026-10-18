import { promises as fs } from "node:fs";
import path from "node:path";

interface UsageRecord {
  month: string;
  builds: number;
  history: Array<{ at: string; platforms: string[]; input: string; passed: boolean }>;
}

const USAGE_DIR = ".audiosure";
const USAGE_FILE = "usage.json";

function monthKey(d = new Date()): string {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

async function read(cwd: string): Promise<UsageRecord> {
  const p = path.join(cwd, USAGE_DIR, USAGE_FILE);
  try {
    const rec = JSON.parse(await fs.readFile(p, "utf8")) as UsageRecord;
    if (rec.month === monthKey()) return rec;
    return { month: monthKey(), builds: 0, history: rec.history ?? [] };
  } catch {
    return { month: monthKey(), builds: 0, history: [] };
  }
}

export async function buildsThisMonth(cwd: string): Promise<number> {
  return (await read(cwd)).builds;
}

export async function recordBuild(
  cwd: string,
  entry: { platforms: string[]; input: string; passed: boolean },
): Promise<UsageRecord> {
  const rec = await read(cwd);
  rec.builds += 1;
  rec.history.unshift({ at: new Date().toISOString(), ...entry });
  rec.history = rec.history.slice(0, 100);
  const dir = path.join(cwd, USAGE_DIR);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(path.join(dir, USAGE_FILE), JSON.stringify(rec, null, 2) + "\n", "utf8");
  return rec;
}
