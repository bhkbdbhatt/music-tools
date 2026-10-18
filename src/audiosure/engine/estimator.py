from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from audiosure.core.types import AudioAsset, AudioEffect, MetricsSnapshot, ProjectModel, js_round
from audiosure.engine.profiles import get_profile
from audiosure.parsers.util import mulberry32

MB = 1024 * 1024
PCM_BYTES_PER_SAMPLE = 2


@dataclass
class EstimateOptions:
    seed: Optional[int] = None
    noise: Optional[bool] = None


def _decoded_bytes(asset: AudioAsset) -> float:
    rate = asset.sample_rate or 48000
    ch = asset.channels or 2
    dur = asset.duration_sec if asset.duration_sec > 0 else 1
    return dur * rate * ch * PCM_BYTES_PER_SAMPLE


def _asset_memory_bytes(asset: AudioAsset) -> float:
    if asset.load_type == "stream":
        return 0
    if asset.decode_in_memory:
        return _decoded_bytes(asset)
    return asset.size_bytes


def _is_convolution(fx: AudioEffect) -> bool:
    return bool(re.search(r"convol", fx.plugin, re.I)) or bool(re.search(r"convol", fx.name, re.I))


def _ir_seconds(fx: AudioEffect) -> float:
    p = fx.params.get("irDurationSec")
    if isinstance(p, (int, float)) and not isinstance(p, bool) and p > 0:
        return float(p)
    for k, v in fx.params.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and re.search(r"duration|length|sec|ir", k, re.I):
            return float(v)
    return 0.0


def _round(n: float) -> float:
    return js_round(n * 100) / 100


def estimate_metrics(model: ProjectModel, platform: str, opts: Optional[EstimateOptions] = None) -> MetricsSnapshot:
    if opts is None:
        opts = EstimateOptions()
    profile = get_profile(platform)
    assets = model.assets
    streams = [a for a in assets if a.load_type == "stream"]
    memory_assets = [a for a in assets if a.load_type != "stream"]
    conv_effects = [e for e in model.effects if _is_convolution(e)]
    other_effects = [e for e in model.effects if not _is_convolution(e)]

    audio_sources = model.metadata.get("audioSourceCount") or 0
    explicit_voices = sum(e.max_instances if e.max_instances is not None else 1 for e in model.events)
    voices = 6 + explicit_voices * 0.35 + audio_sources * 0.15 + len(streams) * 0.5
    voices = js_round(min(profile.max_voices, max(1, voices)))

    memory_bytes = 0.0
    for a in memory_assets:
        memory_bytes += _asset_memory_bytes(a)
    memory_bytes += len(streams) * profile.stream_buffer_kb * 1024
    memory_bytes += len(model.banks) * profile.bank_overhead_kb * 1024
    memory_bytes += voices * profile.per_voice_mem_kb * 1024
    for fx in conv_effects:
        ir = _ir_seconds(fx) or 0.5
        memory_bytes += ir * 48000 * 2 * 4 * (1 + profile.conv_fft_factor)
    memory_bytes += len(other_effects) * profile.generic_fx_kb * 1024

    streaming_kbps = 0.0
    for a in streams:
        bitrate = (a.size_bytes * 8) / a.duration_sec / 1000 if a.duration_sec > 0 else 128
        weight = 1 if (a.is_music or re.search(r"ambien|bgm|theme", a.name, re.I)) else 0.25
        streaming_kbps += bitrate * weight

    cpu = (
        profile.base_cpu_pct
        + voices * profile.per_voice_cpu_pct
        + len(streams) * profile.per_stream_cpu_pct
        + len(conv_effects) * profile.conv_cpu_pct
        + len(other_effects) * profile.per_fx_cpu_pct
    )
    cpu = min(60, cpu)

    gpu = len(conv_effects) * profile.conv_gpu_pct + len(other_effects) * profile.generic_gpu_pct

    latency = profile.base_latency_ms + len(conv_effects) * profile.conv_latency_ms
    if streams:
        latency += profile.stream_seek_latency_ms
    if voices > 0.85 * profile.max_voices:
        latency += profile.voice_contention_ms

    battery = 0.0
    if profile.has_battery:
        battery = profile.battery_base_mw + cpu * profile.battery_per_cpu_mw + streaming_kbps * profile.battery_per_kbps_mw

    metrics = MetricsSnapshot(
        platform=platform,
        memory_footprint_mb=memory_bytes / MB,
        in_memory_mb=memory_bytes / MB,
        streamed_mb=sum(a.size_bytes for a in streams) / MB,
        audio_thread_latency_ms=latency,
        cpu_audio_pct=cpu,
        gpu_dsp_pct=gpu,
        streaming_bandwidth_kbps=streaming_kbps,
        battery_drain_mw=battery,
        peak_concurrent_voices=voices,
        clip_count=len(assets),
    )

    if opts.noise:
        rnd = mulberry32(opts.seed if opts.seed is not None else 1337)

        def jitter(v: float) -> float:
            return v * (1 + (rnd() - 0.5) * 0.08)

        metrics.memory_footprint_mb = jitter(metrics.memory_footprint_mb)
        metrics.audio_thread_latency_ms = jitter(metrics.audio_thread_latency_ms)
        metrics.cpu_audio_pct = jitter(metrics.cpu_audio_pct)
        metrics.gpu_dsp_pct = jitter(metrics.gpu_dsp_pct)
        metrics.streaming_bandwidth_kbps = jitter(metrics.streaming_bandwidth_kbps)
        metrics.battery_drain_mw = jitter(metrics.battery_drain_mw)
        metrics.in_memory_mb = jitter(metrics.in_memory_mb)
        metrics.streamed_mb = jitter(metrics.streamed_mb)

    metrics.memory_footprint_mb = _round(metrics.memory_footprint_mb)
    metrics.in_memory_mb = _round(metrics.in_memory_mb)
    metrics.streamed_mb = _round(metrics.streamed_mb)
    metrics.audio_thread_latency_ms = _round(metrics.audio_thread_latency_ms)
    metrics.cpu_audio_pct = _round(metrics.cpu_audio_pct)
    metrics.gpu_dsp_pct = _round(metrics.gpu_dsp_pct)
    metrics.streaming_bandwidth_kbps = _round(metrics.streaming_bandwidth_kbps)
    metrics.battery_drain_mw = _round(metrics.battery_drain_mw)
    return metrics
