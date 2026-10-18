# AudioSure

Cross-platform game audio certification: budgets, profiling, and fix reports for Wwise, FMOD, Unity, and Unreal projects.

AudioSure parses your game's audio data (bank files, engine assets, soundbanks info), estimates per-platform performance metrics (memory, latency, CPU, streaming bandwidth, battery), checks them against published platform budgets, and produces pass/fail certification reports with prioritized fix recommendations.

## Repository layout

This repo contains two implementations of the same tool:

| Path | What it is |
| --- | --- |
| `packages/` | TypeScript monorepo (pnpm workspaces): `core`, `parsers`, `engine`, `cli` |
| `apps/dashboard` | Next.js web dashboard that renders certification reports |
| `src/audiosure/` | Python package (stdlib-only) — pip-installable, same CLI and report format |
| `fixtures/` | Generated demo projects (Wwise, FMOD, Unity) used for tests and demos |
| `reports/` | Certification output (JSON / Markdown / HTML), gitignored |

The two implementations are kept in strict parity: given the same input and no `--noise`, they produce byte-identical report metrics.

## Quickstart (Python)

Requires Python 3.9+.

```console
$ pip install .
$ audiosure --help
```

Generate the demo projects and run a full certification:

```console
$ audiosure fixtures generate --out fixtures
$ audiosure certify --input fixtures/wwu-demo --platforms all
```

Output:

```
Summary: NOT CERTIFIED (FAIL)
  PASS  pc       score 100  0 fail / 0 warn
  PASS  ps5      score 100  0 fail / 0 warn
  PASS  xbox     score 100  0 fail / 0 warn
  FAIL  switch2  score  55  3 fail / 0 warn
  FAIL  mobile   score  40  4 fail / 0 warn
  FAIL  vr       score  70  2 fail / 0 warn

Recommendations: 10
  - Cut voice count, streaming bitrate, and convolution cost to reduce battery drain
  - Re-encode 320 in-memory clips (172.81MB) at lower bitrate to save ~51.84MB
  - ...
```

Reports are written to `reports/<id>.json`, `.md`, and `.html` (plus `latest.*`).

## Quickstart (TypeScript)

Requires Node 20+ and pnpm.

```console
$ pnpm install
$ pnpm build
$ pnpm certify:demo
```

## CLI

```
audiosure init [input]                    create .audiosure.json for a project
audiosure analyze <input> [--json]        parse a project and print the audio model
audiosure certify [input] [options]       run the certification pipeline, write reports
audiosure report <file|dir> [--format]    re-render a saved report (md|json|html)
audiosure budget show [platform]          inspect platform budgets
audiosure budget validate --file <json>   validate a budget override file
audiosure fixtures generate --out <dir>   generate demo projects
audiosure dash [--reports <dir>]          start the web dashboard
```

Useful `certify` options:

| Flag | Meaning |
| --- | --- |
| `--platforms all` or `pc,ps5,xbox,switch2,mobile,vr` | target platforms |
| `--engine wwise\|fmod\|unity\|unreal` | force engine detection |
| `--runner local\|cloud` | local audit or simulated cloud runner |
| `--tier starter\|pro\|studio` | entitlement tier (platform/build limits) |
| `--captures <json>` | override estimates with real profiler captures |
| `--seed N --noise` | deterministic run-to-run variance for realistic deltas |
| `--out <dir>` | report output directory (default `reports/`) |

## How it works

1. **Detect & parse** — engine-specific parsers read banks, streams, events, buses, effects, and mixer data into a common `ProjectModel`.
2. **Estimate** — platform profiles estimate metrics: in-memory size, streamed bandwidth, audio-thread latency, CPU/DSP load, peak voices, battery drain.
3. **Capture override** — optional real profiler captures (from device runs) replace estimated values with measured ones.
4. **Certify** — metrics are checked against per-platform budgets; each platform gets a score, pass/fail, and a list of violations (fail/warn severities).
5. **Recommend** — violations and model heuristics produce an ordered fix list with estimated savings (MB, kbps, ms).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design and [ROADMAP.md](ROADMAP.md) for what's planned next.

## Platform budgets

Default budgets ship per platform (PC, PS5, Xbox, Switch 2, mobile, VR). Override them per project:

```console
$ audiosure budget show switch2
$ audiosure budget validate --file my-budgets.json
```

```json
{
  "platforms": [
    { "platform": "switch2", "limits": { "memoryFootprintMB": { "max": 192 } } }
  ]
}
```

## License and contributing

Contributions are welcome — please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [SECURITY.md](SECURITY.md) first.
