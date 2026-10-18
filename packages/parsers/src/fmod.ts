import { promises as fs } from "node:fs";
import path from "node:path";
import type { AudioAsset, AudioBus, AudioEvent, BankInfo, ProjectModel } from "@audiosure/core";
import { attrStr, childrenByTag, findAll, parseXml } from "./xml.js";
import { guessDurationSec, walkFiles } from "./util.js";

interface Fsb5Header {
  version: number;
  numSamples: number;
  sampleHeadersSize: number;
  nameTableSize: number;
  dataSize: number;
  mode: number;
}

const FSB5_CODECS: Record<number, string> = {
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
};

export function readFsb5Header(buf: Buffer): Fsb5Header | null {
  if (buf.length < 0x20) return null;
  if (buf.toString("ascii", 0, 4) !== "FSB5") return null;
  return {
    version: buf.readUInt32LE(0x04),
    numSamples: buf.readUInt32LE(0x08),
    sampleHeadersSize: buf.readUInt32LE(0x0c),
    nameTableSize: buf.readUInt32LE(0x10),
    dataSize: buf.readUInt32LE(0x14),
    mode: buf.readUInt32LE(0x18),
  };
}

function loadTypeFromAttr(v: string | undefined): AudioAsset["loadType"] {
  if (!v) return "memory";
  const s = v.toLowerCase();
  if (s.includes("stream")) return "stream";
  if (s.includes("preload")) return "preload";
  return "memory";
}

interface StudioExportData {
  assets: AudioAsset[];
  events: AudioEvent[];
  banksMeta: Map<string, { memoryBytes: number; streamBytes: number; assetIds: string[]; streamIds: string[] }>;
}

function parseStudioExport(xml: string): StudioExportData {
  const root = parseXml(xml);
  const assets: AudioAsset[] = [];
  const events: AudioEvent[] = [];
  const banksMeta = new Map<string, { memoryBytes: number; streamBytes: number; assetIds: string[]; streamIds: string[] }>();

  const ensureBank = (name: string) => {
    let b = banksMeta.get(name);
    if (!b) {
      b = { memoryBytes: 0, streamBytes: 0, assetIds: [], streamIds: [] };
      banksMeta.set(name, b);
    }
    return b;
  };

  const soundsNodes = findAll(root, "Sounds").flatMap((c) => childrenByTag(c, "Sound"));
  for (const s of soundsNodes) {
    if (s.tag !== "Sound") continue;
    const id = attrStr(s, "id") ?? attrStr(s, "ref") ?? attrStr(s, "name") ?? `sound-${assets.length}`;
    const name = attrStr(s, "name") ?? id;
    const loadType = loadTypeFromAttr(attrStr(s, "loadType") ?? attrStr(s, "mode"));
    const sizeBytes = Number(attrStr(s, "sizeBytes") ?? attrStr(s, "size") ?? 0) || 0;
    let durationSec = Number(attrStr(s, "duration") ?? 0) || 0;
    const channels = Number(attrStr(s, "channels") ?? 2) || 2;
    const sampleRate = Number(attrStr(s, "sampleRate") ?? 48000) || 48000;
    const codec = attrStr(s, "codec") ?? "vorbis";
    const p = attrStr(s, "path");
    if (durationSec <= 0) durationSec = guessDurationSec(sizeBytes, codec, channels);
    const bank = attrStr(s, "bank") ?? "Master";
    const asset: AudioAsset = {
      id: `fmod-${id}`,
      name,
      path: p,
      durationSec,
      channels,
      sampleRate,
      codec,
      loadType,
      sizeBytes,
      isMusic: attrStr(s, "category") ? /music/i.test(attrStr(s, "category")!) : /music|bgm|theme/i.test(name),
      isSfx: !/music|bgm|theme|ambience/i.test(name),
      language: attrStr(s, "language"),
      bankId: bank,
    };
    assets.push(asset);
    const b = ensureBank(bank);
    if (loadType === "stream") b.streamIds.push(asset.id);
    else {
      b.assetIds.push(asset.id);
      b.memoryBytes += sizeBytes;
    }
  }

  const eventsNodes = findAll(root, "Events").flatMap((c) => childrenByTag(c, "Event"));
  for (const e of eventsNodes) {
    if (e.tag !== "Event") continue;
    const name = attrStr(e, "name") ?? attrStr(e, "id") ?? `event-${events.length}`;
    const bank = attrStr(e, "bank") ?? "Master";
    const assetRefs = childrenByTag(e, "Sound")
      .map((s) => attrStr(s, "ref"))
      .filter((r): r is string => !!r)
      .map((r) => `fmod-${r}`);
    const maxInst = Number(attrStr(e, "maxInstances") ?? 0) || undefined;
    events.push({ id: attrStr(e, "id") ?? name, name, bankId: bank, assetIds: assetRefs, maxInstances: maxInst });
  }

  const busesNodes = root.children.flatMap((c) => (c.tag === "Buses" ? c.children : []));
  void busesNodes;
  return { assets, events, banksMeta };
}

export async function parseFmod(root: string): Promise<ProjectModel> {
  const bankFiles = await walkFiles(root, (rel) => /\.bank$/i.test(rel) && !/\.strings\.bank$/i.test(rel));
  const banks: BankInfo[] = [];
  const metadata: Record<string, unknown> = { fsb5: {} };

  for (const bankPath of bankFiles) {
    const buf = await fs.readFile(bankPath);
    const base = path.basename(bankPath);
    const shortName = base.replace(/\.bank$/i, "");
    const hdr = readFsb5Header(buf);
    const isStreamBank = /stream|music|audio/i.test(shortName) || /\.streams\.bank$/i.test(base);
    let memoryBytes = 0;
    let streamIds: string[] = [];
    let assetIds: string[] = [];
    let codec = "unknown";
    let eventCount = 0;

    if (hdr) {
      codec = FSB5_CODECS[hdr.mode] ?? `mode${hdr.mode}`;
      eventCount = hdr.numSamples;
      if (isStreamBank) streamIds = [];
      else memoryBytes = hdr.dataSize;
      (metadata["fsb5"] as Record<string, unknown>)[shortName] = {
        version: hdr.version,
        numSamples: hdr.numSamples,
        dataSize: hdr.dataSize,
        codec,
      };
    }

    banks.push({
      id: shortName,
      name: shortName,
      sizeBytes: buf.length,
      memoryBytes,
      streamIds,
      assetIds,
    });
  }

  const exportXml = (await walkFiles(root, (rel) => /audio-export\.xml$|studio-export\.xml$|fmod-export\.xml$/i.test(rel)))[0];
  let studio: StudioExportData | null = null;
  if (exportXml) {
    studio = parseStudioExport(await fs.readFile(exportXml, "utf8"));
    metadata["studioExport"] = path.relative(root, exportXml);
  }

  let assets: AudioAsset[] = [];
  let events: AudioEvent[] = [];
  const buses: AudioBus[] = [];

  if (studio) {
    assets = studio.assets;
    events = studio.events;
    const merged: BankInfo[] = banks.map((b) => {
      const meta = studio!.banksMeta.get(b.name);
      if (!meta) return b;
      const hasStreams = meta.streamIds.length > 0;
      return {
        ...b,
        memoryBytes: b.memoryBytes || meta.memoryBytes,
        streamIds: meta.streamIds,
        assetIds: meta.assetIds,
        ...(hasStreams && b.memoryBytes === 0 ? { memoryBytes: meta.memoryBytes } : {}),
      };
    });
    for (const [name, meta] of studio.banksMeta) {
      if (!merged.some((b) => b.name === name)) {
        merged.push({
          id: name,
          name,
          sizeBytes: meta.memoryBytes + meta.streamBytes,
          memoryBytes: meta.memoryBytes,
          streamIds: meta.streamIds,
          assetIds: meta.assetIds,
        });
      }
    }
    banks.length = 0;
    banks.push(...merged);
  } else {
    for (const b of banks) {
      const count = (metadata["fsb5"] as Record<string, { numSamples: number }>)[b.name]?.numSamples ?? 0;
      for (let i = 0; i < count; i++) {
        const perSample = count > 0 ? Math.floor(b.memoryBytes / count) : 0;
        const id = `${b.name}-s${i}`;
        assets.push({
          id: `fmod-${id}`,
          name: id,
          durationSec: guessDurationSec(perSample, "vorbis", 2),
          channels: 2,
          sampleRate: 48000,
          codec: "vorbis",
          loadType: /stream|music/i.test(b.name) ? "stream" : "memory",
          sizeBytes: perSample,
          bankId: b.name,
        });
        if (/stream|music/i.test(b.name)) b.streamIds.push(`fmod-${id}`);
        else b.assetIds.push(`fmod-${id}`);
      }
      if (count > 0) {
        events.push({ id: `ev-${b.name}`, name: `${b.name} events`, bankId: b.name, assetIds: b.assetIds });
      }
    }
  }

  const pluginsUsed = ["FMOD Core", "FMOD Studio"];
  return {
    engine: "fmod",
    name: path.basename(path.resolve(root)),
    assets,
    effects: [],
    buses,
    events,
    banks,
    pluginsUsed,
    metadata,
  };
}
