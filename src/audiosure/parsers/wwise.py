from __future__ import annotations

import json
import os
import re
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from audiosure.core.types import AudioAsset, AudioBus, AudioEffect, AudioEvent, BankInfo, ProjectModel
from audiosure.parsers.util import file_size, guess_duration_sec, path_exists, read_wav_info, walk_files
from audiosure.parsers.xml import XmlNode, attr_num, attr_str, find_all, find_all_where, parse_xml


@dataclass
class StreamedFileInfo:
    id: str
    name: str
    path: Optional[str] = None
    language: Optional[str] = None
    bank_short_name: Optional[str] = None


@dataclass
class BankXmlInfo:
    id: str
    short_name: str
    name: Optional[str] = None
    path: Optional[str] = None
    language: Optional[str] = None
    memory_bytes: Optional[int] = None
    size_bytes: Optional[int] = None
    stream_ids: List[str] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)


@dataclass
class BnkSection:
    id: str
    size: int
    payload_offset: int


@dataclass
class DidxEntry:
    source_id: int
    file_offset: int
    file_length: int


def _read_sections(buf: bytes) -> List[BnkSection]:
    sections: List[BnkSection] = []
    off = 0
    n = len(buf)
    while off + 8 <= n:
        section_id = buf[off : off + 4].decode("ascii", errors="replace")
        if not re.fullmatch(r"[A-Z0-9]{4}", section_id):
            break
        (size,) = struct.unpack_from("<I", buf, off + 4)
        sections.append(BnkSection(id=section_id, size=size, payload_offset=off + 8))
        off += 8 + size
        if size == 0 and section_id == "DATA":
            break
    return sections


def _read_didx(buf: bytes, section: BnkSection) -> List[DidxEntry]:
    entries: List[DidxEntry] = []
    count = section.size // 12
    for i in range(count):
        o = section.payload_offset + i * 12
        if o + 12 > len(buf):
            break
        source_id, file_offset, file_length = struct.unpack_from("<III", buf, o)
        entries.append(DidxEntry(source_id=source_id, file_offset=file_offset, file_length=file_length))
    return entries


def _read_hirc_count(buf: bytes, section: BnkSection) -> int:
    if section.payload_offset + 4 > len(buf):
        return 0
    return struct.unpack_from("<I", buf, section.payload_offset)[0]


def _first_num_attr(n: XmlNode, names: List[str]) -> Optional[int]:
    for name in names:
        v = attr_num(n, name)
        if v is not None:
            return int(v)
    return None


def _parse_soundbanks_info_xml(text: str) -> Tuple[List[BankXmlInfo], List[StreamedFileInfo]]:
    root = parse_xml(text)
    banks: List[BankXmlInfo] = []
    streams: List[StreamedFileInfo] = []

    for sf in find_all_where(
        root,
        lambda n: n.tag == "StreamedFile"
        and (attr_str(n, "Path") is not None or attr_str(n, "Name") is not None),
    ):
        sid = attr_str(sf, "Id") or attr_str(sf, "ID")
        if not sid:
            continue
        streams.append(
            StreamedFileInfo(
                id=sid,
                name=attr_str(sf, "Name") or attr_str(sf, "ShortName") or sid,
                path=attr_str(sf, "Path"),
                language=attr_str(sf, "Language"),
                bank_short_name=attr_str(sf, "SoundBankShortName") or attr_str(sf, "BankShortName"),
            )
        )

    for sb in find_all(root, "SoundBank"):
        short_name = attr_str(sb, "ShortName") or attr_str(sb, "Name") or "Unknown"
        bank_id = attr_str(sb, "Id") or attr_str(sb, "ID") or short_name
        stream_ids: List[str] = []
        event_ids: List[str] = []
        for sfl in find_all(sb, "StreamedFile"):
            sid = attr_str(sfl, "Id") or attr_str(sfl, "ID")
            if sid:
                stream_ids.append(sid)
        for ev in find_all(sb, "Event"):
            eid = attr_str(ev, "Id") or attr_str(ev, "ID") or attr_str(ev, "Name")
            if eid:
                event_ids.append(eid)
        banks.append(
            BankXmlInfo(
                id=bank_id,
                short_name=short_name,
                name=attr_str(sb, "Name") or attr_str(sb, "FileName"),
                path=attr_str(sb, "Path"),
                language=attr_str(sb, "Language"),
                memory_bytes=_first_num_attr(sb, ["MemoryBytes", "Memory", "BankMemory"]),
                size_bytes=_first_num_attr(sb, ["SizeBytes", "Size", "BankSize"]),
                stream_ids=stream_ids,
                event_ids=event_ids,
            )
        )
    return banks, streams


def _as_int(v: Any) -> Optional[int]:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _parse_soundbanks_info_json(raw: str) -> Tuple[List[BankXmlInfo], List[StreamedFileInfo]]:
    data = json.loads(raw)
    info = data.get("SoundbanksInfo") or data.get("SoundBanksInfo") or data
    banks_raw = info.get("SoundBanks") or info.get("soundBanks") or []
    streams_raw = info.get("StreamedFiles") or info.get("streamedFiles") or []

    streams: List[StreamedFileInfo] = []
    for s in streams_raw:
        streams.append(
            StreamedFileInfo(
                id=str(s.get("Id") or s.get("ID") or s.get("id") or ""),
                name=str(s.get("Name") or s.get("name") or s.get("ShortName") or ""),
                path=str(s["Path"]) if s.get("Path") else (str(s["path"]) if s.get("path") else None),
                language=str(s["Language"]) if s.get("Language") else None,
                bank_short_name=str(s["SoundBankShortName"]) if s.get("SoundBankShortName") else None,
            )
        )

    banks: List[BankXmlInfo] = []
    for b in banks_raw:
        memory_bytes = _as_int(b.get("MemoryBytes"))
        if memory_bytes is None and _as_int(b.get("MemoryBits")) is not None:
            memory_bytes = -(-_as_int(b["MemoryBits"]) // 8)  # ceil div
        banks.append(
            BankXmlInfo(
                id=str(b.get("Id") or b.get("ID") or b.get("ShortName") or ""),
                short_name=str(b.get("ShortName") or b.get("shortName") or b.get("Name") or "Unknown"),
                name=str(b["Name"]) if b.get("Name") else None,
                path=str(b["Path"]) if b.get("Path") else None,
                language=str(b["Language"]) if b.get("Language") else None,
                memory_bytes=memory_bytes,
                size_bytes=_as_int(b.get("SizeBytes")),
                stream_ids=[
                    str(s.get("Id") or s.get("ID") or "") for s in (b.get("StreamedFiles") or [])
                ],
                event_ids=[str(e.get("Id") or e.get("Name") or "") for e in (b.get("Events") or [])],
            )
        )
    return banks, streams


def _extract_fx_params(fx_node: XmlNode) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for p in find_all_where(
        fx_node, lambda n: n.tag in ("Property", "Param", "FXProperty")
    ):
        name = attr_str(p, "Name") or attr_str(p, "key")
        if not name:
            for c in p.children:
                if c.tag == "Name":
                    name = c.text.strip()
                    break
        if not name:
            continue
        raw = attr_str(p, "Value") or attr_str(p, "value")
        if raw is None:
            for c in p.children:
                if c.tag == "Value":
                    raw = c.text.strip()
                    break
        if raw is None:
            raw = p.text.strip()
        if not raw:
            continue
        try:
            num = float(raw)
            params[name] = int(num) if num.is_integer() else num
        except ValueError:
            params[name] = raw
    return params


def _parse_wwu_effects(text: str) -> Tuple[List[AudioEffect], List[AudioBus], List[AudioEvent]]:
    root = parse_xml(text)
    effects: List[AudioEffect] = []
    buses: List[AudioBus] = []
    events: List[AudioEvent] = []

    fx_nodes = find_all_where(
        root,
        lambda n: n.tag in ("Fx", "Effect", "FxRef", "EffectBase")
        and (
            attr_str(n, "Plugin") is not None
            or any(c.tag in ("PluginName", "Plugin") for c in n.children)
        ),
    )
    for i, fx in enumerate(fx_nodes):
        plugin = attr_str(fx, "Plugin")
        if plugin is None:
            plugin = next((c.text.strip() for c in fx.children if c.tag in ("PluginName", "Plugin")), None)
        plugin = plugin or "Unknown"
        name = attr_str(fx, "Name")
        if name is None:
            name = next((c.text.strip() for c in fx.children if c.tag == "Name"), None)
        name = name or plugin
        params = _extract_fx_params(fx)
        normalized: Dict[str, Any] = dict(params)
        for k, v in params.items():
            if re.search(r"ir.*duration|impulse.*len|convolution.*sec", k, re.I) and isinstance(v, (int, float)):
                normalized["irDurationSec"] = v
        if re.search(r"convol", plugin, re.I) and normalized.get("irDurationSec") is None:
            guess_key = next((k for k in params if re.search(r"duration|length|sec", k, re.I)), None)
            if guess_key and isinstance(params[guess_key], (int, float)):
                normalized["irDurationSec"] = params[guess_key]
        effects.append(AudioEffect(id=f"fx-wwu-{i}", name=name, plugin=plugin, params=normalized))

    bus_nodes = find_all_where(root, lambda n: n.tag in ("Bus", "AuxBus"))
    for i, b in enumerate(bus_nodes):
        name = attr_str(b, "Name")
        if name is None:
            name = next((c.text.strip() for c in b.children if c.tag == "Name"), None)
        name = name or f"Bus{i}"
        effect_ids: List[str] = []
        for fx in find_all(b, "Fx"):
            plugin = attr_str(fx, "Plugin")
            if plugin is None:
                plugin = next((c.text.strip() for c in fx.children if c.tag == "PluginName"), None)
            if plugin:
                match = next((e for e in effects if e.plugin == plugin), None)
                if match:
                    effect_ids.append(match.id)
        buses.append(AudioBus(id=f"bus-wwu-{i}", name=name, effect_ids=effect_ids))

    event_nodes = find_all_where(
        root,
        lambda n: n.tag == "Event"
        and (attr_str(n, "Name") is not None or any(c.tag == "Name" for c in n.children)),
    )
    for i, e in enumerate(event_nodes):
        name = attr_str(e, "Name")
        if name is None:
            name = next((c.text.strip() for c in e.children if c.tag == "Name"), None)
        name = name or f"Event{i}"
        events.append(AudioEvent(id=attr_str(e, "Id") or f"evt-wwu-{i}", name=name, asset_ids=[]))

    return effects, buses, events


def parse_wwise(root: str) -> ProjectModel:
    banks: List[BankInfo] = []
    assets: List[AudioAsset] = []
    effects: List[AudioEffect] = []
    buses: List[AudioBus] = []
    events: List[AudioEvent] = []
    plugins: Dict[str, None] = {}  # ordered set
    metadata: Dict[str, Any] = {"missingStreamedFiles": []}

    bank_info_list: List[BankXmlInfo] = []
    stream_list: List[StreamedFileInfo] = []
    json_info = next(iter(walk_files(root, lambda rel, _: bool(re.search(r"SoundBanksInfo\.json$", rel, re.I)))), None)
    xml_info = next(iter(walk_files(root, lambda rel, _: bool(re.search(r"SoundBanksInfo\.xml$", rel, re.I)))), None)
    if json_info:
        with open(json_info, "r", encoding="utf-8") as f:
            bank_info_list, stream_list = _parse_soundbanks_info_json(f.read())
        metadata["soundbanksInfoSource"] = os.path.relpath(json_info, root)
    elif xml_info:
        with open(xml_info, "r", encoding="utf-8") as f:
            bank_info_list, stream_list = _parse_soundbanks_info_xml(f.read())
        metadata["soundbanksInfoSource"] = os.path.relpath(xml_info, root)

    bnk_files = walk_files(root, lambda rel, _: bool(re.search(r"\.bnk$", rel, re.I)))
    bnk_by_short: Dict[str, Dict[str, int]] = {}

    for bnk in bnk_files:
        with open(bnk, "rb") as f:
            buf = f.read()
        sections = _read_sections(buf)
        didx_bytes = 0
        didx_count = 0
        hirc_count = 0
        didx_section = next((s for s in sections if s.id == "DIDX"), None)
        hirc_section = next((s for s in sections if s.id == "HIRC"), None)
        stem = os.path.splitext(os.path.basename(bnk))[0]
        if didx_section:
            entries = _read_didx(buf, didx_section)
            didx_count = len(entries)
            didx_bytes = sum(e.file_length for e in entries)
            for idx, entry in enumerate(entries):
                assets.append(
                    AudioAsset(
                        id=f"wem-{entry.source_id}",
                        name=f"{stem}-media-{idx}",
                        duration_sec=0,
                        channels=2,
                        sample_rate=48000,
                        codec="wem",
                        load_type="memory",
                        size_bytes=entry.file_length,
                        is_sfx=True,
                        bank_id=stem,
                    )
                )
        if hirc_section:
            hirc_count = _read_hirc_count(buf, hirc_section)
        bnk_by_short[stem] = {
            "memoryBytes": didx_bytes,
            "sizeBytes": len(buf),
            "didxCount": didx_count,
            "hircCount": hirc_count,
            "didxBytes": didx_bytes,
        }

    missing: List[str] = metadata["missingStreamedFiles"]

    for s in stream_list:
        size = 0
        duration = 0.0
        channels = 2
        sample_rate = 48000
        candidates = (
            [
                os.path.join(root, s.path),
                os.path.join(root, "audio", os.path.basename(s.path)),
                os.path.join(os.path.dirname(root), s.path),
            ]
            if s.path
            else []
        )
        # Normalize paths (os.path.join with absolute-ish segments)
        candidates = [os.path.normpath(c) for c in candidates]
        found: Optional[str] = None
        for c in candidates:
            if path_exists(c):
                found = c
                break
        if found:
            size = file_size(found)
            if re.search(r"\.wav$", found, re.I):
                wav = read_wav_info(found)
                if wav:
                    duration = wav.duration_sec
                    channels = wav.channels
                    sample_rate = wav.sample_rate
            else:
                duration = guess_duration_sec(size, "wem", channels)
        else:
            missing.append(s.name)
        is_music = bool(re.search(r"music|bgm|theme", s.name, re.I))
        assets.append(
            AudioAsset(
                id=f"stream-{s.id}",
                name=s.name,
                path=s.path,
                duration_sec=duration,
                channels=channels,
                sample_rate=sample_rate,
                codec="wem",
                load_type="stream",
                size_bytes=size,
                is_music=is_music,
                is_sfx=not is_music,
                language=s.language,
                bank_id=s.bank_short_name,
            )
        )

    for b in bank_info_list:
        bnk_data = bnk_by_short.get(b.short_name)
        stream_ids = [f"stream-{sid}" for sid in b.stream_ids]
        asset_ids = [a.id for a in assets if a.bank_id == b.short_name]
        banks.append(
            BankInfo(
                id=b.id,
                name=b.short_name,
                size_bytes=b.size_bytes if b.size_bytes is not None else (bnk_data["sizeBytes"] if bnk_data else 0),
                memory_bytes=(
                    b.memory_bytes if b.memory_bytes is not None else (bnk_data["memoryBytes"] if bnk_data else 0)
                ),
                stream_ids=stream_ids,
                asset_ids=asset_ids,
                language=b.language,
            )
        )

    for name, data in bnk_by_short.items():
        if not any(b.name == name for b in banks):
            banks.append(
                BankInfo(
                    id=name,
                    name=name,
                    size_bytes=data["sizeBytes"],
                    memory_bytes=data["didxBytes"],
                    stream_ids=[],
                    asset_ids=[a.id for a in assets if a.bank_id == name],
                )
            )

    wwu_files = walk_files(root, lambda rel, _: bool(re.search(r"\.wwu$", rel, re.I)))
    for wwu in wwu_files:
        with open(wwu, "r", encoding="utf-8") as f:
            text = f.read()
        parsed_effects, parsed_buses, parsed_events = _parse_wwu_effects(text)
        effects.extend(parsed_effects)
        buses.extend(parsed_buses)
        events.extend(parsed_events)
        for fx in parsed_effects:
            plugins[fx.plugin] = None

    for bank in bank_info_list:
        for eid in bank.event_ids:
            stream_asset_ids = [f"stream-{sid}" for sid in bank.stream_ids]
            if not any(e.id == eid for e in events):
                events.append(
                    AudioEvent(id=eid, name=eid, bank_id=bank.short_name, asset_ids=stream_asset_ids)
                )

    return ProjectModel(
        engine="wwise",
        name=os.path.basename(os.path.normpath(root)),
        assets=assets,
        effects=effects,
        buses=buses,
        events=events,
        banks=banks,
        plugins_used=list(plugins),
        metadata=metadata,
    )
