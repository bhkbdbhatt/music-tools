from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

from audiosure.cli.config import default_config, load_config, parse_platforms, resolve_tier, save_config
from audiosure.cli.fixtures import generate_all_fixtures
from audiosure.cli.reporters import render_html, render_json, render_markdown
from audiosure.cli.store import load_report, save_report
from audiosure.cli.usage import builds_this_month, record_build
from audiosure.core.budgets import DEFAULT_BUDGETS, merge_budgets
from audiosure.core.tiers import check_build_limit, check_platform_limit, get_tier
from audiosure.core.types import PLATFORM_IDS, MetricLimit, PlatformBudget, ProjectModel, to_jsonable
from audiosure.engine.captures import ProfilerCapture, capture_from_dict
from audiosure.engine.pipeline import AuditOptions, AuditResult
from audiosure.engine.runners import CloudRunnerSim, LocalRunner
from audiosure.parsers.detect import detect_engine, parse_project

DEFAULT_OUT = "reports"


@dataclass
class CertifyOptions:
    input: Optional[str] = None
    engine: Optional[str] = None
    platforms: Optional[str] = None
    runner: Optional[str] = None
    tier: Optional[str] = None
    out: Optional[str] = None
    seed: Optional[int] = None
    noise: bool = False
    captures: Optional[str] = None
    quiet: bool = False


def _rel(path: str, start: str) -> str:
    try:
        return os.path.relpath(path, start)
    except ValueError:
        return path


def cmd_init(cwd: str, input_path: str = ".") -> int:
    engine = detect_engine(os.path.abspath(os.path.join(cwd, input_path)))
    config = default_config()
    config.project.input = input_path
    config.project.engine = engine
    config.project.name = os.path.basename(os.path.abspath(os.path.join(cwd, input_path)))
    p = save_config(cwd, config)
    print(f"Wrote {os.path.relpath(p, cwd)}")
    print(f"  input:     {config.project.input}")
    print(f"  engine:    {engine or '(auto-detect)'}")
    print(f"  platforms: {', '.join(config.platforms)}")
    print(f"  tier:      {config.tier}")
    print("\nNext: audiosure certify")
    return 0


def cmd_analyze(input_path: str, engine: Optional[str], as_json: bool) -> int:
    model = parse_project(input_path, engine)
    if as_json:
        print(json.dumps(to_jsonable(model), indent=2))
        return 0
    _print_model(model)
    return 0


def _print_model(model: ProjectModel) -> None:
    in_memory = [a for a in model.assets if a.load_type != "stream"]
    streamed = [a for a in model.assets if a.load_type == "stream"]
    print(f"Engine:     {model.engine}")
    print(f"Project:    {model.name}")
    print(f"Assets:     {len(model.assets)} ({len(in_memory)} in-memory, {len(streamed)} streamed)")
    print(f"Banks:      {len(model.banks)}")
    print(f"Events:     {len(model.events)}")
    print(f"Effects:    {len(model.effects)}")
    print(f"Plugins:    {', '.join(model.plugins_used) or '(none)'}")
    print(f"Metadata:   {json.dumps(model.metadata)}")
    if model.effects:
        print("\nEffects:")
        for fx in model.effects:
            print(f"  - {fx.name} [{fx.plugin}] {json.dumps(fx.params)}")


def cmd_certify(cwd: str, opts: CertifyOptions) -> int:
    config = load_config(cwd)
    input_path = opts.input or (config.project.input if config else None)
    if not input_path:
        print("No input project. Pass a path or run `audiosure init`.", file=sys.stderr)
        return 2
    tier = resolve_tier(opts.tier or (config.tier if config else None))
    if opts.platforms:
        platforms = parse_platforms(opts.platforms)
    elif config and config.platforms:
        platforms = parse_platforms(",".join(config.platforms))
    else:
        platforms = parse_platforms("all")
    engine = opts.engine or (config.project.engine if config else None)
    out = os.path.abspath(os.path.join(cwd, opts.out or DEFAULT_OUT))

    platform_gate = check_platform_limit(tier, len(platforms))
    if not platform_gate.allowed:
        print(f"Tier limit: {platform_gate.reason}", file=sys.stderr)
        return 3
    used = builds_this_month(cwd)
    build_gate = check_build_limit(tier, used)
    if not build_gate.allowed:
        print(f"Tier limit: {build_gate.reason}", file=sys.stderr)
        return 3

    captures: Optional[List[ProfilerCapture]] = None
    if opts.captures:
        with open(os.path.abspath(os.path.join(cwd, opts.captures)), "r", encoding="utf-8") as f:
            parsed = json.load(f)
        raw_list = parsed if isinstance(parsed, list) else parsed.get("captures", [])
        captures = [capture_from_dict(c) for c in raw_list]

    if (opts.runner or "local") == "cloud":
        runner = CloudRunnerSim(
            on_progress=None
            if opts.quiet
            else (lambda e: print(f"  [{e.platform}] {e.message}"))
        )
    else:
        runner = LocalRunner()

    if not opts.quiet:
        print(f"audiosure certify — {input_path}")
        print(f"  engine:    {engine or '(auto)'}")
        print(f"  runner:    {runner.kind}")
        print(f"  platforms: {', '.join(platforms)}")
        print(f"  tier:      {get_tier(tier).name} ({used} builds used this month)")
        print("")

    try:
        result: AuditResult = runner.run(
            AuditOptions(
                input=input_path,
                engine=engine,
                platforms=platforms,
                tier=tier,
                captures=captures,
                seed=opts.seed,
                noise=opts.noise,
            )
        )
    except ValueError as err:
        print(f"Audit failed: {err}", file=sys.stderr)
        return 4

    paths = save_report(out, result.report)
    record_build(cwd, platforms=platforms, input_path=input_path, passed=result.report.overall_pass)

    r = result.report
    print(f"Summary: {'CERTIFIED PASS' if r.overall_pass else 'NOT CERTIFIED (FAIL)'}")
    for p in r.platforms:
        status = "PASS" if p.passed else "FAIL"
        print(
            f"  {status}  {p.platform:<8} score {str(p.score):>3}  "
            f"{p.fail_count} fail / {p.warn_count} warn"
        )
    print("")
    print(f"Recommendations: {len(r.recommendations)}")
    for rec in r.recommendations[:5]:
        print(f"  - {rec.title}")
    if len(r.recommendations) > 5:
        print(f"  ...and {len(r.recommendations) - 5} more (see report)")
    print("")
    print(f"Reports written to {_rel(os.path.dirname(paths['json']), cwd)}/")
    print(f"  json: {_rel(paths['json'], cwd)}")
    print(f"  md:   {_rel(paths['md'], cwd)}")
    print(f"  html: {_rel(paths['html'], cwd)}")

    return 0 if r.overall_pass else 1


def cmd_report(file_path: str, fmt: str, out: Optional[str]) -> int:
    report = load_report(file_path)
    if fmt == "json":
        content = render_json(report)
    elif fmt == "html":
        content = render_html(report)
    else:
        content = render_markdown(report)
    if out:
        with open(os.path.abspath(out), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {out}")
    else:
        print(content)
    return 0


def _load_budgets(overrides_path: Optional[str]) -> List[PlatformBudget]:
    if not overrides_path:
        return list(DEFAULT_BUDGETS)
    with open(os.path.abspath(overrides_path), "r", encoding="utf-8") as f:
        raw = json.load(f)
    return merge_budgets(raw.get("platforms") or [])


def cmd_budget(action: str, platform: Optional[str], overrides_path: Optional[str]) -> int:
    budgets = _load_budgets(overrides_path)
    if action == "show":
        matched = [b for b in budgets if b.platform == platform] if platform else budgets
        if not matched:
            print(f"Unknown platform: {platform}. Valid: {', '.join(PLATFORM_IDS)}", file=sys.stderr)
            return 2
        for b in matched:
            print(f"{b.platform} — {b.display_name}")
            for metric, limit in b.limits.items():
                parts: List[str] = []
                if limit.max is not None:
                    parts.append(f"max {limit.max}")
                if limit.min is not None:
                    parts.append(f"min {limit.min}")
                warn = limit.warn_ratio if limit.warn_ratio is not None else 0.8
                print(f"  {metric:<26} {', '.join(parts)}  (warn @ {round(warn * 100)}%)")
        return 0
    if action == "validate":
        if not overrides_path:
            print("Provide --file <budgets.json> to validate.", file=sys.stderr)
            return 2
        with open(os.path.abspath(overrides_path), "r", encoding="utf-8") as f:
            raw = json.load(f)
        platforms_raw = raw.get("platforms")
        if not isinstance(platforms_raw, list):
            print("Invalid budget file: missing platforms[] array.", file=sys.stderr)
            return 1
        ids = set(PLATFORM_IDS)
        bad = 0
        for p in platforms_raw:
            pid = p.get("platform") if isinstance(p, dict) else None
            if not pid or pid not in ids:
                print(f"Unknown platform in overrides: {pid}", file=sys.stderr)
                bad += 1
        if bad:
            return 1
        print(f"Budget file OK ({len(platforms_raw)} platform overrides).")
        return 0
    print(f"Unknown budget action: {action} (use show|validate)", file=sys.stderr)
    return 2


def cmd_fixtures(out_dir: str) -> int:
    result = generate_all_fixtures(out_dir)
    print(f"Generated fixtures in {result.root}")
    for p in result.projects:
        print(f"  - {os.path.relpath(p, out_dir)}")
    print(f"\nTry: audiosure certify --input {_rel(result.projects[0], os.getcwd())} --platforms all")
    return 0


def cmd_dash(reports_dir: str, start: bool) -> int:
    reports_abs = os.path.abspath(reports_dir)
    if not start:
        print(f'AUDIOSURE_REPORTS="{reports_abs}" pnpm --filter @audiosure/dashboard dev')
        return 0
    repo_root = _find_dashboard_repo()
    if not repo_root:
        print(
            "Dashboard not found (apps/dashboard). The web dashboard ships with the source repo;\n"
            'run "audiosure dash --no-start" for the command to run inside the repo checkout.',
            file=sys.stderr,
        )
        return 2
    print(f"Starting dashboard (reports: {reports_abs})...")
    import subprocess

    env = dict(os.environ)
    env["AUDIOSURE_REPORTS"] = reports_abs
    proc = subprocess.run(
        ["pnpm", "--filter", "@audiosure/dashboard", "dev"],
        cwd=repo_root,
        env=env,
        shell=True,
    )
    return proc.returncode


def _find_dashboard_repo() -> Optional[str]:
    d = os.getcwd()
    while True:
        candidate = os.path.join(d, "apps", "dashboard", "package.json")
        if os.path.isfile(candidate):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
