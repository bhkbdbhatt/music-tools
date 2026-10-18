from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from audiosure.core.types import AudioAsset, AudioBus, AudioEvent, BankInfo, ProjectModel
from audiosure.parsers.util import file_size, guess_duration_sec, read_wav_info, walk_files

AUDIO_EXT_RE = re.compile(r"\.(wav|ogg|mp3|aiff|aif|flac)$", re.I)

UNITY_LOAD_TYPE = {"0": "memory", "1": "memory", "2": "stream"}
UNITY_COMPRESSION = {"0": "pcm", "1": "vorbis", "2": "adpcm", "3": "mp3", "4": "pcm"}


@dataclass
class MetaInfo:
    guid: Optional[str] = None
    load_type: Optional[str] = None
    decode_in_memory: Optional[bool] = None
    compression_format: Optional[str] = None
    sample_rate_override: Optional[int] = None
    quality: Optional[float] = None
    preload_audio_data: Optional[bool] = None


def _get_yaml_scalar(text: str, key: str) -> Optional[str]:
    m = re.search(rf"^\s*{re.escape(key)}:\s*(-?[0-9]+|true|false|\"[^\"]*\"|'[^']*'|[^\s].*)$", text, re.M)
    if not m:
        return None
    v = m.group(1).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def _parse_audio_importer_meta(text: str) -> MetaInfo:
    gm = re.search(r"^guid:\s*([0-9a-f]+)$", text, re.M)
    guid = gm.group(1) if gm else None
    bm = re.search(r"AudioImporter:[\s\S]*?(?=\n[A-Za-z]+:|$)", text)
    block = bm.group(0) if bm else text
    load_type_raw = _get_yaml_scalar(block, "loadType")
    compression_raw = _get_yaml_scalar(block, "compressionFormat")
    sample_rate_raw = _get_yaml_scalar(block, "sampleRateOverride")
    quality_raw = _get_yaml_scalar(block, "quality")
    preload_raw = _get_yaml_scalar(block, "preloadAudioData")
    try:
        sample_rate_override = int(sample_rate_raw) if sample_rate_raw is not None else None
    except ValueError:
        sample_rate_override = None
    try:
        quality = float(quality_raw) if quality_raw is not None else None
    except ValueError:
        quality = None
    return MetaInfo(
        guid=guid,
        load_type=UNITY_LOAD_TYPE.get(load_type_raw, "memory") if load_type_raw else None,
        decode_in_memory=load_type_raw == "0",
        compression_format=(
            UNITY_COMPRESSION.get(compression_raw, f"fmt{compression_raw}") if compression_raw else None
        ),
        sample_rate_override=sample_rate_override,
        quality=quality,
        preload_audio_data=preload_raw == "true",
    )


def parse_unity(root: str) -> ProjectModel:
    audio_files = walk_files(
        root, lambda rel, _: bool(AUDIO_EXT_RE.search(rel)) and not bool(re.search(r"\.meta$", rel, re.I))
    )
    meta_files = walk_files(root, lambda rel, _: bool(re.search(r"\.meta$", rel, re.I)))

    meta_by_source: Dict[str, MetaInfo] = {}
    for meta_path in meta_files:
        if not AUDIO_EXT_RE.search(meta_path[: -len(".meta")]):
            continue
        with open(meta_path, "r", encoding="utf-8") as f:
            text = f.read()
        if "AudioImporter:" not in text:
            continue
        source = meta_path[: -len(".meta")]
        meta_by_source[os.path.normpath(source)] = _parse_audio_importer_meta(text)

    assets: List[AudioAsset] = []
    for file_path in audio_files:
        abs_path = os.path.normpath(file_path)
        info = meta_by_source.get(abs_path) or MetaInfo()
        size = file_size(abs_path)
        duration = 0.0
        channels = 2
        sample_rate = info.sample_rate_override or 48000
        if re.search(r"\.wav$", abs_path, re.I):
            wav = read_wav_info(abs_path)
            if wav:
                duration = wav.duration_sec
                channels = wav.channels
                if not info.sample_rate_override:
                    sample_rate = wav.sample_rate
        if duration <= 0:
            duration = guess_duration_sec(size, info.compression_format or "vorbis", channels)
        name = AUDIO_EXT_RE.sub("", os.path.basename(abs_path))
        assets.append(
            AudioAsset(
                id=f"unity-{info.guid or name}",
                name=name,
                path=os.path.relpath(abs_path, root),
                duration_sec=duration,
                channels=channels,
                sample_rate=sample_rate,
                codec=info.compression_format or "vorbis",
                load_type=info.load_type or "memory",
                size_bytes=size,
                decode_in_memory=info.decode_in_memory or False,
                is_music=bool(re.search(r"music|bgm|theme|ambient", name, re.I)),
                is_sfx=True,
                bank_id="Assets",
            )
        )

    mixer_files = walk_files(root, lambda rel, _: bool(re.search(r"\.mixer$", rel, re.I)))
    buses: List[AudioBus] = []
    for m in mixer_files:
        with open(m, "r", encoding="utf-8") as f:
            text = f.read()
        group_count = len(re.findall(r"AudioMixerGroupController:", text))
        buses.append(
            AudioBus(
                id=f"mixer-{os.path.splitext(os.path.basename(m))[0]}",
                name=os.path.splitext(os.path.basename(m))[0],
                effect_ids=[f"mixer-group-{i}" for i in range(group_count)],
            )
        )

    scene_files = walk_files(root, lambda rel, _: bool(re.search(r"\.(unity|prefab)$", rel, re.I)))
    audio_source_count = 0
    for s in scene_files:
        with open(s, "r", encoding="utf-8") as f:
            text = f.read()
        audio_source_count += len(re.findall(r"^AudioSource:", text, re.M))

    banks: List[BankInfo] = [
        BankInfo(
            id="Assets",
            name="Assets",
            size_bytes=sum(a.size_bytes for a in assets),
            memory_bytes=sum(a.size_bytes for a in assets if a.load_type != "stream"),
            stream_ids=[a.id for a in assets if a.load_type == "stream"],
            asset_ids=[a.id for a in assets if a.load_type != "stream"],
        )
    ]

    return ProjectModel(
        engine="unity",
        name=os.path.basename(os.path.normpath(root)),
        assets=assets,
        effects=[],
        buses=buses,
        events=[],
        banks=banks,
        plugins_used=["Unity Audio"],
        metadata={
            "audioSourceCount": audio_source_count,
            "mixerCount": len(mixer_files),
        },
    )
