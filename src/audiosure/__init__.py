"""Cross-platform game audio certification: budgets, profiling, fix reports."""

__version__ = "0.1.0"

from audiosure.core import (  # noqa: F401
    DEFAULT_BUDGETS,
    PLATFORM_IDS,
    TIERS,
    build_platform_certification,
    build_report,
    check_build_limit,
    check_platform_limit,
    evaluate_limits,
    get_budget,
    get_tier,
    merge_budgets,
    violation_key,
)
