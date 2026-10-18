import type { MetricsSnapshot, PlatformId } from "@audiosure/core";

export interface ProfilerCapture {
  platform: PlatformId;
  capturedAt?: string;
  source?: string;
  metrics: Partial<Omit<MetricsSnapshot, "platform">>;
}

export interface CaptureFile {
  $schema?: string;
  captures: ProfilerCapture[];
}

export function applyCaptures(
  estimated: MetricsSnapshot,
  captures: ProfilerCapture[],
): { metrics: MetricsSnapshot; source: "estimate" | "capture"; capturedKeys: string[] } {
  const match = captures.find((c) => c.platform === estimated.platform);
  if (!match) return { metrics: estimated, source: "estimate", capturedKeys: [] };
  const capturedKeys = Object.keys(match.metrics);
  const merged: MetricsSnapshot = { ...estimated };
  for (const [k, v] of Object.entries(match.metrics)) {
    if (typeof v === "number") {
      (merged as unknown as Record<string, number>)[k] = v;
    }
  }
  return { metrics: merged, source: "capture", capturedKeys };
}
