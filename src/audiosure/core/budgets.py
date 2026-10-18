from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from audiosure.core.types import PLATFORM_IDS, MetricLimit, PlatformBudget


def _limit(max: Optional[float] = None, min: Optional[float] = None, warn_ratio: Optional[float] = None) -> MetricLimit:
    return MetricLimit(max=max, min=min, warn_ratio=warn_ratio)


DEFAULT_BUDGETS: List[PlatformBudget] = [
    PlatformBudget(
        platform="pc",
        display_name="PC (Steam/Epic)",
        limits={
            "memoryFootprintMB": _limit(max=512, warn_ratio=0.85),
            "audioThreadLatencyMs": _limit(max=30, warn_ratio=0.8),
            "cpuAudioPct": _limit(max=12, warn_ratio=0.75),
            "gpuDspPct": _limit(max=6, warn_ratio=0.75),
            "streamingBandwidthKbps": _limit(max=512, warn_ratio=0.8),
            "peakConcurrentVoices": _limit(max=128, warn_ratio=0.8),
        },
    ),
    PlatformBudget(
        platform="ps5",
        display_name="PlayStation 5",
        limits={
            "memoryFootprintMB": _limit(max=256, warn_ratio=0.85),
            "audioThreadLatencyMs": _limit(max=18, warn_ratio=0.8),
            "cpuAudioPct": _limit(max=6, warn_ratio=0.75),
            "gpuDspPct": _limit(max=4, warn_ratio=0.75),
            "streamingBandwidthKbps": _limit(max=1024, warn_ratio=0.85),
            "peakConcurrentVoices": _limit(max=96, warn_ratio=0.8),
        },
    ),
    PlatformBudget(
        platform="xbox",
        display_name="Xbox Series X|S",
        limits={
            "memoryFootprintMB": _limit(max=256, warn_ratio=0.85),
            "audioThreadLatencyMs": _limit(max=18, warn_ratio=0.8),
            "cpuAudioPct": _limit(max=6, warn_ratio=0.75),
            "gpuDspPct": _limit(max=4, warn_ratio=0.75),
            "streamingBandwidthKbps": _limit(max=1024, warn_ratio=0.85),
            "peakConcurrentVoices": _limit(max=96, warn_ratio=0.8),
        },
    ),
    PlatformBudget(
        platform="switch2",
        display_name="Nintendo Switch 2",
        limits={
            "memoryFootprintMB": _limit(max=128, warn_ratio=0.8),
            "audioThreadLatencyMs": _limit(max=25, warn_ratio=0.8),
            "cpuAudioPct": _limit(max=10, warn_ratio=0.75),
            "gpuDspPct": _limit(max=5, warn_ratio=0.75),
            "streamingBandwidthKbps": _limit(max=48, warn_ratio=0.75),
            "peakConcurrentVoices": _limit(max=64, warn_ratio=0.8),
        },
    ),
    PlatformBudget(
        platform="mobile",
        display_name="Mobile (iOS/Android)",
        limits={
            "memoryFootprintMB": _limit(max=96, warn_ratio=0.8),
            "audioThreadLatencyMs": _limit(max=20, warn_ratio=0.75),
            "cpuAudioPct": _limit(max=8, warn_ratio=0.7),
            "gpuDspPct": _limit(max=2, warn_ratio=0.7),
            "streamingBandwidthKbps": _limit(max=128, warn_ratio=0.8),
            "batteryDrainMw": _limit(max=150, warn_ratio=0.8),
            "peakConcurrentVoices": _limit(max=48, warn_ratio=0.8),
        },
    ),
    PlatformBudget(
        platform="vr",
        display_name="VR Headset (Quest-class)",
        limits={
            "memoryFootprintMB": _limit(max=192, warn_ratio=0.85),
            "audioThreadLatencyMs": _limit(max=10, warn_ratio=0.7),
            "cpuAudioPct": _limit(max=8, warn_ratio=0.7),
            "gpuDspPct": _limit(max=6, warn_ratio=0.75),
            "streamingBandwidthKbps": _limit(max=256, warn_ratio=0.8),
            "batteryDrainMw": _limit(max=400, warn_ratio=0.8),
            "peakConcurrentVoices": _limit(max=64, warn_ratio=0.8),
        },
    ),
]


def get_budget(platform: str) -> PlatformBudget:
    for b in DEFAULT_BUDGETS:
        if b.platform == platform:
            return b
    raise ValueError(f"No default budget for platform: {platform}")


def _as_limit(v: Union[MetricLimit, Dict[str, Any]]) -> MetricLimit:
    if isinstance(v, MetricLimit):
        return v
    return MetricLimit.from_dict(v)


def merge_budgets(overrides: Optional[List[Union[PlatformBudget, Dict[str, Any]]]] = None) -> List[PlatformBudget]:
    if not overrides:
        return list(DEFAULT_BUDGETS)
    by_id = {b.platform: b for b in DEFAULT_BUDGETS}
    for ov in overrides:
        if isinstance(ov, PlatformBudget):
            platform = ov.platform
            display_name = ov.display_name
            ov_limits: Dict[str, Any] = {
                k: {"max": v.max, "min": v.min, "warnRatio": v.warn_ratio} for k, v in ov.limits.items()
            }
        else:
            platform = ov.get("platform")
            display_name = ov.get("displayName")
            ov_limits = ov.get("limits") or {}
        base = by_id.get(platform)
        if base is None:
            by_id[platform] = PlatformBudget(
                platform=platform,
                display_name=display_name or platform,
                limits={k: _as_limit(v) for k, v in ov_limits.items()},
            )
            continue
        merged: Dict[str, Any] = {
            **{k: {"max": v.max, "min": v.min, "warnRatio": v.warn_ratio} for k, v in base.limits.items()},
            **ov_limits,
        }
        by_id[platform] = PlatformBudget(
            platform=platform,
            display_name=display_name or base.display_name,
            limits={k: _as_limit(v) for k, v in merged.items()},
        )
    return [by_id[p] for p in PLATFORM_IDS if p in by_id]
