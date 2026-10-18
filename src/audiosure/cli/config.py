from __future__ import annotations

import json
import os
from typing import Optional

from audiosure.core.types import PLATFORM_IDS, AuditConfig, ProjectConfig

CONFIG_NAME = ".audiosure.json"


def default_config() -> AuditConfig:
    return AuditConfig(
        project=ProjectConfig(input="."),
        platforms=["pc", "ps5", "mobile"],
        tier="pro",
        seed=1337,
        noise=False,
    )


def load_config(cwd: str) -> Optional[AuditConfig]:
    p = os.path.join(cwd, CONFIG_NAME)
    try:
        with open(p, "r", encoding="utf-8") as f:
            parsed = json.load(f)
    except (OSError, ValueError):
        return None
    base = default_config()
    project_raw = parsed.get("project") or {}
    return AuditConfig(
        project=ProjectConfig(
            input=project_raw.get("input", base.project.input),
            name=project_raw.get("name"),
            engine=project_raw.get("engine"),
        ),
        platforms=parsed.get("platforms", base.platforms),
        tier=parsed.get("tier", base.tier),
        budget_overrides_path=parsed.get("budgetOverridesPath"),
        seed=parsed.get("seed", base.seed),
        noise=parsed.get("noise", base.noise),
    )


def save_config(cwd: str, config: AuditConfig) -> str:
    p = os.path.join(cwd, CONFIG_NAME)
    data = {
        "project": {
            k: v
            for k, v in {
                "input": config.project.input,
                "name": config.project.name,
                "engine": config.project.engine,
            }.items()
            if v is not None
        },
        "platforms": config.platforms,
        "tier": config.tier,
    }
    if config.budget_overrides_path is not None:
        data["budgetOverridesPath"] = config.budget_overrides_path
    if config.seed is not None:
        data["seed"] = config.seed
    if config.noise is not None:
        data["noise"] = config.noise
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return p


def parse_platforms(value: str) -> list:
    if not value or value == "all":
        return list(PLATFORM_IDS)
    parts = [s.strip().lower() for s in value.split(",") if s.strip()]
    invalid = [p for p in parts if p not in PLATFORM_IDS]
    if invalid:
        raise ValueError(f"Unknown platform(s): {', '.join(invalid)}. Valid: {', '.join(PLATFORM_IDS)}")
    seen = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    return seen


def resolve_tier(v: Optional[str]) -> str:
    if v in ("starter", "pro", "studio"):
        return v
    return "pro"
