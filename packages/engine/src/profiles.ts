import type { PlatformId } from "@audiosure/core";

export interface PlatformProfile {
  platform: PlatformId;
  displayName: string;
  baseLatencyMs: number;
  baseCpuPct: number;
  perVoiceCpuPct: number;
  perStreamCpuPct: number;
  perFxCpuPct: number;
  convCpuPct: number;
  convLatencyMs: number;
  convGpuPct: number;
  genericGpuPct: number;
  perVoiceMemKB: number;
  bankOverheadKB: number;
  streamBufferKB: number;
  convFftFactor: number;
  genericFxKB: number;
  streamSeekLatencyMs: number;
  voiceContentionMs: number;
  maxVoices: number;
  batteryBaseMw: number;
  batteryPerCpuMw: number;
  batteryPerKbpsMw: number;
  hasBattery: boolean;
}

const M = (v: number) => v;

export const PLATFORM_PROFILES: Record<PlatformId, PlatformProfile> = {
  pc: {
    platform: "pc",
    displayName: "PC",
    baseLatencyMs: M(12),
    baseCpuPct: 1.0,
    perVoiceCpuPct: 0.03,
    perStreamCpuPct: 0.1,
    perFxCpuPct: 0.12,
    convCpuPct: 1.2,
    convLatencyMs: 0.5,
    convGpuPct: 1.0,
    genericGpuPct: 0.2,
    perVoiceMemKB: 8,
    bankOverheadKB: 64,
    streamBufferKB: 256,
    convFftFactor: 2.0,
    genericFxKB: 48,
    streamSeekLatencyMs: 0.4,
    voiceContentionMs: 2.0,
    maxVoices: 128,
    batteryBaseMw: 0,
    batteryPerCpuMw: 0,
    batteryPerKbpsMw: 0,
    hasBattery: false,
  },
  ps5: {
    platform: "ps5",
    displayName: "PlayStation 5",
    baseLatencyMs: M(8),
    baseCpuPct: 0.6,
    perVoiceCpuPct: 0.02,
    perStreamCpuPct: 0.05,
    perFxCpuPct: 0.1,
    convCpuPct: 0.8,
    convLatencyMs: 0.3,
    convGpuPct: 0.5,
    genericGpuPct: 0.15,
    perVoiceMemKB: 8,
    bankOverheadKB: 48,
    streamBufferKB: 256,
    convFftFactor: 1.8,
    genericFxKB: 40,
    streamSeekLatencyMs: 0.3,
    voiceContentionMs: 1.5,
    maxVoices: 96,
    batteryBaseMw: 0,
    batteryPerCpuMw: 0,
    batteryPerKbpsMw: 0,
    hasBattery: false,
  },
  xbox: {
    platform: "xbox",
    displayName: "Xbox Series X|S",
    baseLatencyMs: M(9),
    baseCpuPct: 0.7,
    perVoiceCpuPct: 0.022,
    perStreamCpuPct: 0.06,
    perFxCpuPct: 0.1,
    convCpuPct: 0.9,
    convLatencyMs: 0.35,
    convGpuPct: 0.6,
    genericGpuPct: 0.15,
    perVoiceMemKB: 8,
    bankOverheadKB: 48,
    streamBufferKB: 256,
    convFftFactor: 1.8,
    genericFxKB: 40,
    streamSeekLatencyMs: 0.35,
    voiceContentionMs: 1.6,
    maxVoices: 96,
    batteryBaseMw: 0,
    batteryPerCpuMw: 0,
    batteryPerKbpsMw: 0,
    hasBattery: false,
  },
  switch2: {
    platform: "switch2",
    displayName: "Nintendo Switch 2",
    baseLatencyMs: M(14),
    baseCpuPct: 1.2,
    perVoiceCpuPct: 0.05,
    perStreamCpuPct: 0.2,
    perFxCpuPct: 0.2,
    convCpuPct: 2.5,
    convLatencyMs: 1.0,
    convGpuPct: 1.5,
    genericGpuPct: 0.35,
    perVoiceMemKB: 6,
    bankOverheadKB: 40,
    streamBufferKB: 128,
    convFftFactor: 2.2,
    genericFxKB: 32,
    streamSeekLatencyMs: 0.8,
    voiceContentionMs: 3.0,
    maxVoices: 64,
    batteryBaseMw: 0,
    batteryPerCpuMw: 0,
    batteryPerKbpsMw: 0,
    hasBattery: false,
  },
  mobile: {
    platform: "mobile",
    displayName: "Mobile",
    baseLatencyMs: M(11),
    baseCpuPct: 1.5,
    perVoiceCpuPct: 0.08,
    perStreamCpuPct: 0.25,
    perFxCpuPct: 0.3,
    convCpuPct: 3.5,
    convLatencyMs: 1.2,
    convGpuPct: 0.5,
    genericGpuPct: 0.3,
    perVoiceMemKB: 4,
    bankOverheadKB: 32,
    streamBufferKB: 96,
    convFftFactor: 2.5,
    genericFxKB: 24,
    streamSeekLatencyMs: 1.0,
    voiceContentionMs: 3.5,
    maxVoices: 48,
    batteryBaseMw: 60,
    batteryPerCpuMw: 6,
    batteryPerKbpsMw: 0.03,
    hasBattery: true,
  },
  vr: {
    platform: "vr",
    displayName: "VR Headset",
    baseLatencyMs: M(6),
    baseCpuPct: 1.0,
    perVoiceCpuPct: 0.05,
    perStreamCpuPct: 0.15,
    perFxCpuPct: 0.25,
    convCpuPct: 2.0,
    convLatencyMs: 0.4,
    convGpuPct: 1.0,
    genericGpuPct: 0.4,
    perVoiceMemKB: 6,
    bankOverheadKB: 48,
    streamBufferKB: 128,
    convFftFactor: 2.0,
    genericFxKB: 32,
    streamSeekLatencyMs: 0.5,
    voiceContentionMs: 2.0,
    maxVoices: 64,
    batteryBaseMw: 250,
    batteryPerCpuMw: 8,
    batteryPerKbpsMw: 0.05,
    hasBattery: true,
  },
};

export function getProfile(platform: PlatformId): PlatformProfile {
  return PLATFORM_PROFILES[platform];
}
