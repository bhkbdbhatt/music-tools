#!/usr/bin/env node
import { promises as fs } from "node:fs";
import path from "node:path";
import type { AuditConfig, PlatformId, TierId } from "@audiosure/core";
import { PLATFORM_IDS } from "@audiosure/core";

export const CONFIG_NAME = ".audiosure.json";

export function defaultConfig(): AuditConfig {
  return {
    project: { input: "." },
    platforms: ["pc", "ps5", "mobile"],
    tier: "pro",
    seed: 1337,
    noise: false,
  };
}

export async function loadConfig(cwd: string): Promise<AuditConfig | null> {
  const p = path.join(cwd, CONFIG_NAME);
  try {
    const raw = await fs.readFile(p, "utf8");
    const parsed = JSON.parse(raw) as AuditConfig;
    return { ...defaultConfig(), ...parsed, project: { ...defaultConfig().project, ...parsed.project } };
  } catch {
    return null;
  }
}

export async function saveConfig(cwd: string, config: AuditConfig): Promise<string> {
  const p = path.join(cwd, CONFIG_NAME);
  await fs.writeFile(p, JSON.stringify(config, null, 2) + "\n", "utf8");
  return p;
}

export function parsePlatforms(input: string): PlatformId[] {
  if (!input || input === "all") return [...PLATFORM_IDS];
  const parts = input
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean) as PlatformId[];
  const invalid = parts.filter((p) => !PLATFORM_IDS.includes(p));
  if (invalid.length) {
    throw new Error(`Unknown platform(s): ${invalid.join(", ")}. Valid: ${PLATFORM_IDS.join(", ")}`);
  }
  return [...new Set(parts)];
}

export function resolveTier(v: string | undefined): TierId {
  if (v === "starter" || v === "pro" || v === "studio") return v;
  return "pro";
}
