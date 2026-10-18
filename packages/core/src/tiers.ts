import type { Tier, TierId } from "./types.js";

export const TIERS: Record<TierId, Tier> = {
  starter: {
    id: "starter",
    name: "Starter",
    priceMonthlyUsd: 79,
    maxPlatforms: 3,
    maxBuildsPerMonth: 10,
    apiAccess: false,
    teamSeats: 1,
    features: [
      "3 platforms",
      "10 certification builds / month",
      "CLI + dashboard",
      "Budget violation flags",
      "Fix report generation",
    ],
  },
  pro: {
    id: "pro",
    name: "Pro",
    priceMonthlyUsd: 199,
    maxPlatforms: 6,
    maxBuildsPerMonth: 50,
    apiAccess: false,
    teamSeats: 5,
    features: [
      "All platforms (PC, PS5, Xbox, Switch 2, mobile, VR)",
      "50 certification builds / month",
      "CLI + dashboard",
      "Budget violation flags",
      "Fix report generation",
      "Run history + regression diffs",
      "5 team seats",
    ],
  },
  studio: {
    id: "studio",
    name: "Studio",
    priceMonthlyUsd: 499,
    maxPlatforms: 6,
    maxBuildsPerMonth: null,
    apiAccess: true,
    teamSeats: null,
    features: [
      "Unlimited platforms",
      "Unlimited certification builds",
      "REST API access",
      "Unlimited team seats",
      "Cloud runner priority queue",
      "Custom budget profiles",
      "CI webhook notifications",
    ],
  },
};

export function getTier(id: TierId): Tier {
  return TIERS[id] ?? TIERS.starter;
}

export interface TierGateResult {
  allowed: boolean;
  reason?: string;
}

export function checkPlatformLimit(tierId: TierId, platformCount: number): TierGateResult {
  const tier = getTier(tierId);
  if (tier.maxPlatforms === null) return { allowed: true };
  if (platformCount > tier.maxPlatforms) {
    return {
      allowed: false,
      reason: `Tier "${tier.name}" allows ${tier.maxPlatforms} platforms per run; you requested ${platformCount}. Upgrade for all platforms.`,
    };
  }
  return { allowed: true };
}

export function checkBuildLimit(tierId: TierId, buildsThisMonth: number): TierGateResult {
  const tier = getTier(tierId);
  if (tier.maxBuildsPerMonth === null) return { allowed: true };
  if (buildsThisMonth >= tier.maxBuildsPerMonth) {
    return {
      allowed: false,
      reason: `Tier "${tier.name}" includes ${tier.maxBuildsPerMonth} builds/month; ${buildsThisMonth} already used. Upgrade or wait for next cycle.`,
    };
  }
  return { allowed: true };
}
