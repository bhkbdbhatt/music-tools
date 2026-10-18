import { promises as fs } from "node:fs";
import path from "node:path";

export async function pathExists(p: string): Promise<boolean> {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

export async function walkFiles(
  root: string,
  match: (relPath: string, absPath: string) => boolean,
): Promise<string[]> {
  const out: string[] = [];
  async function rec(dir: string): Promise<void> {
    let entries;
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (e.name === "node_modules" || e.name === ".git") continue;
      const abs = path.join(dir, e.name);
      const rel = path.relative(root, abs);
      if (e.isDirectory()) {
        await rec(abs);
      } else if (e.isFile() && match(rel, abs)) {
        out.push(abs);
      }
    }
  }
  await rec(root);
  return out;
}

export async function fileSize(p: string): Promise<number> {
  const st = await fs.stat(p);
  return st.size;
}

export function guessDurationSec(sizeBytes: number, codec: string, channels: number): number {
  const bitrates: Record<string, number> = {
    vorbis: 96_000,
    opus: 64_000,
    mp3: 192_000,
    xma: 128_000,
    at9: 60_000,
    adpcm: 352_800,
    pcm: 48_000 * 16 * Math.max(1, channels),
    wem: 96_000,
    wav: 48_000 * 16 * Math.max(1, channels),
  };
  const bps = bitrates[codec.toLowerCase()] ?? 96_000;
  return Math.max(0.01, (sizeBytes * 8) / bps);
}

export function parseWavDuration(pcmBytes: number, sampleRate: number, channels: number, bitsPerSample: number): number {
  const bytesPerSec = sampleRate * channels * (bitsPerSample / 8);
  return bytesPerSec > 0 ? pcmBytes / bytesPerSec : 0;
}

export interface WavInfo {
  sampleRate: number;
  channels: number;
  bitsPerSample: number;
  dataBytes: number;
  durationSec: number;
}

export async function readWavInfo(p: string): Promise<WavInfo | null> {
  try {
    const buf = await fs.readFile(p);
    if (buf.length < 44 || buf.toString("ascii", 0, 4) !== "RIFF") return null;
    if (buf.toString("ascii", 8, 12) !== "WAVE") return null;
    let offset = 12;
    let sampleRate = 48000;
    let channels = 2;
    let bitsPerSample = 16;
    let dataBytes = 0;
    while (offset + 8 <= buf.length) {
      const chunkId = buf.toString("ascii", offset, offset + 4);
      const chunkSize = buf.readUInt32LE(offset + 4);
      const body = offset + 8;
      if (chunkId === "fmt ") {
        channels = buf.readUInt16LE(body + 2);
        sampleRate = buf.readUInt32LE(body + 4);
        bitsPerSample = buf.readUInt16LE(body + 14);
      } else if (chunkId === "data") {
        dataBytes = chunkSize;
        break;
      }
      offset = body + chunkSize + (chunkSize % 2);
    }
    return {
      sampleRate,
      channels,
      bitsPerSample,
      dataBytes,
      durationSec: parseWavDuration(dataBytes, sampleRate, channels, bitsPerSample),
    };
  } catch {
    return null;
  }
}

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
