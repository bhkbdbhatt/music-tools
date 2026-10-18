from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import Dict, List, Optional


def _ensure_dir(directory: str) -> None:
    os.makedirs(directory, exist_ok=True)


def _write_file(file_path: str, data: bytes) -> None:
    _ensure_dir(os.path.dirname(file_path))
    with open(file_path, "wb") as f:
        f.write(data)


def wav_buffer(
    duration_sec: float,
    sample_rate: int = 48000,
    channels: int = 2,
    bits_per_sample: int = 16,
    declared_data_bytes: Optional[int] = None,
) -> bytes:
    real_bytes = int(duration_sec * sample_rate * channels * (bits_per_sample / 8))
    declared = declared_data_bytes if declared_data_bytes is not None else real_bytes
    payload = min(real_bytes, 4096)
    buf = bytearray(44 + payload)
    buf[0:4] = b"RIFF"
    struct.pack_into("<I", buf, 4, 36 + declared)
    buf[8:12] = b"WAVE"
    buf[12:16] = b"fmt "
    struct.pack_into("<I", buf, 16, 16)
    struct.pack_into("<H", buf, 20, 1)
    struct.pack_into("<H", buf, 22, channels)
    struct.pack_into("<I", buf, 24, sample_rate)
    struct.pack_into("<I", buf, 28, sample_rate * channels * (bits_per_sample // 8))
    struct.pack_into("<H", buf, 32, channels * (bits_per_sample // 8))
    struct.pack_into("<H", buf, 34, bits_per_sample)
    buf[36:40] = b"data"
    struct.pack_into("<I", buf, 40, declared)
    return bytes(buf)


def bnk_buffer(bank_id: int, version: int = 150, didx: Optional[List[Dict[str, int]]] = None, hirc_objects: Optional[int] = None) -> bytes:
    didx = didx or []
    hirc_count = hirc_objects if hirc_objects is not None else len(didx)

    bkhd = bytearray(8 + 8)
    bkhd[0:4] = b"BKHD"
    struct.pack_into("<I", bkhd, 4, 8)
    struct.pack_into("<I", bkhd, 8, version)
    struct.pack_into("<I", bkhd, 12, bank_id)

    didx_buf = bytearray(8 + len(didx) * 12)
    didx_buf[0:4] = b"DIDX"
    struct.pack_into("<I", didx_buf, 4, len(didx) * 12)
    data_offset = 0
    for i, e in enumerate(didx):
        o = 8 + i * 12
        struct.pack_into("<III", didx_buf, o, e["sourceId"], data_offset, e["size"])
        data_offset += e["size"]

    data_placeholder = bytes(4096)
    data_buf = bytearray(8 + len(data_placeholder))
    data_buf[0:4] = b"DATA"
    struct.pack_into("<I", data_buf, 4, len(data_placeholder))
    data_buf[8:] = data_placeholder

    hirc = bytearray(8 + 4 + hirc_count * 8)
    hirc[0:4] = b"HIRC"
    struct.pack_into("<I", hirc, 4, 4 + hirc_count * 8)
    struct.pack_into("<I", hirc, 8, hirc_count)

    return bytes(bkhd) + bytes(didx_buf) + bytes(data_buf) + bytes(hirc)


def fsb5_buffer(num_samples: int, data_size: int, mode: int = 7) -> bytes:
    header = bytearray(0x20)
    header[0:4] = b"FSB5"
    struct.pack_into("<I", header, 0x04, 1)
    struct.pack_into("<I", header, 0x08, num_samples)
    struct.pack_into("<I", header, 0x0C, max(4, num_samples * 4))
    struct.pack_into("<I", header, 0x10, 0)
    struct.pack_into("<I", header, 0x14, data_size)
    struct.pack_into("<I", header, 0x18, mode)
    return bytes(header) + bytes(4096)


def generate_wwise_demo(root: str) -> None:
    sb = os.path.join(root, "Audio", "GeneratedSoundBanks", "Windows")
    wu = os.path.join(root, "WorkUnits")
    streamed = os.path.join(root, "Audio", "Streamed")

    streams = [
        {"id": 31001, "name": "Music_Theme_01", "file": "Music_Theme_01.wem", "size": 2_880_000, "language": None},
        {"id": 31002, "name": "Music_Combat_01", "file": "Music_Combat_01.wem", "size": 2_400_000, "language": None},
        {"id": 31003, "name": "Amb_Forest_Loop", "file": "Amb_Forest_Loop.wem", "size": 1_200_000, "language": None},
        {"id": 31004, "name": "VO_Player_Grunt", "file": "VO_Player_Grunt.wem", "size": 48_000, "language": "English"},
        {"id": 31005, "name": "SFX_Explosion_Short", "file": "SFX_Explosion_Short.wem", "size": 36_000, "language": None},
    ]
    for s in streams:
        _write_file(os.path.join(streamed, s["file"]), bytes(s["size"]))

    _write_file(
        os.path.join(sb, "SFX.bnk"),
        bnk_buffer(
            bank_id=1355168291,
            didx=[{"sourceId": 40000 + i, "size": 600_000} for i in range(300)],
            hirc_objects=340,
        ),
    )
    _write_file(
        os.path.join(sb, "VO.bnk"),
        bnk_buffer(
            bank_id=202899026,
            didx=[{"sourceId": 50000 + i, "size": 60_000} for i in range(20)],
            hirc_objects=40,
        ),
    )
    _write_file(os.path.join(sb, "Music.bnk"), bnk_buffer(bank_id=3991942870, didx=[], hirc_objects=8))
    _write_file(os.path.join(sb, "Init.bnk"), bnk_buffer(bank_id=1355168291 - 1, didx=[], hirc_objects=4))

    streamed_xml = "\n".join(
        f'      <StreamedFile Id="{s["id"]}" Name="{s["name"]}" Language="{s["language"] or "SFX"}" '
        f'Path="Audio/Streamed/{s["file"]}" SoundBankShortName="{"Music" if ("Music" in s["name"] or "Amb" in s["name"]) else "SFX"}" />'
        for s in streams
    )

    sound_banks_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<SoundBankInfo>
  <RootPath>Audio/GeneratedSoundBanks/Windows</RootPath>
  <SoundBankPlatform>Windows</SoundBankPlatform>
  <StreamedFiles>
{streamed_xml}
  </StreamedFiles>
  <SoundBanks>
    <SoundBank ShortName="Init" Id="1355168290" Name="Init.bnk" Path="Init.bnk" Platform="Windows" MemoryBytes="4096" SizeBytes="4200" Language="SFX">
      <EventList>
        <Event Id="1001" Name="Play_Init" />
      </EventList>
    </SoundBank>
    <SoundBank ShortName="SFX" Id="1355168291" Name="SFX.bnk" Path="SFX.bnk" Platform="Windows" MemoryBytes="180000000" SizeBytes="180040000" Language="SFX">
      <StreamedFileList>
        <StreamedFile Id="31005" />
      </StreamedFileList>
      <EventList>
        <Event Id="2001" Name="Play_Gunshot" />
        <Event Id="2002" Name="Play_Explosion" />
        <Event Id="2003" Name="Play_Footstep" />
      </EventList>
    </SoundBank>
    <SoundBank ShortName="Music" Id="3991942870" Name="Music.bnk" Path="Music.bnk" Platform="Windows" MemoryBytes="8192" SizeBytes="12000" Language="SFX">
      <StreamedFileList>
        <StreamedFile Id="31001" />
        <StreamedFile Id="31002" />
        <StreamedFile Id="31003" />
      </StreamedFileList>
      <EventList>
        <Event Id="3001" Name="Play_Music_Theme" />
        <Event Id="3002" Name="Play_Music_Combat" />
      </EventList>
    </SoundBank>
    <SoundBank ShortName="VO" Id="202899026" Name="VO.bnk" Path="VO.bnk" Platform="Windows" MemoryBytes="1200000" SizeBytes="1210000" Language="English">
      <StreamedFileList>
        <StreamedFile Id="31004" />
      </StreamedFileList>
      <EventList>
        <Event Id="4001" Name="Play_VO_Grunt" />
      </EventList>
    </SoundBank>
  </SoundBanks>
</SoundBankInfo>
"""
    _write_file(os.path.join(root, "Audio", "SoundBanksInfo.xml"), sound_banks_xml.encode("utf-8"))

    actors_wwu = """<?xml version="1.0" encoding="utf-8"?>
<WwiseDocument Type="WorkUnit" ID="{11111111-1111-1111-1111-111111111111}" SchemaVersion="2">
  <AudioObjects>
    <ActorMixerHierarchy>
      <ActorMixer Name="Default Work Unit" ID="{20000000-0000-0000-0000-000000000001}">
        <Event Name="Play_Explosion" ID="{30000000-0000-0000-0000-000000000001}">
          <Property Name="MaxAttenuation" Value="120" />
        </Event>
        <Event Name="Play_Footstep" ID="{30000000-0000-0000-0000-000000000002}" />
        <Event Name="Play_Music_Theme" ID="{30000000-0000-0000-0000-000000000003}" />
      </ActorMixer>
    </ActorMixerHierarchy>
  </AudioObjects>
</WwiseDocument>
"""
    _write_file(os.path.join(wu, "Actors.wwu"), actors_wwu.encode("utf-8"))

    buses_wwu = """<?xml version="1.0" encoding="utf-8"?>
<WwiseDocument Type="WorkUnit" ID="{22222222-2222-2222-2222-222222222222}" SchemaVersion="2">
  <AudioObjects>
    <Bus Name="Master Audio Bus" ID="{40000000-0000-0000-0000-000000000001}" />
    <AuxBus Name="Reverb_Large_Hall" ID="{40000000-0000-0000-0000-000000000002}">
      <Fx Plugin="Audiokinetic Wwise Convolution Reverb" Name="Reverb_Large_Hall_Conv" ID="{50000000-0000-0000-0000-000000000001}">
        <Property Name="uIRDurationSec" Value="2.0" />
        <Property Name="uIRChannelCount" Value="2" />
      </Fx>
    </AuxBus>
    <AuxBus Name="Reverb_Cave" ID="{40000000-0000-0000-0000-000000000003}">
      <Fx Plugin="Audiokinetic Wwise Convolution Reverb" Name="Reverb_Cave_Conv" ID="{50000000-0000-0000-0000-000000000002}">
        <Property Name="uIRDurationSec" Value="2.5" />
        <Property Name="uIRChannelCount" Value="2" />
      </Fx>
    </AuxBus>
    <AuxBus Name="Reverb_Small_Room" ID="{40000000-0000-0000-0000-000000000004}">
      <Fx Plugin="Audiokinetic Wwise Convolution Reverb" Name="Reverb_Small_Room_Conv" ID="{50000000-0000-0000-0000-000000000003}">
        <Property Name="uIRDurationSec" Value="1.5" />
        <Property Name="uIRChannelCount" Value="2" />
      </Fx>
    </AuxBus>
    <Bus Name="SFX_Bus" ID="{40000000-0000-0000-0000-000000000005}">
      <Fx Plugin="Audiokinetic Wwise Matrix Reverb" Name="Matrix_Reverb" ID="{50000000-0000-0000-0000-000000000004}" />
    </Bus>
  </AudioObjects>
</WwiseDocument>
"""
    _write_file(os.path.join(wu, "Buses.wwu"), buses_wwu.encode("utf-8"))


def generate_fmod_demo(root: str) -> None:
    _write_file(os.path.join(root, "Build", "PC", "Master.bank"), fsb5_buffer(num_samples=42, data_size=2_000_000))
    _write_file(os.path.join(root, "Build", "PC", "Master.strings.bank"), fsb5_buffer(num_samples=0, data_size=0))
    _write_file(
        os.path.join(root, "Build", "PC", "Music.bank"), fsb5_buffer(num_samples=6, data_size=9_000_000, mode=7)
    )

    sounds = [
        {"id": "explosion", "name": "SFX_Explosion", "duration": "3.0", "codec": "vorbis", "loadType": "stream", "size": 36000, "cat": "sfx"},
        {"id": "footstep", "name": "SFX_Footstep_Stone", "duration": "0.4", "codec": "vorbis", "loadType": "memory", "size": 12000, "cat": "sfx"},
        {"id": "gunshot", "name": "SFX_Gunshot_Rifle", "duration": "0.9", "codec": "vorbis", "loadType": "memory", "size": 28000, "cat": "sfx"},
        {"id": "ui_click", "name": "UI_Click", "duration": "0.12", "codec": "vorbis", "loadType": "memory", "size": 6000, "cat": "ui"},
        {"id": "amb_forest", "name": "Amb_Forest_Loop", "duration": "120", "codec": "vorbis", "loadType": "stream", "size": 1_440_000, "cat": "ambience"},
        {"id": "music_theme", "name": "Music_Theme", "duration": "240", "codec": "vorbis", "loadType": "stream", "size": 2_880_000, "cat": "music"},
        {"id": "music_combat", "name": "Music_Combat", "duration": "200", "codec": "vorbis", "loadType": "stream", "size": 2_400_000, "cat": "music"},
        {"id": "vo_grunt", "name": "VO_Player_Grunt", "duration": "4.0", "codec": "vorbis", "loadType": "stream", "size": 48000, "cat": "vo"},
    ] + [
        {
            "id": f"sfx_pack_{i}",
            "name": f"SFX_Impacts_Pack_{i}",
            "duration": "1.5",
            "codec": "vorbis",
            "loadType": "memory",
            "size": 4_000_000,
            "cat": "sfx",
        }
        for i in range(24)
    ]

    sounds_xml = "\n".join(
        f'    <Sound id="{s["id"]}" name="{s["name"]}" duration="{s["duration"]}" channels="2" '
        f'sampleRate="48000" codec="{s["codec"]}" loadType="{s["loadType"]}" sizeBytes="{s["size"]}" '
        f'bank="{"Music" if ("music" in s["cat"] or "amb" in s["cat"]) else "Master"}" category="{s["cat"]}" />'
        for s in sounds
    )

    export_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<AudioProject name="FmodDemo">
  <Buses>
    <Bus name="bus:/" />
    <Bus name="bus:/SFX" />
    <Bus name="bus:/Music" />
    <Bus name="bus:/VO" />
  </Buses>
  <Sounds>
{sounds_xml}
  </Sounds>
  <Events>
    <Event name="event:/SFX/Explosion" bank="Master" maxInstances="2"><Sound ref="explosion" /></Event>
    <Event name="event:/SFX/Footstep" bank="Master" maxInstances="6"><Sound ref="footstep" /></Event>
    <Event name="event:/SFX/Gunshot" bank="Master" maxInstances="8"><Sound ref="gunshot" /></Event>
    <Event name="event:/Music/Theme" bank="Music" maxInstances="1"><Sound ref="music_theme" /></Event>
    <Event name="event:/Music/Combat" bank="Music" maxInstances="1"><Sound ref="music_combat" /></Event>
    <Event name="event:/Amb/Forest" bank="Music" maxInstances="1"><Sound ref="amb_forest" /></Event>
  </Events>
</AudioProject>
"""
    _write_file(os.path.join(root, "audio-export.xml"), export_xml.encode("utf-8"))

    for s in ["SFX_Explosion", "SFX_Footstep", "SFX_Gunshot"]:
        _write_file(
            os.path.join(root, "Assets", "sfx", f"{s}.wav"),
            wav_buffer(duration_sec=1, declared_data_bytes=96000),
        )


def _deterministic_guid(seed: str) -> str:
    h = 2166136261
    for ch in seed.encode("utf-8"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    out = ""
    x = h
    while len(out) < 32:
        x = (x * 1664525 + 1013904223) & 0xFFFFFFFF
        out += f"{x:08x}"
    return out[:32]


def generate_unity_demo(root: str) -> None:
    audio_dir = os.path.join(root, "Assets", "Audio")
    clips = [
        {"name": "sfx_footstep", "loadType": 0, "compression": 1, "duration": 0.5, "declaredDataBytes": None},
        {"name": "sfx_gunshot", "loadType": 0, "compression": 1, "duration": 1.0, "declaredDataBytes": None},
        {"name": "sfx_ui_click", "loadType": 0, "compression": 0, "duration": 0.2, "declaredDataBytes": None},
        {"name": "vo_player_grunt", "loadType": 1, "compression": 1, "duration": 4.0, "declaredDataBytes": None},
        {"name": "amb_forest_loop", "loadType": 2, "compression": 1, "duration": 180, "declaredDataBytes": None},
        {"name": "music_theme", "loadType": 2, "compression": 1, "duration": 240, "declaredDataBytes": None},
        {"name": "music_combat", "loadType": 2, "compression": 1, "duration": 200, "declaredDataBytes": None},
        {"name": "sfx_explosion", "loadType": 0, "compression": 1, "duration": 3.0, "declaredDataBytes": None},
    ] + [
        {"name": f"sfx_impacts_{i}", "loadType": 0, "compression": 1, "duration": 1.0, "declaredDataBytes": 20_000_000}
        for i in range(10)
    ]

    for c in clips:
        file_path = os.path.join(audio_dir, f"{c['name']}.wav")
        _write_file(file_path, wav_buffer(duration_sec=c["duration"], declared_data_bytes=c["declaredDataBytes"]))
        guid = _deterministic_guid(c["name"])
        preload = "true" if c["loadType"] == 0 else "false"
        meta = f"""fileFormatVersion: 2
guid: {guid}
AudioImporter:
  externalObjects: {{}}
  serializedVersion: 7
  defaultSettings:
    serializedVersion: 2
    loadType: {c['loadType']}
    sampleRateSetting: 0
    sampleRateOverride: 48000
    compressionFormat: {c['compression']}
    quality: 0.7
    conversionMode: 0
    preloadAudioData: {preload}
  platformSettingOverrides: {{}}
  forceToMono: 0
  normalize: 1
  preloadAudioData: 1
  loadInBackground: 0
  ambisonic: 0
  userData:
  assetBundleName:
  assetBundleVariant:
"""
        _write_file(f"{file_path}.meta", meta.encode("utf-8"))

    mixer = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!241 &24100000
AudioMixerController:
  m_ObjectHideFlags: 0
  m_Name: MainMixer
  m_Children:
  - {fileID: 24100001}
  - {fileID: 24100002}
  - {fileID: 24100003}
  m_EnableSpatialPreprocessing: 0
--- !u!243 &24100001
AudioMixerGroupController:
  m_ObjectHideFlags: 0
  m_Name: Master
--- !u!243 &24100002
AudioMixerGroupController:
  m_ObjectHideFlags: 0
  m_Name: SFX
--- !u!243 &24100003
AudioMixerGroupController:
  m_ObjectHideFlags: 0
  m_Name: Music
--- !u!244 &24100004
AudioMixerSnapshotController:
  m_ObjectHideFlags: 0
  m_Name: Normal
"""
    _write_file(os.path.join(root, "Assets", "MainMixer.mixer"), mixer.encode("utf-8"))

    sources = "".join(
        f"""--- !u!82 &{21000000 + i}
AudioSource:
  m_ObjectHideFlags: 0
  m_Name: AudioSource_{i}
  m_audioClip: {{fileID: 8300000, guid: {_deterministic_guid(f"sfx_impacts_{i % 10}")}, type: 3}}
  m_playOnAwake: 1
  m_loop: 0
"""
        for i in range(18)
    )
    _write_file(
        os.path.join(root, "Assets", "Scenes", "Level01.unity"),
        ("%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n" + sources).encode("utf-8"),
    )


@dataclass
class FixtureResult:
    root: str
    projects: List[str]


def generate_all_fixtures(fixtures_root: str) -> FixtureResult:
    root = os.path.abspath(fixtures_root)
    projects: List[str] = []
    wwu = os.path.join(root, "wwu-demo")
    fmod = os.path.join(root, "fmod-demo")
    unity = os.path.join(root, "unity-demo")

    generate_wwise_demo(wwu)
    projects.append(wwu)
    generate_fmod_demo(fmod)
    projects.append(fmod)
    generate_unity_demo(unity)
    projects.append(unity)

    return FixtureResult(root=root, projects=projects)
