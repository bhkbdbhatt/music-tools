from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from audiosure.core.types import MetricsSnapshot


@dataclass
class ProfilerCapture:
    platform: str
    metrics: Dict[str, float] = field(default_factory=dict)
    captured_at: str | None = None
    source: str | None = None


@dataclass
class CaptureFile:
    captures: List[ProfilerCapture] = field(default_factory=list)


def apply_captures(
    estimated: MetricsSnapshot, captures: List[ProfilerCapture]
) -> Tuple[MetricsSnapshot, str, List[str]]:
    match = next((c for c in captures if c.platform == estimated.platform), None)
    if not match:
        return estimated, "estimate", []
    captured_keys = list(match.metrics.keys())
    merged = MetricsSnapshot.from_dict(estimated.to_dict())
    for k, v in match.metrics.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            merged[k] = v
    return merged, "capture", captured_keys


def capture_from_dict(d: Dict[str, Any]) -> ProfilerCapture:
    return ProfilerCapture(
        platform=d["platform"],
        metrics=d.get("metrics") or {},
        captured_at=d.get("capturedAt"),
        source=d.get("source"),
    )
