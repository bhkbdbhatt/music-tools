import { promises as fs } from "node:fs";
import path from "node:path";
import type { AudioAsset, AudioBus, AudioEffect, AudioEvent, BankInfo, ProjectModel } from "@audiosure/core";
import { attrNum, attrStr, findAll, findAllWhere, parseXml, type XmlNode } from "./xml.js";
import { fileSize, guessDurationSec, pathExists, readWavInfo, walkFiles } from "./util.js";

interface StreamedFileInfo {
  id: string;
  name: string;
  path?: string;
  language?: string;
  bankShortName?: string;
}

interface BankXmlInfo {
  id: string;
  shortName: string;
  name?: string;
  path?: string;
  language?: string;
  memoryBytes?: number;
  sizeBytes?: number;
  streamIds: string[];
  eventIds: string[];
}

interface BnkSection {
  id: string;
  size: number;
  payloadOffset: number;
}

interface DidxEntry {
  sourceId: number;
  fileOffset: number;
  fileLength: number;
}

function readSections(buf: Buffer): BnkSection[] {
  const sections: BnkSection[] = [];
  let off = 0;
  while (off + 8 <= buf.length) {
    const id = buf.toString("ascii", off, off + 4);
    if (!/^[A-Z0-9]{4}$/.test(id)) break;
    const size = buf.readUInt32LE(off + 4);
    sections.push({ id, size, payloadOffset: off + 8 });
    off += 8 + size;
    if (size === 0 && id === "DATA") break;
  }
  return sections;
}

function readDidx(buf: Buffer, section: BnkSection): DidxEntry[] {
  const entries: DidxEntry[] = [];
  const count = Math.floor(section.size / 12);
  for (let i = 0; i < count; i++) {
    const o = section.payloadOffset + i * 12;
    if (o + 12 > buf.length) break;
    entries.push({
      sourceId: buf.readUInt32LE(o),
      fileOffset: buf.readUInt32LE(o + 4),
      fileLength: buf.readUInt32LE(o + 8),
    });
  }
  return entries;
}

function readHircCount(buf: Buffer, section: BnkSection): number {
  if (section.payloadOffset + 4 > buf.length) return 0;
  return buf.readUInt32LE(section.payloadOffset);
}

function firstNumAttr(n: XmlNode, names: string[]): number | undefined {
  for (const name of names) {
    const v = attrNum(n, name);
    if (v !== undefined) return v;
  }
  return undefined;
}

function parseSoundBanksInfoXml(xml: string): { banks: BankXmlInfo[]; streams: StreamedFileInfo[] } {
  const root = parseXml(xml);
  const banks: BankXmlInfo[] = [];
  const streams: StreamedFileInfo[] = [];

  for (const sf of findAllWhere(root, (n) => n.tag === "StreamedFile" && (attrStr(n, "Path") !== undefined || attrStr(n, "Name") !== undefined))) {
    const id = attrStr(sf, "Id") ?? attrStr(sf, "ID");
    if (!id) continue;
    streams.push({
      id,
      name: attrStr(sf, "Name") ?? attrStr(sf, "ShortName") ?? id,
      path: attrStr(sf, "Path"),
      language: attrStr(sf, "Language"),
      bankShortName: attrStr(sf, "SoundBankShortName") ?? attrStr(sf, "BankShortName"),
    });
  }

  for (const sb of findAll(root, "SoundBank")) {
    const shortName = attrStr(sb, "ShortName") ?? attrStr(sb, "Name") ?? "Unknown";
    const id = attrStr(sb, "Id") ?? attrStr(sb, "ID") ?? shortName;
    const streamIds: string[] = [];
    const eventIds: string[] = [];
    for (const sfl of findAll(sb, "StreamedFile")) {
      const sid = attrStr(sfl, "Id") ?? attrStr(sfl, "ID");
      if (sid) streamIds.push(sid);
    }
    for (const ev of findAll(sb, "Event")) {
      const eid = attrStr(ev, "Id") ?? attrStr(ev, "ID") ?? attrStr(ev, "Name");
      if (eid) eventIds.push(eid);
    }
    banks.push({
      id,
      shortName,
      name: attrStr(sb, "Name") ?? attrStr(sb, "FileName"),
      path: attrStr(sb, "Path"),
      language: attrStr(sb, "Language"),
      memoryBytes: firstNumAttr(sb, ["MemoryBytes", "Memory", "BankMemory"]),
      sizeBytes: firstNumAttr(sb, ["SizeBytes", "Size", "BankSize"]),
      streamIds,
      eventIds,
    });
  }
  return { banks, streams };
}

function parseSoundBanksInfoJson(raw: string): { banks: BankXmlInfo[]; streams: StreamedFileInfo[] } {
  const data = JSON.parse(raw) as Record<string, unknown>;
  const info =
    (data["SoundbanksInfo"] as Record<string, unknown>) ??
    (data["SoundBanksInfo"] as Record<string, unknown>) ??
    data;
  const banksRaw = (info["SoundBanks"] ?? info["soundBanks"] ?? []) as Record<string, unknown>[];
  const streamsRaw = (info["StreamedFiles"] ?? info["streamedFiles"] ?? []) as Record<string, unknown>[];

  const streams: StreamedFileInfo[] = streamsRaw.map((s) => ({
    id: String(s["Id"] ?? s["ID"] ?? s["id"] ?? ""),
    name: String(s["Name"] ?? s["name"] ?? s["ShortName"] ?? ""),
    path: s["Path"] ? String(s["Path"]) : s["path"] ? String(s["path"]) : undefined,
    language: s["Language"] ? String(s["Language"]) : undefined,
    bankShortName: s["SoundBankShortName"] ? String(s["SoundBankShortName"]) : undefined,
  }));

  const banks: BankXmlInfo[] = banksRaw.map((b) => ({
    id: String(b["Id"] ?? b["ID"] ?? b["ShortName"] ?? ""),
    shortName: String(b["ShortName"] ?? b["shortName"] ?? b["Name"] ?? "Unknown"),
    name: b["Name"] ? String(b["Name"]) : undefined,
    path: b["Path"] ? String(b["Path"]) : undefined,
    language: b["Language"] ? String(b["Language"]) : undefined,
    memoryBytes: typeof b["MemoryBytes"] === "number" ? b["MemoryBytes"] : typeof b["MemoryBits"] === "number" ? Math.ceil(Number(b["MemoryBits"]) / 8) : undefined,
    sizeBytes: typeof b["SizeBytes"] === "number" ? b["SizeBytes"] : undefined,
    streamIds: ((b["StreamedFiles"] ?? []) as Record<string, unknown>[]).map((s) => String(s["Id"] ?? s["ID"] ?? "")),
    eventIds: ((b["Events"] ?? []) as Record<string, unknown>[]).map((e) => String(e["Id"] ?? e["Name"] ?? "")),
  }));
  return { banks, streams };
}

function extractFxParams(fxNode: XmlNode): Record<string, number | string> {
  const params: Record<string, number | string> = {};
  for (const p of findAllWhere(fxNode, (n) => n.tag === "Property" || n.tag === "Param" || n.tag === "FXProperty")) {
    const name = attrStr(p, "Name") ?? attrStr(p, "key") ?? p.children.find((c) => c.tag === "Name")?.text.trim();
    if (!name) continue;
    const valAttr = attrStr(p, "Value") ?? attrStr(p, "value");
    const valChild = p.children.find((c) => c.tag === "Value")?.text.trim();
    const raw = valAttr ?? valChild ?? p.text.trim();
    if (!raw) continue;
    const num = Number(raw);
    params[name] = Number.isNaN(num) ? raw : num;
  }
  return params;
}

function parseWwuEffects(xml: string): { effects: AudioEffect[]; buses: AudioBus[]; events: AudioEvent[] } {
  const root = parseXml(xml);
  const effects: AudioEffect[] = [];
  const buses: AudioBus[] = [];
  const events: AudioEvent[] = [];

  const fxNodes = findAllWhere(
    root,
    (n) =>
      (n.tag === "Fx" || n.tag === "Effect" || n.tag === "FxRef" || n.tag === "EffectBase") &&
      (attrStr(n, "Plugin") !== undefined || n.children.some((c) => c.tag === "PluginName" || c.tag === "Plugin")),
  );
  for (const [i, fx] of fxNodes.entries()) {
    const plugin =
      attrStr(fx, "Plugin") ??
      fx.children.find((c) => c.tag === "PluginName" || c.tag === "Plugin")?.text.trim() ??
      "Unknown";
    const name = attrStr(fx, "Name") ?? fx.children.find((c) => c.tag === "Name")?.text.trim() ?? plugin;
    const params = extractFxParams(fx);
    const normalized: Record<string, number | string> = { ...params };
    for (const [k, v] of Object.entries(params)) {
      if (/ir.*duration|impulse.*len|convolution.*sec/i.test(k) && typeof v === "number") {
        normalized["irDurationSec"] = v;
      }
    }
    if (/convolution/i.test(plugin) && normalized["irDurationSec"] === undefined) {
      const guessKey = Object.keys(params).find((k) => /duration|length|sec/i.test(k));
      if (guessKey && typeof params[guessKey] === "number") {
        normalized["irDurationSec"] = params[guessKey];
      }
    }
    effects.push({ id: `fx-wwu-${i}`, name, plugin, params: normalized });
  }

  const busNodes = findAllWhere(root, (n) => n.tag === "Bus" || n.tag === "AuxBus");
  for (const [i, b] of busNodes.entries()) {
    const name = attrStr(b, "Name") ?? b.children.find((c) => c.tag === "Name")?.text.trim() ?? `Bus${i}`;
    const effectIds: string[] = [];
    for (const fx of findAll(b, "Fx")) {
      const plugin = attrStr(fx, "Plugin") ?? fx.children.find((c) => c.tag === "PluginName")?.text.trim();
      if (plugin) {
        const match = effects.find((e) => e.plugin === plugin);
        if (match) effectIds.push(match.id);
      }
    }
    buses.push({ id: `bus-wwu-${i}`, name, effectIds });
  }

  const eventNodes = findAllWhere(root, (n) => n.tag === "Event" && (attrStr(n, "Name") !== undefined || n.children.some((c) => c.tag === "Name")));
  for (const [i, e] of eventNodes.entries()) {
    const name = attrStr(e, "Name") ?? e.children.find((c) => c.tag === "Name")?.text.trim() ?? `Event${i}`;
    events.push({ id: attrStr(e, "Id") ?? `evt-wwu-${i}`, name, assetIds: [] });
  }

  return { effects, buses, events };
}

export async function parseWwise(root: string): Promise<ProjectModel> {
  const banks: BankInfo[] = [];
  const assets: AudioAsset[] = [];
  const effects: AudioEffect[] = [];
  const buses: AudioBus[] = [];
  const events: AudioEvent[] = [];
  const plugins = new Set<string>();
  const metadata: Record<string, unknown> = { missingStreamedFiles: [] as string[] };

  let info: { banks: BankXmlInfo[]; streams: StreamedFileInfo[] } = { banks: [], streams: [] };
  const jsonInfo = (await walkFiles(root, (rel) => /SoundBanksInfo\.json$/i.test(rel)))[0];
  const xmlInfo = (await walkFiles(root, (rel) => /SoundBanksInfo\.xml$/i.test(rel)))[0];
  if (jsonInfo) {
    info = parseSoundBanksInfoJson(await fs.readFile(jsonInfo, "utf8"));
    metadata["soundbanksInfoSource"] = path.relative(root, jsonInfo);
  } else if (xmlInfo) {
    info = parseSoundBanksInfoXml(await fs.readFile(xmlInfo, "utf8"));
    metadata["soundbanksInfoSource"] = path.relative(root, xmlInfo);
  }

  const bnkFiles = await walkFiles(root, (rel) => /\.bnk$/i.test(rel));
  const bnkByShort = new Map<string, { memoryBytes: number; sizeBytes: number; didxCount: number; hircCount: number; didxBytes: number }>();

  for (const bnk of bnkFiles) {
    const buf = await fs.readFile(bnk);
    const sections = readSections(buf);
    let didxBytes = 0;
    let didxCount = 0;
    let hircCount = 0;
    const didxSection = sections.find((s) => s.id === "DIDX");
    const hircSection = sections.find((s) => s.id === "HIRC");
    if (didxSection) {
      const entries = readDidx(buf, didxSection);
      didxCount = entries.length;
      didxBytes = entries.reduce((n, e) => n + e.fileLength, 0);
      for (const [idx, entry] of entries.entries()) {
        assets.push({
          id: `wem-${entry.sourceId}`,
          name: `${path.basename(bnk, ".bnk")}-media-${idx}`,
          durationSec: 0,
          channels: 2,
          sampleRate: 48000,
          codec: "wem",
          loadType: "memory",
          sizeBytes: entry.fileLength,
          isSfx: true,
          bankId: path.basename(bnk, ".bnk"),
        });
      }
    }
    if (hircSection) hircCount = readHircCount(buf, hircSection);
    bnkByShort.set(path.basename(bnk, ".bnk"), {
      memoryBytes: didxBytes,
      sizeBytes: buf.length,
      didxCount,
      hircCount,
      didxBytes,
    });
  }

  const streamById = new Map(info.streams.map((s) => [s.id, s]));
  const missing = metadata["missingStreamedFiles"] as string[];

  for (const s of info.streams) {
    let size = 0;
    let duration = 0;
    let channels = 2;
    let sampleRate = 48000;
    const candidates = s.path
      ? [path.resolve(root, s.path), path.resolve(root, "audio", path.basename(s.path)), path.resolve(root, "..", s.path)]
      : [];
    let found: string | null = null;
    for (const c of candidates) {
      if (await pathExists(c)) {
        found = c;
        break;
      }
    }
    if (found) {
      size = await fileSize(found);
      if (/\.wav$/i.test(found)) {
        const wav = await readWavInfo(found);
        if (wav) {
          duration = wav.durationSec;
          channels = wav.channels;
          sampleRate = wav.sampleRate;
        }
      } else {
        duration = guessDurationSec(size, "wem", channels);
      }
    } else {
      missing.push(s.name);
    }
    const isMusic = /music|bgm|theme/i.test(s.name);
    assets.push({
      id: `stream-${s.id}`,
      name: s.name,
      path: s.path,
      durationSec: duration,
      channels,
      sampleRate,
      codec: "wem",
      loadType: "stream",
      sizeBytes: size,
      isMusic,
      isSfx: !isMusic,
      language: s.language,
      bankId: s.bankShortName,
    });
  }

  for (const b of info.banks) {
    const bnkData = bnkByShort.get(b.shortName);
    const streamIds = b.streamIds.map((id) => `stream-${id}`);
    const assetIds = assets.filter((a) => a.bankId === b.shortName).map((a) => a.id);
    banks.push({
      id: b.id,
      name: b.shortName,
      sizeBytes: b.sizeBytes ?? bnkData?.sizeBytes ?? 0,
      memoryBytes: b.memoryBytes ?? bnkData?.memoryBytes ?? 0,
      streamIds,
      assetIds,
      language: b.language,
    });
  }

  for (const [name, data] of bnkByShort) {
    if (!banks.some((b) => b.name === name)) {
      banks.push({
        id: name,
        name,
        sizeBytes: data.sizeBytes,
        memoryBytes: data.didxBytes,
        streamIds: [],
        assetIds: assets.filter((a) => a.bankId === name).map((a) => a.id),
      });
    }
  }

  const wwuFiles = await walkFiles(root, (rel) => /\.wwu$/i.test(rel));
  for (const wwu of wwuFiles) {
    const xml = await fs.readFile(wwu, "utf8");
    const parsed = parseWwuEffects(xml);
    effects.push(...parsed.effects);
    buses.push(...parsed.buses);
    events.push(...parsed.events);
    for (const fx of parsed.effects) {
      plugins.add(fx.plugin);
    }
  }

  for (const bank of info.banks) {
    for (const eid of bank.eventIds) {
      const streamAssetIds = bank.streamIds.map((id) => `stream-${id}`);
      if (!events.some((e) => e.id === eid)) {
        events.push({ id: eid, name: eid, bankId: bank.shortName, assetIds: streamAssetIds });
      }
    }
  }

  return {
    engine: "wwise",
    name: path.basename(path.resolve(root)),
    assets,
    effects,
    buses,
    events,
    banks,
    pluginsUsed: [...plugins],
    metadata,
  };
}
