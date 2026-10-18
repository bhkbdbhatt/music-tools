from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from audiosure.core.budgets import get_budget, merge_budgets
from audiosure.core.report import build_platform_certification, build_report
from audiosure.core.types import BankInfo, CertificationReport, PlatformBudget, ProjectModel, js_round
from audiosure.engine.captures import ProfilerCapture, apply_captures
from audiosure.engine.estimator import EstimateOptions, estimate_metrics
from audiosure.engine.recommender import recommend_fixes
from audiosure.parsers.detect import parse_project


@dataclass
class AuditOptions:
    input: str
    platforms: List[str]
    engine: Optional[str] = None
    budget_overrides: Optional[List[PlatformBudget]] = None
    captures: Optional[List[ProfilerCapture]] = None
    seed: Optional[int] = None
    noise: Optional[bool] = None
    tier: Optional[str] = None
    project_name: Optional[str] = None
    est_options: Optional[EstimateOptions] = None


@dataclass
class AuditResult:
    report: CertificationReport
    model: ProjectModel


def run_audit(opts: AuditOptions) -> AuditResult:
    model = parse_project(opts.input, opts.engine)
    budgets = merge_budgets(opts.budget_overrides) if opts.budget_overrides else None
    captures = opts.captures or []

    certs = []
    for platform in opts.platforms:
        budget = next((b for b in budgets if b.platform == platform), None) if budgets else None
        if budget is None:
            budget = get_budget(platform)
        est_opts = opts.est_options or EstimateOptions(seed=opts.seed, noise=opts.noise)
        estimated = estimate_metrics(model, platform, est_opts)
        metrics, _source, _keys = apply_captures(estimated, captures)
        certs.append(build_platform_certification(platform, budget, metrics))

    recommendations = recommend_fixes(model, certs, opts.platforms)

    report = build_report(
        project=_project_info(opts, model),
        runner=_runner_summary(),
        platforms=certs,
        recommendations=recommendations,
        tier=opts.tier or "pro",
    )

    return AuditResult(report=report, model=model)


def _project_info(opts: AuditOptions, model: ProjectModel):
    from audiosure.core.types import ProjectInfo

    return ProjectInfo(
        name=opts.project_name or model.name,
        engine=model.engine,
        input_path=opts.input,
    )


def _runner_summary():
    from audiosure.core.types import RunSummary

    return RunSummary(kind="local", name="local-runner", duration_ms=0)


def summarize_banks(banks: List[BankInfo]):
    mb = 1024 * 1024
    return {
        "count": len(banks),
        "totalMB": js_round(sum(b.size_bytes for b in banks) / mb),
        "memoryMB": js_round(sum(b.memory_bytes for b in banks) / mb),
    }
