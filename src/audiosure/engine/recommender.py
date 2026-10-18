from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from audiosure.core.types import (
    AudioAsset,
    AudioEffect,
    FixRecommendation,
    PlatformCertification,
    ProjectModel,
    js_round,
    violation_key,
)
from audiosure.engine.profiles import get_profile

MB = 1024 * 1024
PCM16 = 2
CONV_AVG_FFT_FACTOR = 2.0
IR_TARGET_SEC = 0.5


@dataclass
class RecommendOptions:
    ir_target_sec: Optional[float] = None
    stream_sfx_max_sec: Optional[float] = None
    sample_rate_downgrade_hz: Optional[int] = None


class _ViolationIndex:
    def __init__(self, certs: List[PlatformCertification]) -> None:
        self._certs = certs
        self.by_severity: Dict[str, Dict[str, str]] = {}
        for c in certs:
            m: Dict[str, str] = {}
            for v in c.violations:
                m[v.metric] = v.severity
            self.by_severity[c.platform] = m

    def failing(self, metric: str) -> List[str]:
        return [
            c.platform
            for c in self._certs
            if any(v.metric == metric and v.severity == "fail" for v in c.violations)
        ]

    def warning(self, metric: str) -> List[str]:
        return [
            c.platform
            for c in self._certs
            if any(v.metric == metric and v.severity == "warn" for v in c.violations)
        ]

    def severity_for(self, metric: str) -> Optional[str]:
        best: Optional[str] = None
        for c in self._certs:
            for v in c.violations:
                if v.metric != metric:
                    continue
                if v.severity == "fail":
                    return "fail"
                best = "warn"
        return best


def _targets_for(index: _ViolationIndex, metrics: List[str], fallback_all: List[str]) -> List[str]:
    s: List[str] = []
    for m in metrics:
        for p in index.failing(m) + index.warning(m):
            if p not in s:
                s.append(p)
    return s if s else list(fallback_all)


def _violation_keys_for(index: _ViolationIndex, metrics: List[str], platforms: List[str]) -> List[str]:
    keys: List[str] = []
    for p in platforms:
        for m in metrics:
            if m in index.by_severity.get(p, {}):
                keys.append(violation_key(p, m))
    return keys


def _priority_from(index: _ViolationIndex, metrics: List[str]) -> int:
    p = 4
    for m in metrics:
        sev = index.severity_for(m)
        if sev == "fail":
            return 1
        if sev == "warn":
            p = min(p, 2)
    return p


def _is_convolution(fx: AudioEffect) -> bool:
    return bool(re.search(r"convol", fx.plugin, re.I)) or bool(re.search(r"convol", fx.name, re.I))


def _ir_seconds(fx: AudioEffect) -> float:
    p = fx.params.get("irDurationSec")
    if isinstance(p, (int, float)) and not isinstance(p, bool) and p > 0:
        return float(p)
    for k, v in fx.params.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and re.search(r"duration|length|sec", k, re.I):
            return float(v)
    return 0.0


def _asset_bitrate_kbps(a: AudioAsset) -> float:
    if a.duration_sec > 0:
        return (a.size_bytes * 8) / a.duration_sec / 1000
    return 128


def _asset_memory_bytes(a: AudioAsset) -> float:
    if a.load_type == "stream":
        return 0
    if a.decode_in_memory:
        rate = a.sample_rate or 48000
        ch = a.channels or 2
        dur = a.duration_sec if a.duration_sec > 0 else 1
        return dur * rate * ch * PCM16
    return a.size_bytes


def _r2(n: float) -> float:
    v = js_round(n * 100) / 100
    return int(v) if v == int(v) else v


def recommend_fixes(
    model: ProjectModel,
    certs: List[PlatformCertification],
    all_platforms: List[str],
    opts: Optional[RecommendOptions] = None,
) -> List[FixRecommendation]:
    if opts is None:
        opts = RecommendOptions()
    index = _ViolationIndex(certs)
    ir_target = opts.ir_target_sec if opts.ir_target_sec is not None else IR_TARGET_SEC
    stream_sfx_max = opts.stream_sfx_max_sec if opts.stream_sfx_max_sec is not None else 4
    recs: List[FixRecommendation] = []

    conv_effects = [e for e in model.effects if _is_convolution(e)]
    for i, fx in enumerate(conv_effects):
        ir = _ir_seconds(fx)
        if ir <= ir_target + 0.01:
            continue
        savings_bytes = (ir - ir_target) * 48000 * 2 * 4 * (1 + CONV_AVG_FFT_FACTOR)
        savings_mb = savings_bytes / MB
        platforms = _targets_for(index, ["memoryFootprintMB"], all_platforms)
        recs.append(
            FixRecommendation(
                id=f"rec-ir-{i}",
                rule_id="convolution-ir-too-long",
                title=(
                    f"Reduce convolution reverb impulse from {_r2(ir)}s to {_r2(ir_target)}s "
                    f"to save ~{_r2(savings_mb)}MB"
                ),
                detail=(
                    f'Effect "{fx.name}" ({fx.plugin}) uses a {_r2(ir)}s impulse response. '
                    f"Shortening to {_r2(ir_target)}s cuts IR memory and FFT working buffers by "
                    f"~{_r2(savings_mb)}MB per convolution instance and reduces DSP cost. "
                    f"For a {ir}s IR, consider an offline-baked short IR or a cheaper algorithmic "
                    f"reverb on memory-constrained targets."
                ),
                estimated_savings_mb=_r2(savings_mb),
                effort="low",
                priority=_priority_from(index, ["memoryFootprintMB"]),
                platform_targets=platforms,
                violation_keys=_violation_keys_for(index, ["memoryFootprintMB"], platforms),
            )
        )

    short_stream_sfx = sorted(
        [
            a
            for a in model.assets
            if a.load_type == "stream"
            and a.duration_sec > 0
            and a.duration_sec < stream_sfx_max
            and (a.is_sfx if a.is_sfx is not None else True)
            and not a.is_music
        ],
        key=lambda a: _asset_bitrate_kbps(a),
        reverse=True,
    )
    for i, a in enumerate(short_stream_sfx[:6]):
        kbps = _asset_bitrate_kbps(a)
        platforms = _targets_for(
            index, ["streamingBandwidthKbps", "audioThreadLatencyMs", "memoryFootprintMB"], all_platforms
        )
        recs.append(
            FixRecommendation(
                id=f"rec-stream-{i}",
                rule_id="short-sfx-should-be-in-memory",
                title=f'Switch from streaming to in-memory for "{a.name}" ({_r2(a.duration_sec)}s SFX)',
                detail=(
                    f'"{a.name}" is only {_r2(a.duration_sec)}s but is streamed (~{js_round(kbps)}kbps). '
                    f"Short one-shot SFX gain nothing from streaming and pay stream-seek latency plus I/O jitter. "
                    f"Loading it in memory costs ~{_r2(a.size_bytes / MB)}MB but frees ~{js_round(kbps)}kbps of "
                    f"streaming bandwidth and removes seek latency."
                ),
                estimated_savings_kbps=js_round(kbps),
                effort="trivial",
                priority=_priority_from(index, ["streamingBandwidthKbps"]),
                platform_targets=platforms,
                violation_keys=_violation_keys_for(index, ["streamingBandwidthKbps"], platforms),
            )
        )

    stream_budget: Dict[str, float] = {}
    for c in certs:
        v = next((x for x in c.violations if x.metric == "streamingBandwidthKbps"), None)
        if v:
            stream_budget[c.platform] = v.budget
    if stream_budget:
        heaviest = sorted(
            [a for a in model.assets if a.load_type == "stream"],
            key=lambda a: _asset_bitrate_kbps(a),
            reverse=True,
        )[:3]
        for i, a in enumerate(heaviest):
            kbps = _asset_bitrate_kbps(a)
            strictest = min(stream_budget.values())
            target = max(24, min(64, js_round(strictest * 0.7)))
            if kbps <= target:
                continue
            profit = js_round(kbps - target)
            platforms = list(stream_budget.keys())
            recs.append(
                FixRecommendation(
                    id=f"rec-reencode-{i}",
                    rule_id="reencode-stream-bitrate",
                    title=f'Re-encode stream "{a.name}" to Opus @ {target}kbps to save ~{profit}kbps',
                    detail=(
                        f'"{a.name}" streams at ~{js_round(kbps)}kbps, above the strictest platform budget '
                        f"({strictest}kbps). Re-encoding to Opus at {target}kbps saves ~{profit}kbps of "
                        f"streaming bandwidth on {', '.join(platforms)}. "
                        f"Verify perceived quality on music/ambience before shipping."
                    ),
                    estimated_savings_kbps=profit,
                    effort="medium",
                    priority=_priority_from(index, ["streamingBandwidthKbps"]),
                    platform_targets=platforms,
                    violation_keys=_violation_keys_for(index, ["streamingBandwidthKbps"], platforms),
                )
            )

    short_sfx_48 = [
        a
        for a in model.assets
        if (a.is_sfx if a.is_sfx is not None else True)
        and not a.is_music
        and a.duration_sec > 0
        and a.duration_sec < 2
        and a.sample_rate >= 44100
        and a.load_type != "stream"
    ]
    if short_sfx_48 and index.severity_for("memoryFootprintMB"):
        savings_mb = (
            sum(
                (a.duration_sec * a.sample_rate * a.channels * PCM16) if a.decode_in_memory else a.size_bytes
                for a in short_sfx_48
            )
            * 0.5
        ) / MB
        platforms = _targets_for(index, ["memoryFootprintMB"], all_platforms)
        recs.append(
            FixRecommendation(
                id="rec-downsample",
                rule_id="downsample-short-sfx",
                title=(
                    f"Downsample {len(short_sfx_48)} short SFX from 48kHz to "
                    f"{(opts.sample_rate_downgrade_hz or 22050) / 1000}kHz to save ~{_r2(savings_mb)}MB"
                ),
                detail=(
                    f"{len(short_sfx_48)} SFX clips under 2s play at 48kHz. Halving the rate to 22.05kHz "
                    f"is inaudible for most one-shots (impacts, footsteps, UI) and saves ~{_r2(savings_mb)}MB "
                    f"of memory. Keep 48kHz for pitched/musical content."
                ),
                estimated_savings_mb=_r2(savings_mb),
                effort="low",
                priority=_priority_from(index, ["memoryFootprintMB"]),
                platform_targets=platforms,
                violation_keys=_violation_keys_for(index, ["memoryFootprintMB"], platforms),
            )
        )

    decompressed = [a for a in model.assets if a.decode_in_memory and a.duration_sec >= 0.5]
    if decompressed and index.severity_for("memoryFootprintMB"):
        savings_mb = 0.0
        for a in decompressed:
            decoded = a.duration_sec * a.sample_rate * a.channels * PCM16
            savings_mb += max(0, decoded - a.size_bytes)
        savings_mb /= MB
        platforms = _targets_for(index, ["memoryFootprintMB"], all_platforms)
        recs.append(
            FixRecommendation(
                id="rec-compressed-in-memory",
                rule_id="switch-to-compressed-in-memory",
                title=(
                    f"Switch {len(decompressed)} clips from DecompressOnLoad to CompressedInMemory "
                    f"to save ~{_r2(savings_mb)}MB"
                ),
                detail=(
                    f"{len(decompressed)} clips are fully decompressed into RAM. Switching the long/heavy ones "
                    f"to CompressedInMemory keeps them compressed and decodes on the fly, saving "
                    f"~{_r2(savings_mb)}MB at a small CPU cost. Keep DecompressOnLoad for the hottest one-shots."
                ),
                estimated_savings_mb=_r2(savings_mb),
                effort="low",
                priority=_priority_from(index, ["memoryFootprintMB"]),
                platform_targets=platforms,
                violation_keys=_violation_keys_for(index, ["memoryFootprintMB"], platforms),
            )
        )

    in_memory_assets = [a for a in model.assets if a.load_type != "stream"]
    in_memory_bytes = sum(_asset_memory_bytes(a) for a in in_memory_assets)
    if in_memory_assets and in_memory_bytes > 16 * MB and index.severity_for("memoryFootprintMB"):
        savings_mb = (in_memory_bytes * 0.3) / MB
        platforms = _targets_for(index, ["memoryFootprintMB"], all_platforms)
        biggest_bank = max(model.banks, key=lambda b: b.memory_bytes, default=None)
        recs.append(
            FixRecommendation(
                id="rec-inmemory-bitrate",
                rule_id="reduce-in-memory-media",
                title=(
                    f"Re-encode {len(in_memory_assets)} in-memory clips ({_r2(in_memory_bytes / MB)}MB) "
                    f"at lower bitrate to save ~{_r2(savings_mb)}MB"
                ),
                detail=(
                    f"In-memory media totals ~{_r2(in_memory_bytes / MB)}MB"
                    + (f' (largest bank "{biggest_bank.name}")' if biggest_bank else "")
                    + f", driving the memory overage on {', '.join(platforms)}. "
                    f"Dropping Vorbis/Opus quality by one tier (or moving rarely-heard one-shots to 22.05kHz) "
                    f"typically saves ~30% = ~{_r2(savings_mb)}MB with little perceptual cost. "
                    f"Stream the largest one-shot banks if they exceed their working set."
                ),
                estimated_savings_mb=_r2(savings_mb),
                effort="medium",
                priority=_priority_from(index, ["memoryFootprintMB"]),
                platform_targets=platforms,
                violation_keys=_violation_keys_for(index, ["memoryFootprintMB"], platforms),
            )
        )

    voice_violation = index.failing("peakConcurrentVoices") + index.warning("peakConcurrentVoices")
    cpu_violation = index.failing("cpuAudioPct") + index.warning("cpuAudioPct")
    voice_targets: List[str] = []
    for p in voice_violation + cpu_violation:
        if p not in voice_targets:
            voice_targets.append(p)
    if voice_targets:
        peak = max((c.metrics.peak_concurrent_voices for c in certs), default=1) or 1
        cap = js_round(peak * 0.7)
        strictest = min(get_profile(p).per_voice_cpu_pct for p in voice_targets)
        cpu_save = _r2(peak * 0.3 * strictest)
        recs.append(
            FixRecommendation(
                id="rec-voice-virtualization",
                rule_id="voice-virtualization",
                title=f"Cap concurrent voices to {cap} via virtualization to cut audio CPU ~{cpu_save}%",
                detail=(
                    f"Peak reach is ~{peak} concurrent voices. Virtualizing distant/quiet voices above {cap} "
                    f"(Wwise voice limiting / FMOD virtual voices) keeps CPU within budget with minimal "
                    f"audible impact. Prioritize music/player-critical sounds and cull ambience tails first."
                ),
                effort="low",
                priority=_priority_from(index, ["peakConcurrentVoices", "cpuAudioPct"]),
                platform_targets=voice_targets,
                violation_keys=_violation_keys_for(index, ["peakConcurrentVoices", "cpuAudioPct"], voice_targets),
            )
        )

    latency_violation: List[str] = []
    for p in index.failing("audioThreadLatencyMs") + index.warning("audioThreadLatencyMs"):
        if p not in latency_violation:
            latency_violation.append(p)
    if latency_violation and conv_effects:
        save = _r2(len(conv_effects) * 0.6)
        recs.append(
            FixRecommendation(
                id="rec-latency-dsp",
                rule_id="latency-dsp-chain",
                title=f"Shorten convolution on the master path to cut ~{save}ms of audio latency",
                detail=(
                    f"Platforms {', '.join(latency_violation)} are near/over their audio-latency budget. "
                    f"Long convolution reverbs and deep DSP chains on the master bus add latency. "
                    f"Move convolution to sends, shorten IRs, and keep the master insert chain shallow."
                ),
                estimated_latency_ms=save,
                effort="medium",
                priority=1,
                platform_targets=latency_violation,
                violation_keys=_violation_keys_for(index, ["audioThreadLatencyMs"], latency_violation),
            )
        )

    battery_violation = index.failing("batteryDrainMw") + index.warning("batteryDrainMw")
    battery_targets: List[str] = []
    for p in battery_violation:
        if p not in battery_targets:
            battery_targets.append(p)
    if battery_targets:
        recs.append(
            FixRecommendation(
                id="rec-battery",
                rule_id="reduce-battery-drain",
                title="Cut voice count, streaming bitrate, and convolution cost to reduce battery drain",
                detail=(
                    f"Battery budget is exceeded on {', '.join(battery_targets)}. "
                    f"Audio decode and DSP run continuously; the fastest milliwatt wins are fewer "
                    f"concurrent voices, lower streaming bitrate, and cheaper reverb DSP. "
                    f"Consider suspending audio work when the app is backgrounded."
                ),
                effort="medium",
                priority=1,
                platform_targets=battery_targets,
                violation_keys=_violation_keys_for(index, ["batteryDrainMw"], battery_targets),
            )
        )

    return recs
