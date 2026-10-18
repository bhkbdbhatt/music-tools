import { promises as fs } from "node:fs";
import path from "node:path";

async function ensureDir(dir: string): Promise<void> {
  await fs.mkdir(dir, { recursive: true });
}

async function writeFile(file: string, data: string | Buffer): Promise<void> {
  await ensureDir(path.dirname(file));
  await fs.writeFile(file, data);
}

function wavBuffer(opts: {
  durationSec: number;
  sampleRate?: number;
  channels?: number;
  bitsPerSample?: number;
  declaredDataBytes?: number;
}): Buffer {
  const sampleRate = opts.sampleRate ?? 48000;
  const channels = opts.channels ?? 2;
  const bits = opts.bitsPerSample ?? 16;
  const realBytes = Math.floor(opts.durationSec * sampleRate * channels * (bits / 8));
  const declared = opts.declaredDataBytes ?? realBytes;
  const payload = Math.min(realBytes, 4096);
  const buf = Buffer.alloc(44 + payload);
  buf.write("RIFF", 0, "ascii");
  buf.writeUInt32LE(36 + declared, 4);
  buf.write("WAVE", 8, "ascii");
  buf.write("fmt ", 12, "ascii");
  buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20);
  buf.writeUInt16LE(channels, 22);
  buf.writeUInt32LE(sampleRate, 24);
  buf.writeUInt32LE(sampleRate * channels * (bits / 8), 28);
  buf.writeUInt16LE(channels * (bits / 8), 32);
  buf.writeUInt16LE(bits, 34);
  buf.write("data", 36, "ascii");
  buf.writeUInt32LE(declared, 40);
  return buf;
}

interface DidxEntry {
  sourceId: number;
  size: number;
}

function bnkBuffer(opts: {
  bankId: number;
  version?: number;
  didx?: DidxEntry[];
  hircObjects?: number;
}): Buffer {
  const version = opts.version ?? 150;
  const didx = opts.didx ?? [];
  const hircObjects = opts.hircObjects ?? didx.length;

  const bkhd = Buffer.alloc(8 + 8);
  bkhd.write("BKHD", 0, "ascii");
  bkhd.writeUInt32LE(8, 4);
  bkhd.writeUInt32LE(version, 8);
  bkhd.writeUInt32LE(opts.bankId, 12);

  const didxBuf = Buffer.alloc(8 + didx.length * 12);
  let dataOffset = 0;
  didxBuf.write("DIDX", 0, "ascii");
  didxBuf.writeUInt32LE(didx.length * 12, 4);
  didx.forEach((e, i) => {
    const o = 8 + i * 12;
    didxBuf.writeUInt32LE(e.sourceId, o);
    didxBuf.writeUInt32LE(dataOffset, o + 4);
    didxBuf.writeUInt32LE(e.size, o + 8);
    dataOffset += e.size;
  });

  const dataPlaceholder = Buffer.alloc(4096, 0);
  const dataBuf = Buffer.alloc(8 + dataPlaceholder.length);
  dataBuf.write("DATA", 0, "ascii");
  dataBuf.writeUInt32LE(dataPlaceholder.length, 4);
  dataPlaceholder.copy(dataBuf, 8);

  const hirc = Buffer.alloc(8 + 4 + hircObjects * 8);
  hirc.write("HIRC", 0, "ascii");
  hirc.writeUInt32LE(4 + hircObjects * 8, 4);
  hirc.writeUInt32LE(hircObjects, 8);

  return Buffer.concat([bkhd, didxBuf, dataBuf, hirc]);
}

function fsb5Buffer(opts: { numSamples: number; dataSize: number; mode?: number }): Buffer {
  const header = Buffer.alloc(0x20);
  header.write("FSB5", 0, "ascii");
  header.writeUInt32LE(1, 0x04);
  header.writeUInt32LE(opts.numSamples, 0x08);
  header.writeUInt32LE(Math.max(4, opts.numSamples * 4), 0x0c);
  header.writeUInt32LE(0, 0x10);
  header.writeUInt32LE(opts.dataSize, 0x14);
  header.writeUInt32LE(opts.mode ?? 7, 0x18);
  return Buffer.concat([header, Buffer.alloc(4096, 0)]);
}

export async function generateWwiseDemo(root: string): Promise<void> {
  const sb = path.join(root, "Audio", "GeneratedSoundBanks", "Windows");
  const wu = path.join(root, "WorkUnits");
  const streamed = path.join(root, "Audio", "Streamed");

  const streams: Array<{ id: number; name: string; file: string; size: number; language?: string }> = [
    { id: 31001, name: "Music_Theme_01", file: "Music_Theme_01.wem", size: 2_880_000 },
    { id: 31002, name: "Music_Combat_01", file: "Music_Combat_01.wem", size: 2_400_000 },
    { id: 31003, name: "Amb_Forest_Loop", file: "Amb_Forest_Loop.wem", size: 1_200_000 },
    { id: 31004, name: "VO_Player_Grunt", file: "VO_Player_Grunt.wem", size: 48_000, language: "English" },
    { id: 31005, name: "SFX_Explosion_Short", file: "SFX_Explosion_Short.wem", size: 36_000 },
  ];
  for (const s of streams) {
    await writeFile(path.join(streamed, s.file), Buffer.alloc(s.size, 0));
  }

  await writeFile(
    path.join(sb, "SFX.bnk"),
    bnkBuffer({
      bankId: 1355168291,
      didx: Array.from({ length: 300 }, (_, i) => ({ sourceId: 40000 + i, size: 600_000 })),
      hircObjects: 340,
    }),
  );
  await writeFile(
    path.join(sb, "VO.bnk"),
    bnkBuffer({
      bankId: 202899026,
      didx: Array.from({ length: 20 }, (_, i) => ({ sourceId: 50000 + i, size: 60_000 })),
      hircObjects: 40,
    }),
  );
  await writeFile(path.join(sb, "Music.bnk"), bnkBuffer({ bankId: 3991942870, didx: [], hircObjects: 8 }));
  await writeFile(path.join(sb, "Init.bnk"), bnkBuffer({ bankId: 1355168291 - 1, didx: [], hircObjects: 4 }));

  const streamedXml = streams
    .map(
      (s) =>
        `      <StreamedFile Id="${s.id}" Name="${s.name}" Language="${s.language ?? "SFX"}" Path="Audio/Streamed/${s.file}" SoundBankShortName="${/Music|Amb/.test(s.name) ? "Music" : "SFX"}" />`,
    )
    .join("\n");

  const soundBanksXml = `<?xml version="1.0" encoding="utf-8"?>
<SoundBankInfo>
  <RootPath>Audio/GeneratedSoundBanks/Windows</RootPath>
  <SoundBankPlatform>Windows</SoundBankPlatform>
  <StreamedFiles>
${streamedXml}
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
`;
  await writeFile(path.join(root, "Audio", "SoundBanksInfo.xml"), soundBanksXml);

  const actorsWwu = `<?xml version="1.0" encoding="utf-8"?>
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
`;
  await writeFile(path.join(wu, "Actors.wwu"), actorsWwu);

  const busesWwu = `<?xml version="1.0" encoding="utf-8"?>
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
      </Fx>
    </AuxBus>
    <Bus Name="SFX_Bus" ID="{40000000-0000-0000-0000-000000000005}">
      <Fx Plugin="Audiokinetic Wwise Matrix Reverb" Name="Matrix_Reverb" ID="{50000000-0000-0000-0000-000000000004}" />
    </Bus>
  </AudioObjects>
</WwiseDocument>
`;
  await writeFile(path.join(wu, "Buses.wwu"), busesWwu);
}

export async function generateFmodDemo(root: string): Promise<void> {
  await writeFile(path.join(root, "Build", "PC", "Master.bank"), fsb5Buffer({ numSamples: 42, dataSize: 2_000_000 }));
  await writeFile(path.join(root, "Build", "PC", "Master.strings.bank"), fsb5Buffer({ numSamples: 0, dataSize: 0 }));
  await writeFile(path.join(root, "Build", "PC", "Music.bank"), fsb5Buffer({ numSamples: 6, dataSize: 9_000_000, mode: 7 }));

  const sounds = [
    { id: "explosion", name: "SFX_Explosion", duration: "3.0", codec: "vorbis", loadType: "stream", size: 36000, cat: "sfx" },
    { id: "footstep", name: "SFX_Footstep_Stone", duration: "0.4", codec: "vorbis", loadType: "memory", size: 12000, cat: "sfx" },
    { id: "gunshot", name: "SFX_Gunshot_Rifle", duration: "0.9", codec: "vorbis", loadType: "memory", size: 28000, cat: "sfx" },
    { id: "ui_click", name: "UI_Click", duration: "0.12", codec: "vorbis", loadType: "memory", size: 6000, cat: "ui" },
    { id: "amb_forest", name: "Amb_Forest_Loop", duration: "120", codec: "vorbis", loadType: "stream", size: 1_440_000, cat: "ambience" },
    { id: "music_theme", name: "Music_Theme", duration: "240", codec: "vorbis", loadType: "stream", size: 2_880_000, cat: "music" },
    { id: "music_combat", name: "Music_Combat", duration: "200", codec: "vorbis", loadType: "stream", size: 2_400_000, cat: "music" },
    { id: "vo_grunt", name: "VO_Player_Grunt", duration: "4.0", codec: "vorbis", loadType: "stream", size: 48000, cat: "vo" },
    ...Array.from({ length: 24 }, (_, i) => ({
      id: `sfx_pack_${i}`,
      name: `SFX_Impacts_Pack_${i}`,
      duration: "1.5",
      codec: "vorbis",
      loadType: "memory",
      size: 4_000_000,
      cat: "sfx",
    })),
  ];

  const soundsXml = sounds
    .map(
      (s) =>
        `    <Sound id="${s.id}" name="${s.name}" duration="${s.duration}" channels="2" sampleRate="48000" codec="${s.codec}" loadType="${s.loadType}" sizeBytes="${s.size}" bank="${/music|amb/i.test(s.cat) ? "Music" : "Master"}" category="${s.cat}" />`,
    )
    .join("\n");

  const exportXml = `<?xml version="1.0" encoding="utf-8"?>
<AudioProject name="FmodDemo">
  <Buses>
    <Bus name="bus:/" />
    <Bus name="bus:/SFX" />
    <Bus name="bus:/Music" />
    <Bus name="bus:/VO" />
  </Buses>
  <Sounds>
${soundsXml}
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
`;
  await writeFile(path.join(root, "audio-export.xml"), exportXml);

  for (const s of ["SFX_Explosion", "SFX_Footstep", "SFX_Gunshot"]) {
    await writeFile(path.join(root, "Assets", "sfx", `${s}.wav`), wavBuffer({ durationSec: 1, declaredDataBytes: 96000 }));
  }
}

export async function generateUnityDemo(root: string): Promise<void> {
  const audioDir = path.join(root, "Assets", "Audio");
  const clips: Array<{
    name: string;
    loadType: number;
    compression: number;
    duration: number;
    declaredDataBytes?: number;
    codec: string;
  }> = [
    { name: "sfx_footstep", loadType: 0, compression: 1, duration: 0.5, codec: "wav" },
    { name: "sfx_gunshot", loadType: 0, compression: 1, duration: 1.0, codec: "wav" },
    { name: "sfx_ui_click", loadType: 0, compression: 0, duration: 0.2, codec: "wav" },
    { name: "vo_player_grunt", loadType: 1, compression: 1, duration: 4.0, codec: "wav" },
    { name: "amb_forest_loop", loadType: 2, compression: 1, duration: 180, codec: "wav" },
    { name: "music_theme", loadType: 2, compression: 1, duration: 240, codec: "wav" },
    { name: "music_combat", loadType: 2, compression: 1, duration: 200, codec: "wav" },
    { name: "sfx_explosion", loadType: 0, compression: 1, duration: 3.0, codec: "wav" },
    ...Array.from({ length: 10 }, (_, i) => ({
      name: `sfx_impacts_${i}`,
      loadType: 0,
      compression: 1,
      duration: 1.0,
      declaredDataBytes: 20_000_000,
      codec: "wav",
    })),
  ];

  for (const c of clips) {
    const file = path.join(audioDir, `${c.name}.wav`);
    await writeFile(file, wavBuffer({ durationSec: c.duration, declaredDataBytes: c.declaredDataBytes }));
    const guid = deterministicGuid(c.name);
    const meta = `fileFormatVersion: 2
guid: ${guid}
AudioImporter:
  externalObjects: {}
  serializedVersion: 7
  defaultSettings:
    serializedVersion: 2
    loadType: ${c.loadType}
    sampleRateSetting: 0
    sampleRateOverride: 48000
    compressionFormat: ${c.compression}
    quality: 0.7
    conversionMode: 0
    preloadAudioData: ${c.loadType === 0 ? "true" : "false"}
  platformSettingOverrides: {}
  forceToMono: 0
  normalize: 1
  preloadAudioData: 1
  loadInBackground: 0
  ambisonic: 0
  userData:
  assetBundleName:
  assetBundleVariant:
`;
    await writeFile(`${file}.meta`, meta);
  }

  const mixer = `%YAML 1.1
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
`;
  await writeFile(path.join(root, "Assets", "MainMixer.mixer"), mixer);

  const sources = Array.from(
    { length: 18 },
    (_, i) => `--- !u!82 &${21000000 + i}
AudioSource:
  m_ObjectHideFlags: 0
  m_Name: AudioSource_${i}
  m_audioClip: {fileID: 8300000, guid: ${deterministicGuid(`sfx_impacts_${i % 10}`)}, type: 3}
  m_playOnAwake: 1
  m_loop: 0
`,
  ).join("");
  await writeFile(
    path.join(root, "Assets", "Scenes", "Level01.unity"),
    `%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
${sources}`,
  );
}

function deterministicGuid(seed: string): string {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  let out = "";
  let x = h >>> 0;
  while (out.length < 32) {
    x = (Math.imul(x, 1664525) + 1013904223) >>> 0;
    out += x.toString(16).padStart(8, "0");
  }
  return out.slice(0, 32);
}

export interface FixtureResult {
  root: string;
  projects: string[];
}

export async function generateAllFixtures(fixturesRoot: string): Promise<FixtureResult> {
  const root = path.resolve(fixturesRoot);
  const projects: string[] = [];
  const wwise = path.join(root, "wwu-demo");
  const fmod = path.join(root, "fmod-demo");
  const unity = path.join(root, "unity-demo");

  await generateWwiseDemo(wwise);
  projects.push(wwise);
  await generateFmodDemo(fmod);
  projects.push(fmod);
  await generateUnityDemo(unity);
  projects.push(unity);

  return { root, projects };
}
