from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from audiosure.core.types import Tier

TIERS: Dict[str, Tier] = {
    "starter": Tier(
        id="starter",
        name="Starter",
        price_monthly_usd=79,
        max_platforms=3,
        max_builds_per_month=10,
        api_access=False,
        team_seats=1,
        features=[
            "3 platforms",
            "10 certification builds / month",
            "CLI + dashboard",
            "Budget violation flags",
            "Fix report generation",
        ],
    ),
    "pro": Tier(
        id="pro",
        name="Pro",
        price_monthly_usd=199,
        max_platforms=6,
        max_builds_per_month=50,
        api_access=False,
        team_seats=5,
        features=[
            "All platforms (PC, PS5, Xbox, Switch 2, mobile, VR)",
            "50 certification builds / month",
            "CLI + dashboard",
            "Budget violation flags",
            "Fix report generation",
            "Run history + regression diffs",
            "5 team seats",
        ],
    ),
    "studio": Tier(
        id="studio",
        name="Studio",
        price_monthly_usd=499,
        max_platforms=6,
        max_builds_per_month=None,
        api_access=True,
        team_seats=None,
        features=[
            "Unlimited platforms",
            "Unlimited certification builds",
            "REST API access",
            "Unlimited team seats",
            "Cloud runner priority queue",
            "Custom budget profiles",
            "CI webhook notifications",
        ],
    ),
}


def get_tier(tier_id: str) -> Tier:
    return TIERS.get(tier_id) or TIERS["starter"]


@dataclass
class TierGateResult:
    allowed: bool
    reason: Optional[str] = None


def check_platform_limit(tier_id: str, platform_count: int) -> TierGateResult:
    tier = get_tier(tier_id)
    if tier.max_platforms is None:
        return TierGateResult(allowed=True)
    if platform_count > tier.max_platforms:
        return TierGateResult(
            allowed=False,
            reason=(
                f'Tier "{tier.name}" allows {tier.max_platforms} platforms per run; '
                f"you requested {platform_count}. Upgrade for all platforms."
            ),
        )
    return TierGateResult(allowed=True)


def check_build_limit(tier_id: str, builds_this_month: int) -> TierGateResult:
    tier = get_tier(tier_id)
    if tier.max_builds_per_month is None:
        return TierGateResult(allowed=True)
    if builds_this_month >= tier.max_builds_per_month:
        return TierGateResult(
            allowed=False,
            reason=(
                f'Tier "{tier.name}" includes {tier.max_builds_per_month} builds/month; '
                f"{builds_this_month} already used. Upgrade or wait for next cycle."
            ),
        )
    return TierGateResult(allowed=True)
