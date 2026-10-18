from __future__ import annotations

import json
import os
import re
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from audiosure.core.types import AudioAsset, AudioBus, AudioEvent, BankInfo, ProjectModel
from audiosure.parsers.util import guess_duration_sec, walk_files
from audiosure.parsers.xml import attr_str, children_by_tag, find_all, parse_xml

FSB5_CODECS = {
    1: "pcm8",
    2: "pcm16",
    3: "pcm24",
    4: "pcm32",
    5: "float",
    6: "adpcm",
    7: "vorbis",
    8: "xma",
    9: "mp3",
    10: "at9",
    11: "opus",
    12: "fadpcm",
}


@dataclass
class Fsb5Header:
    version: int
    num_samples: int
    sample_headers_size: int
    name_table_size: int
    data_size: int
    mode: int


def read_fsb5_header(buf: bytes) -> Optional[Fsb5Header]:
    if len(buf) < 0x20:
        return None
    if buf[0:4] != b"FSB5":
        return None
    version, num_samples, sample_headers_size, name_table_size, data_size, mode = struct.unpack_from(
        "<IIIIII", buf, 0x04
    )
    return Fsb5Header(
        version=version,
        num_samples=num_samples,
        sample_headers_size=sample_headers_size,
        name_table_size=name_table_size,
        data_size=data_size,
        mode=mode,
    )


def _load_type_from_attr(v: Optional[str]) -> str:
    if not v:
        return "memory"
    s = v.lower()
    if "stream" in s:
        return "stream"
    if "preload" in s:
        return "preload"
    return "memory"


@dataclass
class StudioExportData:
    assets: List[AudioAsset] = field(default_factory=list)
    events: List[AudioEvent] = field(default_factory=list)
    banks_meta: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def _parse_studio_export(text: str) -> StudioExportData:
    root = parse_xml(text)
    assets: List[AudioAsset] = []
    events: List[AudioEvent] = []
    banks_meta: Dict[str, Dict[str, Any]] = {}

    def ensure_bank(name: str) -> Dict[str, Any]:
        b = banks_meta.get(name)
        if b is None:
            b = {"memoryBytes": 0, "streamBytes": 0, "assetIds": [], "streamIds": []}
            banks_meta[name] = b
        return b

    sounds_nodes = [c for s in find_all(root, "Sounds") for c in children_by_tag(s, "Sound")]
    for s in sounds_nodes:
        if s.tag != "Sound":
            continue
        sid = attr_str(s, "id") or attr_str(s, "ref") or attr_str(s, "name") or f"sound-{len(assets)}"
        name = attr_str(s, "name") or sid
        load_type = _load_type_from_attr(attr_str(s, "loadType") or attr_str(s, "mode"))
        try:
            size_bytes = int(float(attr_str(s, "sizeBytes") or attr_str(s, "size") or 0))
        except ValueError:
            size_bytes = 0
        try:
            duration_sec = float(attr_str(s, "duration") or 0)
        except ValueError:
            duration_sec = 0.0
        try:
            channels = int(float(attr_str(s, "channels") or 2)) or 2
        except ValueError:
            channels = 2
        try:
            sample_rate = int(float(attr_str(s, "sampleRate") or 48000)) or 48000
        except ValueError:
            sample_rate = 48000
        codec = attr_str(s, "codec") or "vorbis"
        p = attr_str(s, "path")
        if duration_sec <= 0:
            duration_sec = guess_duration_sec(size_bytes, codec, channels)
        bank = attr_str(s, "bank") or "Master"
        category = attr_str(s, "category")
        asset = AudioAsset(
            id=f"fmod-{sid}",
            name=name,
            path=p,
            duration_sec=duration_sec,
            channels=channels,
            sample_rate=sample_rate,
            codec=codec,
            load_type=load_type,
            size_bytes=size_bytes,
            is_music=bool(re.search(r"music", category, re.I)) if category else bool(re.search(r"music|bgm|theme", name, re.I)),
            is_sfx=not bool(re.search(r"music|bgm|theme|ambience", name, re.I)),
            language=attr_str(s, "language"),
            bank_id=bank,
        )
        assets.append(asset)
        b = ensure_bank(bank)
        if load_type == "stream":
            b["streamIds"].append(asset.id)
        else:
            b["assetIds"].append(asset.id)
            b["memoryBytes"] += size_bytes

    events_nodes = [c for e in find_all(root, "Events") for c in children_by_tag(e, "Event")]
    for e in events_nodes:
        if e.tag != "Event":
            continue
        name = attr_str(e, "name") or attr_str(e, "id") or f"event-{len(events)}"
        bank = attr_str(e, "bank") or "Master"
        asset_refs = [
            f"fmod-{r}" for c in children_by_tag(e, "Sound") if (r := attr_str(c, "ref"))
        ]
        max_inst_raw = attr_str(e, "maxInstances")
        try:
            max_inst = int(float(max_inst_raw)) if max_inst_raw else None
        except ValueError:
            max_inst = None
        events.append(
            AudioEvent(
                id=attr_str(e, "id") or name,
                name=name,
                bank_id=bank,
                asset_ids=asset_refs,
                max_instances=max_inst if max_inst else None,
            )
        )

    return StudioExportData(assets=assets, events=events, banks_meta=banks_meta)


def parse_fmod(root: str) -> ProjectModel:
    bank_files = walk_files(
        root, lambda rel, _: bool(re.search(r"\.bank$", rel, re.I)) and not bool(re.search(r"\.strings\.bank$", rel, re.I))
    )
    banks: List[BankInfo] = []
    metadata: Dict[str, Any] = {"fsb5": {}}

    for bank_path in bank_files:
        with open(bank_path, "rb") as f:
            buf = f.read()
        base = os.path.basename(bank_path)
        short_name = re.sub(r"\.bank$", "", base, flags=re.I)
        hdr = read_fsb5_header(buf)
        is_stream_bank = bool(re.search(r"stream|music|audio", short_name, re.I)) or bool(
            re.search(r"\.streams\.bank$", base, re.I)
        )
        memory_bytes = 0
        stream_ids: List[str] = []
        asset_ids: List[str] = []

        if hdr:
            codec = FSB5_CODECS.get(hdr.mode, f"mode{hdr.mode}")
            if not is_stream_bank:
                memory_bytes = hdr.data_size
            metadata["fsb5"][short_name] = {
                "version": hdr.version,
                "numSamples": hdr.num_samples,
                "dataSize": hdr.data_size,
                "codec": codec,
            }

        banks.append(
            BankInfo(
                id=short_name,
                name=short_name,
                size_bytes=len(buf),
                memory_bytes=memory_bytes,
                stream_ids=stream_ids,
                asset_ids=asset_ids,
            )
        )

    export_xml = next(
        iter(
            walk_files(
                root,
                lambda rel, _: bool(re.search(r"audio-export\.xml$|studio-export\.xml$|fmod-export\.xml$", rel, re.I)),
            )
        ),
        None,
    )
    studio: Optional[StudioExportData] = None
    if export_xml:
        with open(export_xml, "r", encoding="utf-8") as f:
            studio = _parse_studio_export(f.read())
        metadata["studioExport"] = os.path.relpath(export_xml, root)

    assets: List[AudioAsset] = []
    events: List[AudioEvent] = []
    buses: List[AudioBus] = []

    if studio:
        assets = studio.assets
        events = studio.events
        merged: List[BankInfo] = []
        for b in banks:
            meta = studio.banks_meta.get(b.name)
            if not meta:
                merged.append(b)
                continue
            has_streams = len(meta["streamIds"]) > 0
            merged.append(
                BankInfo(
                    id=b.id,
                    name=b.name,
                    size_bytes=b.size_bytes,
                    memory_bytes=b.memory_bytes or meta["memoryBytes"],
                    stream_ids=list(meta["streamIds"]),
                    asset_ids=list(meta["assetIds"]),
                    language=b.language,
                )
            )
            if has_streams and b.memory_bytes == 0:
                merged[-1].memory_bytes = meta["memoryBytes"]
        for name, meta in studio.banks_meta.items():
            if not any(b.name == name for b in merged):
                merged.append(
                    BankInfo(
                        id=name,
                        name=name,
                        size_bytes=meta["memoryBytes"] + meta["streamBytes"],
                        memory_bytes=meta["memoryBytes"],
                        stream_ids=list(meta["streamIds"]),
                        asset_ids=list(meta["assetIds"]),
                    )
                )
        banks = merged
    else:
        for b in banks:
            count = metadata["fsb5"].get(b.name, {}).get("numSamples", 0)
            for i in range(count):
                per_sample = (b.memory_bytes // count) if count > 0 else 0
                sid = f"{b.name}-s{i}"
                assets.append(
                    AudioAsset(
                        id=f"fmod-{sid}",
                        name=sid,
                        duration_sec=guess_duration_sec(per_sample, "vorbis", 2),
                        channels=2,
                        sample_rate=48000,
                        codec="vorbis",
                        load_type="stream" if re.search(r"stream|music", b.name, re.I) else "memory",
                        size_bytes=per_sample,
                        bank_id=b.name,
                    )
                )
                if re.search(r"stream|music", b.name, re.I):
                    b.stream_ids.append(f"fmod-{sid}")
                else:
                    b.asset_ids.append(f"fmod-{sid}")
            if count > 0:
                events.append(
                    AudioEvent(
                        id=f"ev-{b.name}", name=f"{b.name} events", bank_id=b.name, asset_ids=list(b.asset_ids)
                    )
                )

    return ProjectModel(
        engine="fmod",
        name=os.path.basename(os.path.normpath(root)),
        assets=assets,
        effects=[],
        buses=buses,
        events=events,
        banks=banks,
        plugins_used=["FMOD Core", "FMOD Studio"],
        metadata=metadata,
    )
