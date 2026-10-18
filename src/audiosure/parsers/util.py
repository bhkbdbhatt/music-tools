from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import Callable, List, Optional


def path_exists(p: str) -> bool:
    return os.path.exists(p)


def walk_files(root: str, match: Callable[[str, str], bool]) -> List[str]:
    out: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git")]
        for name in filenames:
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, root)
            if match(rel, abs_path):
                out.append(abs_path)
    return out


def file_size(p: str) -> int:
    return os.stat(p).st_size


def guess_duration_sec(size_bytes: int, codec: str, channels: int) -> float:
    bitrates = {
        "vorbis": 96_000,
        "opus": 64_000,
        "mp3": 192_000,
        "xma": 128_000,
        "at9": 60_000,
        "adpcm": 352_800,
        "pcm": 48_000 * 16 * max(1, channels),
        "wem": 96_000,
        "wav": 48_000 * 16 * max(1, channels),
    }
    bps = bitrates.get(codec.lower(), 96_000)
    return max(0.01, (size_bytes * 8) / bps)


def parse_wav_duration(pcm_bytes: int, sample_rate: int, channels: int, bits_per_sample: int) -> float:
    bytes_per_sec = sample_rate * channels * (bits_per_sample / 8)
    return pcm_bytes / bytes_per_sec if bytes_per_sec > 0 else 0.0


@dataclass
class WavInfo:
    sample_rate: int
    channels: int
    bits_per_sample: int
    data_bytes: int
    duration_sec: float


def read_wav_info(p: str) -> Optional[WavInfo]:
    try:
        with open(p, "rb") as f:
            buf = f.read()
        if len(buf) < 44 or buf[0:4] != b"RIFF":
            return None
        if buf[8:12] != b"WAVE":
            return None
        offset = 12
        sample_rate = 48000
        channels = 2
        bits_per_sample = 16
        data_bytes = 0
        while offset + 8 <= len(buf):
            chunk_id = buf[offset : offset + 4].decode("ascii", errors="replace")
            (chunk_size,) = struct.unpack_from("<I", buf, offset + 4)
            body = offset + 8
            if chunk_id == "fmt ":
                (channels,) = struct.unpack_from("<H", buf, body + 2)
                (sample_rate,) = struct.unpack_from("<I", buf, body + 4)
                (bits_per_sample,) = struct.unpack_from("<H", buf, body + 14)
            elif chunk_id == "data":
                data_bytes = chunk_size
                break
            offset = body + chunk_size + (chunk_size % 2)
        return WavInfo(
            sample_rate=sample_rate,
            channels=channels,
            bits_per_sample=bits_per_sample,
            data_bytes=data_bytes,
            duration_sec=parse_wav_duration(data_bytes, sample_rate, channels, bits_per_sample),
        )
    except OSError:
        return None


def mulberry32(seed: int) -> Callable[[], float]:
    a = seed & 0xFFFFFFFF

    def rng() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (a | 1)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return rng
