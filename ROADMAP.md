# Roadmap

AudioSure is alpha (v0.1.x). This document is the current plan, not a commitment — priorities shift with user feedback. Dates are deliberately omitted; ordering is the signal.

## Now → v0.2 (stabilize)

- **CI parity gate** — run TS and Python implementations on fixtures in CI and fail on any metric diff.
- **Test suite for the Python port** — unit tests for parsers (binary chunk edge cases), estimator determinism, scoring, and report serialization.
- **Real `.uasset` parsing (Unreal)** — replace best-effort name heuristics with actual property-table extraction for `SoundWave` / `SoundCue` assets.
- **Capture schema v1 freeze** — document the profiler capture format and validate it on load (`budget validate`-style command for captures).
- **Report schema stability** — publish a JSON schema for `CertificationReport`; dashboard validates on load.

## Next → v0.3 (depth)

- **Regression diffs** — `audiosure diff <old> <new>`: platform-by-platform metric deltas, new/fixed violations, recommendation churn. Wired into the run history the dashboard already lists.
- **Custom budget profiles as first-class objects** — named profiles (`budgets/mobile-lowend.json`) reusable across projects, shareable via the report index.
- **More capture sources** — importers for common device profilers (PlayStation tools, Xbox PIX audio sessions, Android `Oboe` traces, iOS AudioUnit counters) instead of hand-written capture JSON.
- **Wwise Media Explorer / EVGA parity** — parse `SoundBanksInfo` v150+ schemas fully; validate against real project dumps from multiple Wwise versions.
- **FMOD multi-platform banks** — per-platform bank folders with automatic platform mapping.

## Later → v0.4+ (scale)

- **Real cloud runner** — the current cloud runner is a local simulation (parallel platform audits). Plan: a worker service that pulls certified builds against a queue, with artifact storage for reports and captures. Studio tier gets priority queue.
- **REST API** — Studio tier: trigger audits, fetch reports, subscribe to regression events (webhooks).
- **Dashboard evolution** — historical trend charts per platform, recommendation tracking (accepted / dismissed / shipped), team seats and auth.
- **CI plugins** — GitHub Action and GitLab template that run `certify` on every build, comment on PRs with budget deltas, and fail the pipeline on regression.
- **Budget pack updates** — refresh platform budgets as new consoles/SDKs ship; version budget packs so old reports stay interpretable.
- **Audio-thread tracing** — ingest middleware frame traces (Wwise/FMOD profiling captures) to replace estimation for latency and voice-count metrics.

## Ideas under consideration

- Loudness / compliance checks (LUFS targets, true peak, platform certification for store requirements).
- Localization asset duplication analysis (per-language bank bloat).
- Interactive HTML report bundling captures and traces into a single shareable file.
- Plugin param linting (known-bad convolver/limiter configurations).
- Python/TS shared golden-report corpus as a published package for downstream consumers.

## Non-goals

- Running or instrumenting the game itself — AudioSure stays a static/capture-input tool.
- Replacing platform cert processes — AudioSure predicts budget compliance; it does not certify for Sony/Nintendo/Microsoft.
- DAW or asset-creation features.

## Contributing to the plan

Open an issue describing your engine, platform targets, and the metric you cannot currently trust. The most-requested capture importers and parser gaps move up the list fastest.
