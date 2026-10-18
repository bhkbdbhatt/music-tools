from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Dict, List, Optional


def js_round(n: float) -> int:
    """Round half away from zero, matching JavaScript Math.round for values >= 0."""
    return math.floor(n + 0.5) if n >= 0 else math.ceil(n - 0.5)

PLATFORM_IDS = ["pc", "ps5", "xbox", "switch2", "mobile", "vr"]
ENGINE_KINDS = ["wwise", "fmod", "unity", "unreal"]
LOAD_TYPES = ["memory", "stream", "preload"]
SEVERITIES = ["info", "warn", "fail"]
EFFORTS = ["trivial", "low", "medium", "high"]
TIER_IDS = ["starter", "pro", "studio"]

PlatformId = str
EngineKind = str
LoadType = str
Severity = str
Effort = str
TierId = str

METRIC_UNITS: Dict[str, str] = {
    "memoryFootprintMB": "MB",
    "inMemoryMB": "MB",
    "streamedMB": "MB",
    "audioThreadLatencyMs": "ms",
    "cpuAudioPct": "%",
    "gpuDspPct": "%",
    "streamingBandwidthKbps": "kbps",
    "batteryDrainMw": "mW",
    "peakConcurrentVoices": "voices",
    "clipCount": "clips",
}

METRIC_KEYS: List[str] = list(METRIC_UNITS.keys())

_METRIC_ATTRS: Dict[str, str] = {
    "memoryFootprintMB": "memory_footprint_mb",
    "inMemoryMB": "in_memory_mb",
    "streamedMB": "streamed_mb",
    "audioThreadLatencyMs": "audio_thread_latency_ms",
    "cpuAudioPct": "cpu_audio_pct",
    "gpuDspPct": "gpu_dsp_pct",
    "streamingBandwidthKbps": "streaming_bandwidth_kbps",
    "batteryDrainMw": "battery_drain_mw",
    "peakConcurrentVoices": "peak_concurrent_voices",
    "clipCount": "clip_count",
}

_FIELD_OVERRIDES: Dict[str, str] = {
    "memory_footprint_mb": "memoryFootprintMB",
    "in_memory_mb": "inMemoryMB",
    "streamed_mb": "streamedMB",
    "estimated_savings_mb": "estimatedSavingsMB",
}

_SNAKE_OVERRIDES: Dict[str, str] = {v: k for k, v in _FIELD_OVERRIDES.items()}


def camelize(name: str) -> str:
    if name in _FIELD_OVERRIDES:
        return _FIELD_OVERRIDES[name]
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def decamelize(name: str) -> str:
    if name in _SNAKE_OVERRIDES:
        return _SNAKE_OVERRIDES[name]
    return re.sub(r"([A-Z])", r"_\1", name).lower()


def to_jsonable(obj: Any) -> Any:
    """Convert dataclasses to camelCase JSON-compatible structures."""
    if is_dataclass(obj) and not isinstance(obj, type):
        out: Dict[str, Any] = {}
        for f in fields(obj):
            v = getattr(obj, f.name)
            if v is None:
                continue
            out[camelize(f.name)] = to_jsonable(v)
        return out
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj


@dataclass
class AudioAsset:
    id: str
    name: str
    duration_sec: float
    channels: int
    sample_rate: int
    codec: str
    load_type: str
    size_bytes: int
    path: Optional[str] = None
    decode_in_memory: Optional[bool] = None
    is_music: Optional[bool] = None
    is_sfx: Optional[bool] = None
    language: Optional[str] = None
    bank_id: Optional[str] = None


@dataclass
class AudioEffect:
    id: str
    name: str
    plugin: str
    params: Dict[str, Any] = field(default_factory=dict)
    bus_id: Optional[str] = None


@dataclass
class AudioBus:
    id: str
    name: str
    effect_ids: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None


@dataclass
class AudioEvent:
    id: str
    name: str
    asset_ids: List[str] = field(default_factory=list)
    bank_id: Optional[str] = None
    max_instances: Optional[int] = None


@dataclass
class BankInfo:
    id: str
    name: str
    size_bytes: int
    memory_bytes: int
    stream_ids: List[str] = field(default_factory=list)
    asset_ids: List[str] = field(default_factory=list)
    language: Optional[str] = None


@dataclass
class ProjectModel:
    engine: str
    name: str
    assets: List[AudioAsset] = field(default_factory=list)
    effects: List[AudioEffect] = field(default_factory=list)
    buses: List[AudioBus] = field(default_factory=list)
    events: List[AudioEvent] = field(default_factory=list)
    banks: List[BankInfo] = field(default_factory=list)
    plugins_used: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: Optional[str] = None


@dataclass
class MetricsSnapshot:
    platform: str
    memory_footprint_mb: float
    in_memory_mb: float
    streamed_mb: float
    audio_thread_latency_ms: float
    cpu_audio_pct: float
    gpu_dsp_pct: float
    streaming_bandwidth_kbps: float
    battery_drain_mw: float
    peak_concurrent_voices: int
    clip_count: int

    def __getitem__(self, key: str) -> float:
        return getattr(self, _METRIC_ATTRS[key])

    def __setitem__(self, key: str, value: float) -> None:
        setattr(self, _METRIC_ATTRS[key], value)

    def to_dict(self) -> Dict[str, Any]:
        return {key: getattr(self, attr) for key, attr in _METRIC_ATTRS.items()}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MetricsSnapshot":
        kwargs: Dict[str, Any] = {"platform": d["platform"]}
        for key, attr in _METRIC_ATTRS.items():
            kwargs[attr] = d[key]
        return cls(**kwargs)


@dataclass
class MetricLimit:
    max: Optional[float] = None
    min: Optional[float] = None
    warn_ratio: Optional[float] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MetricLimit":
        return cls(max=d.get("max"), min=d.get("min"), warn_ratio=d.get("warnRatio"))


@dataclass
class PlatformBudget:
    platform: str
    display_name: str
    limits: Dict[str, MetricLimit] = field(default_factory=dict)


@dataclass
class BudgetFile:
    platforms: List[PlatformBudget] = field(default_factory=list)


@dataclass
class Violation:
    key: str
    platform: str
    metric: str
    actual: float
    budget: float
    unit: str
    severity: str
    message: str
    asset_id: Optional[str] = None


@dataclass
class FixRecommendation:
    id: str
    rule_id: str
    title: str
    detail: str
    effort: str
    priority: int
    platform_targets: List[str] = field(default_factory=list)
    violation_keys: List[str] = field(default_factory=list)
    estimated_savings_mb: Optional[float] = None
    estimated_savings_kbps: Optional[float] = None
    estimated_latency_ms: Optional[float] = None


@dataclass
class PlatformCertification:
    platform: str
    passed: bool
    score: int
    fail_count: int
    warn_count: int
    metrics: MetricsSnapshot
    violations: List[Violation] = field(default_factory=list)


@dataclass
class RunSummary:
    kind: str
    name: str
    duration_ms: int


@dataclass
class ProjectInfo:
    name: str
    engine: str
    input_path: str


@dataclass
class ReportSummary:
    total_fail: int
    total_warn: int
    passed_platforms: int
    total_platforms: int


@dataclass
class CertificationReport:
    id: str
    created_at: str
    project: ProjectInfo
    runner: RunSummary
    platforms: List[PlatformCertification]
    recommendations: List[FixRecommendation]
    overall_pass: bool
    summary: ReportSummary
    tier: str


@dataclass
class Tier:
    id: str
    name: str
    price_monthly_usd: int
    max_platforms: Optional[int]
    max_builds_per_month: Optional[int]
    api_access: bool
    team_seats: Optional[int]
    features: List[str]


@dataclass
class ProjectConfig:
    input: str = "."
    name: Optional[str] = None
    engine: Optional[str] = None


@dataclass
class AuditConfig:
    project: ProjectConfig = field(default_factory=ProjectConfig)
    platforms: List[str] = field(default_factory=lambda: ["pc", "ps5", "mobile"])
    tier: str = "pro"
    budget_overrides_path: Optional[str] = None
    seed: Optional[int] = None
    noise: Optional[bool] = None


def violation_key(platform: str, metric: str, asset_id: Optional[str] = None) -> str:
    return f"{platform}:{metric}:{asset_id or 'global'}"
