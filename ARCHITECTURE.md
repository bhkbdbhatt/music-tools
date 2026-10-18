# Architecture

AudioSure is a static-analysis and estimation tool for game audio. It never runs your game; it reads the audio artifacts you ship (bank files, engine assets, soundbanks info exports) and estimates how they behave on each target platform, optionally corrected by real profiler captures.

## Design goals

- **Deterministic** — same input, same report. Variance is opt-in (`--seed`, `--noise`).
- **Engine-agnostic core** — Wwise, FMOD, Unity, and Unreal parsers all produce one shared `ProjectModel`.
- **Budget-driven certification** — pass/fail is a pure function of (metrics, budgets), not of heuristics.
- **Report format is an API** — the JSON report feeds the web dashboard and CI gates; it is versioned by shape, not by tool version.
- **Zero-dependency runtime (Python port)** — the Python package uses only the standard library, so it installs anywhere.

## Pipeline

```
project files                     ProjectModel
─────────────                    ────────────────
detect_engine() ──► parse_project()
                         │
                         ▼
              estimate_metrics(model, platform)
                         │
       profiler captures ▼ (optional override)
                   apply_captures()
                         │
                         ▼
        build_platform_certification(budget, metrics)
                         │  per platform: score, pass, violations
                         ▼
              recommend_fixes(model, certs)
                         │
                         ▼
                  build_report()  ──►  JSON / MD / HTML
```

Implemented in `engine/pipeline.py::run_audit` (Python) and `packages/engine` (TS). The CLI wraps this with tier gates, usage accounting, and report persistence.

## Package layout (both implementations)

| Module | Responsibility |
| --- | --- |
| `core/types` | Shared data model: `ProjectModel`, `AssetInfo`, `BankInfo`, `EffectModel`, `MetricsSnapshot`, `PlatformBudget`, `CertificationReport`. Serialization helpers (`camelize` / `to_jsonable`). |
| `core/budgets` | Default platform budgets and merge logic for overrides. |
| `core/tiers` | Pricing tiers and entitlement gates (platform count, builds/month). |
| `core/report` | Budget evaluation, scoring, report assembly and reload. |
| `parsers/` | Engine detection and per-engine parsers (see below). |
| `engine/profiles` | Per-platform model parameters (voice caps, sample rates, compression assumptions). |
| `engine/estimator` | Metrics estimation from the model + platform profile. |
| `engine/captures` | Profiler capture schema and override application. |
| `engine/recommender` | Ordered fix recommendations with estimated savings. |
| `engine/pipeline` | Orchestration of the audit. |
| `engine/runners` | Local runner and simulated cloud runner (parallel platform audits). |
| `cli/` (Py) / `packages/cli` (TS) | Argument parsing, config, report storage, reporters, fixtures, dashboard launcher. |

## Parsers

Engine detection walks the input path looking for known markers:

| Engine | Markers |
| --- | --- |
| Wwise | `.bnk`, `.wwu`, `SoundBanksInfo.xml` |
| FMOD Studio | `.bank`, `metadata/*.xml`, `audio-export.xml` |
| Unity | `.wav/.ogg` + `.meta`, `.mixer`, scene `AudioSource` refs |
| Unreal | `.uasset` naming conventions, `SoundWave`-style assets |

Each parser fills the same `ProjectModel`: assets (with load type, size, duration, codec, channels), banks, events, buses, effects (with plugin params), and plugins used.

Notable parser details:

- **Wwise** reads `BKHD`/`DIDX`/`DATA`/`HIRC` chunks, resolves streamed media from `SoundBanksInfo` (XML or JSON), and parses `.wwu` work units for buses, effects, and convolution IR parameters (`uIRDurationSec`).
- **FMOD** reads FSB5 container headers (sample count, data size, codec mode) and the Studio XML export for buses, events, and load types.
- **Unity** reads WAV headers (including deliberately mismatched declared sizes), `AudioImporter` meta (load type, compression), mixer groups, and scene `AudioSource` references.
- **Unreal** is best-effort from file naming and metadata; real `.uasset` parsing is on the roadmap.

## Estimation

For each platform, the estimator walks assets and effects and accumulates:

| Metric | Basis |
| --- | --- |
| `memoryFootprintMB` | in-memory assets (decoded or compressed) + bank memory + effect working buffers (e.g. convolution IR + FFT) |
| `inMemoryMB` / `streamedMB` | split of media by load type |
| `streamedBandwidthKbps` | stream sizes vs duration |
| `audioThreadLatencyMs` | voice count, effect chain cost, platform voice caps |
| `cpuAudioPct` / `gpuDspPct` | per-asset and per-effect cost model against platform CPU/DSP share |
| `peakConcurrentVoices` | event graph and mixer fan-out |
| `batteryDrainMw` | weighted combination of voices, DSP, streaming I/O (mobile/VR) |

Platform profiles supply the constants (voice limits, sample rate assumptions, compression round-trip factors).

`--seed N` seeds a deterministic PRNG; `--noise` applies bounded per-metric jitter so successive runs of a changing project look realistic without losing reproducibility.

## Captures

Estimates are useful for early budgets; real numbers come from device profilers. The captures file maps measured values into the pipeline:

```json
{
  "captures": [
    {
      "platform": "ps5",
      "metrics": { "memoryFootprintMB": 172.4, "audioThreadLatencyMs": 14.2 },
      "source": "playstation-telemetry-2026-09"
    }
  ]
}
```

Captures override estimates metric-by-metric; anything not captured stays estimated. The report records which values were measured.

## Certification

`build_platform_certification(platform, budget, metrics)` evaluates every budget limit:

- value > max (or < min) → **fail** violation
- value within `warn_ratio` of a limit (default 0.75–0.85 per metric) → **warn** violation
- platform passes iff it has zero fails; score is a weighted deduction from 100
- project passes iff every requested platform passes

Severity ordering and scoring are shared between implementations — they must never diverge.

## Recommendations

`recommend_fixes` runs rules against the model + violations, each producing a `FixRecommendation` with title, detail, effort, target platforms, and estimated savings (MB / kbps / ms). Rules are ordered by priority; representative rules:

- cut voice count / streaming bitrate / convolution cost when battery or CPU budgets fail
- re-encode in-memory clips at lower bitrate when memory budgets fail
- shorten convolution IRs that exceed the target duration
- switch short streamed SFX to in-memory (and vice versa for long low-priority assets)

## Report format

`CertificationReport` is the contract with the dashboard and CI:

```json
{
  "id": "…",
  "createdAt": "…",
  "tier": "pro",
  "overallPass": false,
  "project": { "name": "…", "engine": "wwise" },
  "runner": { "name": "local-runner", "durationMs": 12 },
  "summary": { "passedPlatforms": 3, "totalPlatforms": 6, "totalFail": 9, "totalWarn": 0 },
  "platforms": [
    {
      "platform": "mobile",
      "passed": false,
      "score": 40,
      "metrics": { "memoryFootprintMB": 181.04, "audioThreadLatencyMs": 24.0, "…": 0 },
      "violations": [
        { "platform": "mobile", "metric": "memoryFootprintMB", "severity": "fail", "actual": 181.04, "budget": 150, "unit": "MB", "message": "…" }
      ]
    }
  ],
  "recommendations": [
    { "id": "rec-…", "ruleId": "…", "title": "…", "detail": "…", "effort": "low", "platformTargets": ["mobile"], "estimatedSavingsMB": 51.84 }
  ]
}
```

JSON keys are camelCase; each certify run writes `<id>.{json,md,html}` plus `latest.*` and an `index.json` run history in the output directory.

## CLI architecture (Python)

- `cli/main.py` — argparse subcommand tree; `main()` returns an exit code (0 pass, 1 fail, 2 usage, 3 tier gate, 4 audit error).
- `cli/commands.py` — command implementations; tier gates and monthly usage accounting (`cli/usage.py`) run before audits.
- `cli/store.py` — report persistence and run index.
- `cli/reporters.py` — JSON/Markdown/HTML renderers (HTML is a self-contained dark-theme page).
- `cli/fixtures.py` — binary generators (WAV, Wwise BNK, FMOD FSB5) for demo projects.
- `cli/config.py` — `.audiosure.json` project config.

## Parity between implementations

The Python port is verified against the TS implementation by running both on the generated fixtures and diffing `latest.json` metric-for-metric. Conventions that make this work:

- JS-style half-up rounding (`js_round`) wherever TS used `Math.round`
- integer-valued floats render as integers (`2s`, not `2.0s`) to match JS number stringification
- `None`/`null` fields are omitted from JSON to match `JSON.stringify`
- dictionary keys (params, metadata, metrics) stay snake_case in model dumps but metric names in report payloads are camelCase via field overrides

Parity diffs belong in CI: any change to estimation, scoring, or recommendation output must land in both implementations together.
