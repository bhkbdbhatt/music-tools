import { promises as fs } from "node:fs";
import path from "node:path";
import type { AudioAsset, AudioBus, AudioEvent, BankInfo, LoadType, ProjectModel } from "@audiosure/core";
import { fileSize, guessDurationSec, readWavInfo, walkFiles } from "./util.js";

interface MetaInfo {
  guid?: string;
  loadType?: LoadType;
  decodeInMemory?: boolean;
  compressionFormat?: string;
  sampleRateOverride?: number;
  quality?: number;
  preloadAudioData?: boolean;
}

const UNITY_LOAD_TYPE: Record<string, LoadType> = {
  "0": "memory",
  "1": "memory",
  "2": "stream",
};

const UNITY_COMPRESSION: Record<string, string> = {
  "0": "pcm",
  "1": "vorbis",
  "2": "adpcm",
  "3": "mp3",
  "4": "pcm",
};

function getYamlScalar(text: string, key: string): string | undefined {
  const re = new RegExp(`^\\s*${key}:\\s*(-?[0-9]+|true|false|"[^"]*"|'[^']*'|[^\\s].*)$`, "m");
  const m = text.match(re);
  if (!m) return undefined;
  return m[1]!.trim().replace(/^["']|["']$/g, "");
}

function parseAudioImporterMeta(text: string): MetaInfo {
  const guid = text.match(/^guid:\s*([0-9a-f]+)$/m)?.[1];
  const block = text.match(/AudioImporter:[\s\S]*?(?=\n[A-Za-z]+:|$)/)?.[0] ?? text;
  const loadTypeRaw = getYamlScalar(block, "loadType");
  const compressionRaw = getYamlScalar(block, "compressionFormat");
  const sampleRateRaw = getYamlScalar(block, "sampleRateOverride");
  const qualityRaw = getYamlScalar(block, "quality");
  const preloadRaw = getYamlScalar(block, "preloadAudioData");
  return {
    guid,
    loadType: loadTypeRaw ? (UNITY_LOAD_TYPE[loadTypeRaw] ?? "memory") : undefined,
    decodeInMemory: loadTypeRaw === "0",
    compressionFormat: compressionRaw ? (UNITY_COMPRESSION[compressionRaw] ?? `fmt${compressionRaw}`) : undefined,
    sampleRateOverride: sampleRateRaw ? Number(sampleRateRaw) : undefined,
    quality: qualityRaw ? Number(qualityRaw) : undefined,
    preloadAudioData: preloadRaw === "true",
  };
}

const AUDIO_EXT = /\.(wav|ogg|mp3|aiff|aif|flac)$/i;

export async function parseUnity(root: string): Promise<ProjectModel> {
  const audioFiles = await walkFiles(root, (rel) => AUDIO_EXT.test(rel) && !/\.meta$/i.test(rel));
  const metaFiles = await walkFiles(root, (rel) => /\.meta$/i.test(rel));

  const metaBySource = new Map<string, MetaInfo>();
  for (const meta of metaFiles) {
    if (!AUDIO_EXT.test(meta.replace(/\.meta$/i, ""))) continue;
    const text = await fs.readFile(meta, "utf8");
    if (!/AudioImporter:/.test(text)) continue;
    const source = meta.replace(/\.meta$/i, "");
    metaBySource.set(path.resolve(source), parseAudioImporterMeta(text));
  }

  const assets: AudioAsset[] = [];
  for (const file of audioFiles) {
    const abs = path.resolve(file);
    const info = metaBySource.get(abs) ?? {};
    const size = await fileSize(abs);
    let duration = 0;
    let channels = 2;
    let sampleRate = info.sampleRateOverride ?? 48000;
    if (/\.wav$/i.test(abs)) {
      const wav = await readWavInfo(abs);
      if (wav) {
        duration = wav.durationSec;
        channels = wav.channels;
        if (!info.sampleRateOverride) sampleRate = wav.sampleRate;
      }
    }
    if (duration <= 0) duration = guessDurationSec(size, info.compressionFormat ?? "vorbis", channels);
    const name = path.basename(abs).replace(AUDIO_EXT, "");
    assets.push({
      id: `unity-${info.guid ?? name}`,
      name,
      path: path.relative(root, abs),
      durationSec: duration,
      channels,
      sampleRate,
      codec: info.compressionFormat ?? "vorbis",
      loadType: info.loadType ?? "memory",
      sizeBytes: size,
      decodeInMemory: info.decodeInMemory ?? false,
      isMusic: /music|bgm|theme|ambient/i.test(name),
      isSfx: true,
      bankId: "Assets",
    });
  }

  const mixerFiles = await walkFiles(root, (rel) => /\.mixer$/i.test(rel));
  const buses: AudioBus[] = [];
  for (const m of mixerFiles) {
    const text = await fs.readFile(m, "utf8");
    const groupCount = (text.match(/AudioMixerGroupController:/g) ?? []).length;
    const snapshotCount = (text.match(/AudioMixerSnapshotController:/g) ?? []).length;
    buses.push({
      id: `mixer-${path.basename(m, ".mixer")}`,
      name: path.basename(m, ".mixer"),
      effectIds: Array.from({ length: groupCount }, (_, i) => `mixer-group-${i}`),
    });
    void snapshotCount;
  }

  const sceneFiles = await walkFiles(root, (rel) => /\.(unity|prefab)$/i.test(rel));
  let audioSourceCount = 0;
  for (const s of sceneFiles) {
    const text = await fs.readFile(s, "utf8");
    audioSourceCount += (text.match(/^AudioSource:/gm) ?? []).length;
  }

  const banks: BankInfo[] = [
    {
      id: "Assets",
      name: "Assets",
      sizeBytes: assets.reduce((n, a) => n + a.sizeBytes, 0),
      memoryBytes: assets.filter((a) => a.loadType !== "stream").reduce((n, a) => n + a.sizeBytes, 0),
      streamIds: assets.filter((a) => a.loadType === "stream").map((a) => a.id),
      assetIds: assets.filter((a) => a.loadType !== "stream").map((a) => a.id),
    },
  ];

  const events: AudioEvent[] = [];

  return {
    engine: "unity",
    name: path.basename(path.resolve(root)),
    assets,
    effects: [],
    buses,
    events,
    banks,
    pluginsUsed: ["Unity Audio"],
    metadata: {
      audioSourceCount,
      mixerCount: mixerFiles.length,
    },
  };
}
