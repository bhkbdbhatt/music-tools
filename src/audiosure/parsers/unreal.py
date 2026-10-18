from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from audiosure.core.types import AudioAsset, AudioBus, AudioEffect, AudioEvent, BankInfo, ProjectModel
from audiosure.parsers.util import guess_duration_sec, walk_files

NUM_RE = re.compile(r"(-?\d+(?:\.\d+)?)")


def _map_loading_behavior(v: Optional[str]) -> str:
    if not v:
        return "memory"
    s = v.lower()
    if "stream" in s:
        return "stream"
    if "preload" in s:
        return "preload"
    return "memory"


def parse_unreal(root: str) -> ProjectModel:
    inventory_path = next(
        iter(walk_files(root, lambda rel, _: bool(re.search(r"AudioInventory\.json$", rel, re.I)))), None
    )
    metadata: Dict[str, Any] = {"inventoryFound": bool(inventory_path)}

    if not inventory_path:
        return ProjectModel(
            engine="unreal",
            name=os.path.basename(os.path.normpath(root)),
            assets=[],
            effects=[],
            buses=[],
            events=[],
            banks=[],
            plugins_used=["Unreal Audio Engine"],
            metadata={
                **metadata,
                "hint": "Export AudioInventory.json from the Unreal editor (see docs/UNREAL.md).",
            },
        )

    with open(inventory_path, "r", encoding="utf-8") as f:
        inv = json.load(f)
    assets: List[AudioAsset] = []
    name_to_id: Dict[str, str] = {}

    for sw in inv.get("soundWaves") or []:
        sid = f"unreal-{sw['name']}"
        name_to_id[sw["name"]] = sid
        size_bytes = sw.get("sizeBytes") or 0
        channels = sw.get("channels") or 2
        codec = (sw.get("compression") or "vorbis").lower()
        duration = (
            sw["durationSec"]
            if sw.get("durationSec") and sw["durationSec"] > 0
            else guess_duration_sec(size_bytes, codec, channels)
        )
        loading_behavior = sw.get("loadingBehavior") or ""
        assets.append(
            AudioAsset(
                id=sid,
                name=sw["name"],
                path=sw.get("path"),
                duration_sec=duration,
                channels=channels,
                sample_rate=sw.get("sampleRate") or 48000,
                codec=codec,
                load_type=_map_loading_behavior(sw.get("loadingBehavior")),
                size_bytes=size_bytes,
                decode_in_memory="forceinline" in loading_behavior.lower(),
                is_music=sw.get("isMusic")
                if sw.get("isMusic") is not None
                else bool(re.search(r"music|bgm|theme|ambient", sw["name"], re.I)),
                is_sfx=not bool(re.search(r"music|bgm|theme", sw["name"], re.I)),
                bank_id="UnrealAssets",
            )
        )

    events: List[AudioEvent] = []
    for cue in inv.get("soundCues") or []:
        events.append(
            AudioEvent(
                id=f"cue-{cue['name']}",
                name=cue["name"],
                bank_id="UnrealAssets",
                asset_ids=[name_to_id.get(n, f"unreal-{n}") for n in (cue.get("soundWaveNames") or [])],
                max_instances=cue.get("maxConcurrentInstances"),
            )
        )

    effects: List[AudioEffect] = []
    buses: List[AudioBus] = []
    mixer = inv.get("audioMixer")
    if mixer:
        for i, name in enumerate(mixer.get("submixes") or []):
            buses.append(AudioBus(id=f"submix-{i}", name=name, effect_ids=[]))
        for i, fx in enumerate(mixer.get("effects") or []):
            params: Dict[str, Any] = dict(fx.get("params") or {})
            plugin = fx.get("plugin") or fx.get("name")
            if re.search(r"convol", plugin, re.I):
                for k, v in params.items():
                    m = NUM_RE.search(str(v))
                    if re.search(r"ir|impulse|duration|length", k, re.I) and m:
                        params["irDurationSec"] = float(m.group(1))
            effects.append(AudioEffect(id=f"ue-fx-{i}", name=fx.get("name", ""), plugin=plugin, params=params))

    banks: List[BankInfo] = [
        BankInfo(
            id="UnrealAssets",
            name="UnrealAssets",
            size_bytes=sum(a.size_bytes for a in assets),
            memory_bytes=sum(a.size_bytes for a in assets if a.load_type != "stream"),
            stream_ids=[a.id for a in assets if a.load_type == "stream"],
            asset_ids=[a.id for a in assets if a.load_type != "stream"],
        )
    ]

    plugins_used: List[str] = []
    seen = set()
    for e in effects:
        if e.plugin not in seen:
            seen.add(e.plugin)
            plugins_used.append(e.plugin)

    return ProjectModel(
        engine="unreal",
        name=inv.get("project") or os.path.basename(os.path.normpath(root)),
        assets=assets,
        effects=effects,
        buses=buses,
        events=events,
        banks=banks,
        plugins_used=plugins_used,
        metadata=metadata,
    )
