import { promises as fs } from "node:fs";
import path from "node:path";
import type { EngineKind, ProjectModel } from "@audiosure/core";
import { parseWwise } from "./wwise.js";
import { parseFmod } from "./fmod.js";
import { parseUnity } from "./unity.js";
import { parseUnreal } from "./unreal.js";
import { pathExists, walkFiles } from "./util.js";

export async function detectEngine(root: string): Promise<EngineKind | null> {
  const ret = (e: EngineKind) => e;
  const files = await walkFiles(root, () => true);
  const has = (re: RegExp) => files.some((f) => re.test(f));

  if (has(/\.uproject$/i) || has(/AudioInventory\.json$/i)) return ret("unreal");
  if (has(/\.wproj$/i) || has(/\.wwu$/i) || has(/SoundBanksInfo\.(xml|json)$/i)) return ret("wwise");
  if (has(/\.fspro$/i)) return ret("fmod");
  if (has(/\.mixer$/i) || has(/\.unity$/i) || has(/\.prefab$/i)) return ret("unity");

  const banks = await walkFiles(root, (rel) => /\.bank$/i.test(rel));
  for (const b of banks) {
    const buf = await fs.readFile(b);
    if (buf.length >= 4 && buf.toString("ascii", 0, 4) === "FSB5") return ret("fmod");
  }
  if (has(/\.bnk$/i)) return ret("wwise");

  const metas = await walkFiles(root, (rel) => /\.meta$/i.test(rel));
  for (const m of metas.slice(0, 50)) {
    const text = await fs.readFile(m, "utf8").catch(() => "");
    if (/AudioImporter:|AudioClip:/.test(text)) return ret("unity");
  }
  return null;
}

const PARSERS: Record<EngineKind, (root: string) => Promise<ProjectModel>> = {
  wwise: parseWwise,
  fmod: parseFmod,
  unity: parseUnity,
  unreal: parseUnreal,
};

export async function parseProject(root: string, engine?: EngineKind): Promise<ProjectModel> {
  if (!(await pathExists(root))) {
    throw new Error(`Input path does not exist: ${root}`);
  }
  const resolved = path.resolve(root);
  const kind = engine ?? (await detectEngine(resolved));
  if (!kind) {
    throw new Error(
      `Could not detect audio engine at ${resolved}. Pass --engine wwise|fmod|unity|unreal.`,
    );
  }
  const model = await PARSERS[kind](resolved);
  if (!model.name || model.name === ".") model.name = path.basename(resolved);
  return model;
}
