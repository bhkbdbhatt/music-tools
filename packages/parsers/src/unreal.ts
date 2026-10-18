import { promises as fs } from "node:fs";
import path from "node:path";
import type {
  AudioAsset,
  AudioBus,
  AudioEffect,
  AudioEvent,
  BankInfo,
  LoadType,
  ProjectModel,
} from "@audiosure/core";
import { guessDurationSec, walkFiles } from "./util.js";

interface UnrealInventory {
  project?: string;
  soundWaves?: Array<{
    name: string;
    path?: string;
    durationSec?: number;
    channels?: number;
    sampleRate?: number;
    loadingBehavior?: string;
    compression?: string;
    sizeBytes?: number;
    looping?: boolean;
    isMusic?: boolean;
  }>;
  soundCues?: Array<{ name: string; soundWaveNames?: string[]; maxConcurrentInstances?: number }>;
  audioMixer?: {
    submixes?: string[];
    effects?: Array<{ name: string; plugin?: string; params?: Record<string, number | string> }>;
  };
}

function mapLoadingBehavior(v: string | undefined): LoadType {
  if (!v) return "memory";
  const s = v.toLowerCase();
  if (s.includes("stream")) return "stream";
  if (s.includes("preload")) return "preload";
  return "memory";
}

const NUM_RE = /(-?\d+(?:\.\d+)?)/;

export async function parseUnreal(root: string): Promise<ProjectModel> {
  const inventoryPath = (await walkFiles(root, (rel) => /AudioInventory\.json$/i.test(rel)))[0];
  const metadata: Record<string, unknown> = { inventoryFound: !!inventoryPath };

  if (!inventoryPath) {
    return {
      engine: "unreal",
      name: path.basename(path.resolve(root)),
      assets: [],
      effects: [],
      buses: [],
      events: [],
      banks: [],
      pluginsUsed: ["Unreal Audio Engine"],
      metadata: { ...metadata, hint: "Export AudioInventory.json from the Unreal editor (see docs/UNREAL.md)." },
    };
  }

  const inv = JSON.parse(await fs.readFile(inventoryPath, "utf8")) as UnrealInventory;
  const assets: AudioAsset[] = [];
  const nameToId = new Map<string, string>();

  for (const sw of inv.soundWaves ?? []) {
    const id = `unreal-${sw.name}`;
    nameToId.set(sw.name, id);
    const sizeBytes = sw.sizeBytes ?? 0;
    const channels = sw.channels ?? 2;
    const codec = (sw.compression ?? "vorbis").toLowerCase();
    const duration = sw.durationSec && sw.durationSec > 0 ? sw.durationSec : guessDurationSec(sizeBytes, codec, channels);
    assets.push({
      id,
      name: sw.name,
      path: sw.path,
      durationSec: duration,
      channels,
      sampleRate: sw.sampleRate ?? 48000,
      codec,
      loadType: mapLoadingBehavior(sw.loadingBehavior),
      sizeBytes,
      decodeInMemory: (sw.loadingBehavior ?? "").toLowerCase().includes("forceinline"),
      isMusic: sw.isMusic ?? /music|bgm|theme|ambient/i.test(sw.name),
      isSfx: !/music|bgm|theme/i.test(sw.name),
      bankId: "UnrealAssets",
    });
  }

  const events: AudioEvent[] = (inv.soundCues ?? []).map((cue) => ({
    id: `cue-${cue.name}`,
    name: cue.name,
    bankId: "UnrealAssets",
    assetIds: (cue.soundWaveNames ?? []).map((n) => nameToId.get(n) ?? `unreal-${n}`),
    maxInstances: cue.maxConcurrentInstances,
  }));

  const effects: AudioEffect[] = [];
  const buses: AudioBus[] = [];
  const mixer = inv.audioMixer;
  if (mixer) {
    (mixer.submixes ?? []).forEach((name, i) => buses.push({ id: `submix-${i}`, name, effectIds: [] }));
    (mixer.effects ?? []).forEach((fx, i) => {
      const params = { ...(fx.params ?? {}) };
      const plugin = fx.plugin ?? fx.name;
      if (/convol/i.test(plugin)) {
        for (const [k, v] of Object.entries(params)) {
          const m = String(v).match(NUM_RE);
          if (/ir|impulse|duration|length/i.test(k) && m) params["irDurationSec"] = Number(m[1]);
        }
      }
      effects.push({ id: `ue-fx-${i}`, name: fx.name, plugin, params });
    });
  }

  const banks: BankInfo[] = [
    {
      id: "UnrealAssets",
      name: "UnrealAssets",
      sizeBytes: assets.reduce((n, a) => n + a.sizeBytes, 0),
      memoryBytes: assets.filter((a) => a.loadType !== "stream").reduce((n, a) => n + a.sizeBytes, 0),
      streamIds: assets.filter((a) => a.loadType === "stream").map((a) => a.id),
      assetIds: assets.filter((a) => a.loadType !== "stream").map((a) => a.id),
    },
  ];

  return {
    engine: "unreal",
    name: inv.project ?? path.basename(path.resolve(root)),
    assets,
    effects,
    buses,
    events,
    banks,
    pluginsUsed: [...new Set(effects.map((e) => e.plugin))],
    metadata,
  };
}
