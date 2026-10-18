from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from audiosure.core.types import (
    METRIC_UNITS,
    CertificationReport,
    FixRecommendation,
    MetricsSnapshot,
    PlatformBudget,
    PlatformCertification,
    ProjectInfo,
    ReportSummary,
    RunSummary,
    Severity,
    Violation,
    js_round,
    violation_key,
)

SEVERITY_RANK = {"fail": 2, "warn": 1, "info": 0}


def _round2(n: float) -> float:
    return js_round(n * 100) / 100


def _fmt(n: float) -> str:
    if float(n).is_integer():
        return str(int(n))
    return f"{n:.2f}"


def evaluate_limits(platform: str, budget: PlatformBudget, metrics: MetricsSnapshot) -> List[Violation]:
    out: List[Violation] = []
    for metric, limit in budget.limits.items():
        try:
            actual = metrics[metric]
        except KeyError:
            continue
        if actual is None:
            continue
        unit = METRIC_UNITS[metric]
        warn_ratio = limit.warn_ratio if limit.warn_ratio is not None else 0.8

        if limit.max is not None and actual > limit.max:
            ratio = actual / limit.max
            severity: Severity = "fail" if ratio > 1 else "warn"
            message = (
                f"{budget.display_name}: {metric} {_fmt(actual)}{unit} exceeds budget {limit.max}{unit}"
                if severity == "fail"
                else (
                    f"{budget.display_name}: {metric} {_fmt(actual)}{unit} at "
                    f"{js_round(ratio * 100)}% of {limit.max}{unit} budget"
                )
            )
            out.append(
                Violation(
                    key=violation_key(platform, metric),
                    platform=platform,
                    metric=metric,
                    actual=_round2(actual),
                    budget=limit.max,
                    unit=unit,
                    severity=severity,
                    message=message,
                )
            )
        if limit.min is not None and actual < limit.min:
            out.append(
                Violation(
                    key=violation_key(platform, metric),
                    platform=platform,
                    metric=metric,
                    actual=_round2(actual),
                    budget=limit.min,
                    unit=unit,
                    severity="fail",
                    message=(
                        f"{budget.display_name}: {metric} {_fmt(actual)}{unit} "
                        f"below required minimum {limit.min}{unit}"
                    ),
                )
            )
    return out


def score_platform(violations: List[Violation]) -> int:
    score = 100
    for v in violations:
        if v.severity == "fail":
            score -= 15
        elif v.severity == "warn":
            score -= 5
        else:
            score -= 1
    return max(0, min(100, score))


def build_platform_certification(
    platform: str, budget: PlatformBudget, metrics: MetricsSnapshot
) -> PlatformCertification:
    violations = evaluate_limits(platform, budget, metrics)
    fail_count = sum(1 for v in violations if v.severity == "fail")
    warn_count = sum(1 for v in violations if v.severity == "warn")
    return PlatformCertification(
        platform=platform,
        passed=fail_count == 0,
        score=score_platform(violations),
        fail_count=fail_count,
        warn_count=warn_count,
        metrics=metrics,
        violations=violations,
    )


def build_report(
    *,
    project: ProjectInfo,
    runner: RunSummary,
    platforms: List[PlatformCertification],
    recommendations: List[FixRecommendation],
    tier: str,
    report_id: Optional[str] = None,
    created_at: Optional[str] = None,
) -> CertificationReport:
    total_fail = sum(p.fail_count for p in platforms)
    total_warn = sum(p.warn_count for p in platforms)
    passed_platforms = sum(1 for p in platforms if p.passed)
    sorted_recs = sorted(recommendations, key=lambda r: (r.priority, r.id))
    return CertificationReport(
        id=report_id or str(uuid.uuid4()),
        created_at=created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        project=project,
        runner=runner,
        platforms=platforms,
        recommendations=sorted_recs,
        overall_pass=all(p.passed for p in platforms),
        summary=ReportSummary(
            total_fail=total_fail,
            total_warn=total_warn,
            passed_platforms=passed_platforms,
            total_platforms=len(platforms),
        ),
        tier=tier,
    )


def max_severity(violations: List[Violation]) -> Optional[Severity]:
    best: Optional[Severity] = None
    for v in violations:
        if not best or SEVERITY_RANK[v.severity] > SEVERITY_RANK[best]:
            best = v.severity
    return best


def _violation_from_dict(d: Dict[str, Any]) -> Violation:
    return Violation(
        key=d["key"],
        platform=d["platform"],
        metric=d["metric"],
        actual=d["actual"],
        budget=d["budget"],
        unit=d["unit"],
        severity=d["severity"],
        message=d["message"],
        asset_id=d.get("assetId"),
    )


def _recommendation_from_dict(d: Dict[str, Any]) -> FixRecommendation:
    return FixRecommendation(
        id=d["id"],
        rule_id=d["ruleId"],
        title=d["title"],
        detail=d["detail"],
        effort=d["effort"],
        priority=d["priority"],
        platform_targets=d.get("platformTargets", []),
        violation_keys=d.get("violationKeys", []),
        estimated_savings_mb=d.get("estimatedSavingsMB"),
        estimated_savings_kbps=d.get("estimatedSavingsKbps"),
        estimated_latency_ms=d.get("estimatedLatencyMs"),
    )


def certification_report_from_dict(d: Dict[str, Any]) -> CertificationReport:
    platforms = [
        PlatformCertification(
            platform=p["platform"],
            passed=p["passed"],
            score=p["score"],
            fail_count=p["failCount"],
            warn_count=p["warnCount"],
            metrics=MetricsSnapshot.from_dict(p["metrics"]),
            violations=[_violation_from_dict(v) for v in p.get("violations", [])],
        )
        for p in d["platforms"]
    ]
    s = d["summary"]
    return CertificationReport(
        id=d["id"],
        created_at=d["createdAt"],
        project=ProjectInfo(
            name=d["project"]["name"],
            engine=d["project"]["engine"],
            input_path=d["project"]["inputPath"],
        ),
        runner=RunSummary(kind=d["runner"]["kind"], name=d["runner"]["name"], duration_ms=d["runner"]["durationMs"]),
        platforms=platforms,
        recommendations=[_recommendation_from_dict(r) for r in d.get("recommendations", [])],
        overall_pass=d["overallPass"],
        summary=ReportSummary(
            total_fail=s["totalFail"],
            total_warn=s["totalWarn"],
            passed_platforms=s["passedPlatforms"],
            total_platforms=s["totalPlatforms"],
        ),
        tier=d["tier"],
    )
