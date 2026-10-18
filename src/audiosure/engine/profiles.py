from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlatformProfile:
    platform: str
    display_name: str
    base_latency_ms: float
    base_cpu_pct: float
    per_voice_cpu_pct: float
    per_stream_cpu_pct: float
    per_fx_cpu_pct: float
    conv_cpu_pct: float
    conv_latency_ms: float
    conv_gpu_pct: float
    generic_gpu_pct: float
    per_voice_mem_kb: float
    bank_overhead_kb: float
    stream_buffer_kb: float
    conv_fft_factor: float
    generic_fx_kb: float
    stream_seek_latency_ms: float
    voice_contention_ms: float
    max_voices: int
    battery_base_mw: float
    battery_per_cpu_mw: float
    battery_per_kbps_mw: float
    has_battery: bool


PLATFORM_PROFILES = {
    "pc": PlatformProfile(
        platform="pc",
        display_name="PC",
        base_latency_ms=12,
        base_cpu_pct=1.0,
        per_voice_cpu_pct=0.03,
        per_stream_cpu_pct=0.1,
        per_fx_cpu_pct=0.12,
        conv_cpu_pct=1.2,
        conv_latency_ms=0.5,
        conv_gpu_pct=1.0,
        generic_gpu_pct=0.2,
        per_voice_mem_kb=8,
        bank_overhead_kb=64,
        stream_buffer_kb=256,
        conv_fft_factor=2.0,
        generic_fx_kb=48,
        stream_seek_latency_ms=0.4,
        voice_contention_ms=2.0,
        max_voices=128,
        battery_base_mw=0,
        battery_per_cpu_mw=0,
        battery_per_kbps_mw=0,
        has_battery=False,
    ),
    "ps5": PlatformProfile(
        platform="ps5",
        display_name="PlayStation 5",
        base_latency_ms=8,
        base_cpu_pct=0.6,
        per_voice_cpu_pct=0.02,
        per_stream_cpu_pct=0.05,
        per_fx_cpu_pct=0.1,
        conv_cpu_pct=0.8,
        conv_latency_ms=0.3,
        conv_gpu_pct=0.5,
        generic_gpu_pct=0.15,
        per_voice_mem_kb=8,
        bank_overhead_kb=48,
        stream_buffer_kb=256,
        conv_fft_factor=1.8,
        generic_fx_kb=40,
        stream_seek_latency_ms=0.3,
        voice_contention_ms=1.5,
        max_voices=96,
        battery_base_mw=0,
        battery_per_cpu_mw=0,
        battery_per_kbps_mw=0,
        has_battery=False,
    ),
    "xbox": PlatformProfile(
        platform="xbox",
        display_name="Xbox Series X|S",
        base_latency_ms=9,
        base_cpu_pct=0.7,
        per_voice_cpu_pct=0.022,
        per_stream_cpu_pct=0.06,
        per_fx_cpu_pct=0.1,
        conv_cpu_pct=0.9,
        conv_latency_ms=0.35,
        conv_gpu_pct=0.6,
        generic_gpu_pct=0.15,
        per_voice_mem_kb=8,
        bank_overhead_kb=48,
        stream_buffer_kb=256,
        conv_fft_factor=1.8,
        generic_fx_kb=40,
        stream_seek_latency_ms=0.35,
        voice_contention_ms=1.6,
        max_voices=96,
        battery_base_mw=0,
        battery_per_cpu_mw=0,
        battery_per_kbps_mw=0,
        has_battery=False,
    ),
    "switch2": PlatformProfile(
        platform="switch2",
        display_name="Nintendo Switch 2",
        base_latency_ms=14,
        base_cpu_pct=1.2,
        per_voice_cpu_pct=0.05,
        per_stream_cpu_pct=0.2,
        per_fx_cpu_pct=0.2,
        conv_cpu_pct=2.5,
        conv_latency_ms=1.0,
        conv_gpu_pct=1.5,
        generic_gpu_pct=0.35,
        per_voice_mem_kb=6,
        bank_overhead_kb=40,
        stream_buffer_kb=128,
        conv_fft_factor=2.2,
        generic_fx_kb=32,
        stream_seek_latency_ms=0.8,
        voice_contention_ms=3.0,
        max_voices=64,
        battery_base_mw=0,
        battery_per_cpu_mw=0,
        battery_per_kbps_mw=0,
        has_battery=False,
    ),
    "mobile": PlatformProfile(
        platform="mobile",
        display_name="Mobile",
        base_latency_ms=11,
        base_cpu_pct=1.5,
        per_voice_cpu_pct=0.08,
        per_stream_cpu_pct=0.25,
        per_fx_cpu_pct=0.3,
        conv_cpu_pct=3.5,
        conv_latency_ms=1.2,
        conv_gpu_pct=0.5,
        generic_gpu_pct=0.3,
        per_voice_mem_kb=4,
        bank_overhead_kb=32,
        stream_buffer_kb=96,
        conv_fft_factor=2.5,
        generic_fx_kb=24,
        stream_seek_latency_ms=1.0,
        voice_contention_ms=3.5,
        max_voices=48,
        battery_base_mw=60,
        battery_per_cpu_mw=6,
        battery_per_kbps_mw=0.03,
        has_battery=True,
    ),
    "vr": PlatformProfile(
        platform="vr",
        display_name="VR Headset",
        base_latency_ms=6,
        base_cpu_pct=1.0,
        per_voice_cpu_pct=0.05,
        per_stream_cpu_pct=0.15,
        per_fx_cpu_pct=0.25,
        conv_cpu_pct=2.0,
        conv_latency_ms=0.4,
        conv_gpu_pct=1.0,
        generic_gpu_pct=0.4,
        per_voice_mem_kb=6,
        bank_overhead_kb=48,
        stream_buffer_kb=128,
        conv_fft_factor=2.0,
        generic_fx_kb=32,
        stream_seek_latency_ms=0.5,
        voice_contention_ms=2.0,
        max_voices=64,
        battery_base_mw=250,
        battery_per_cpu_mw=8,
        battery_per_kbps_mw=0.05,
        has_battery=True,
    ),
}


def get_profile(platform: str) -> PlatformProfile:
    return PLATFORM_PROFILES[platform]
