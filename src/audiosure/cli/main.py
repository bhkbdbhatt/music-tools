from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from audiosure import __version__
from audiosure.cli.commands import (
    CertifyOptions,
    cmd_analyze,
    cmd_budget,
    cmd_certify,
    cmd_dash,
    cmd_fixtures,
    cmd_init,
    cmd_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audiosure",
        description="Cross-platform game audio certification: budgets, profiling, fix reports",
    )
    parser.add_argument("-V", "--version", action="version", version=f"audiosure {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create .audiosure.json in the current directory")
    p_init.add_argument("input", nargs="?", default=".", help="project path to audit")

    p_analyze = sub.add_parser("analyze", help="Parse a project and print the extracted audio model")
    p_analyze.add_argument("input", help="Wwise, FMOD, Unity, or Unreal project path")
    p_analyze.add_argument("--engine", help="force engine: wwise|fmod|unity|unreal")
    p_analyze.add_argument("--json", action="store_true", help="output raw JSON model")

    p_certify = sub.add_parser("certify", help="Run the full certification pipeline and write pass/fail reports")
    p_certify.add_argument("input_pos", nargs="?", default=None, help="project path (defaults to .audiosure.json)")
    p_certify.add_argument("--input", dest="input_opt", help="project path (overrides positional)")
    p_certify.add_argument(
        "--platforms", help="comma list or 'all' (pc,ps5,xbox,switch2,mobile,vr)"
    )
    p_certify.add_argument("--engine", help="force engine: wwise|fmod|unity|unreal")
    p_certify.add_argument("--runner", choices=["local", "cloud"], default=None, help="local | cloud")
    p_certify.add_argument("--tier", choices=["starter", "pro", "studio"], help="starter | pro | studio")
    p_certify.add_argument("--out", help="report output directory", default=None)
    p_certify.add_argument("--captures", help="profiler capture JSON to override estimates")
    p_certify.add_argument("--seed", type=int, help="seed for simulated run variance")
    p_certify.add_argument("--noise", action="store_true", help="add deterministic run-to-run variance")
    p_certify.add_argument("-q", "--quiet", action="store_true", help="suppress progress output")

    p_report = sub.add_parser("report", help="Re-render a saved report")
    p_report.add_argument("file", help="report json (or a directory with latest.json)")
    p_report.add_argument("--format", choices=["md", "json", "html"], default="md", help="md | json | html")
    p_report.add_argument("--out", help="write to file instead of stdout")

    p_budget = sub.add_parser("budget", help="Inspect and validate platform budgets")
    budget_sub = p_budget.add_subparsers(dest="budget_action", required=True)
    p_budget_show = budget_sub.add_parser("show")
    p_budget_show.add_argument("platform", nargs="?", help="pc|ps5|xbox|switch2|mobile|vr")
    p_budget_show.add_argument("--file", help="budget overrides JSON")
    p_budget_validate = budget_sub.add_parser("validate")
    p_budget_validate.add_argument("--file", help="budget overrides JSON to validate")

    p_fixtures = sub.add_parser("fixtures", help="Generate demo projects")
    fixtures_sub = p_fixtures.add_subparsers(dest="fixtures_action", required=True)
    p_fixtures_gen = fixtures_sub.add_parser("generate")
    p_fixtures_gen.add_argument("--out", help="output directory", default="fixtures")

    p_dash = sub.add_parser("dash", help="Start the web dashboard against the reports directory")
    p_dash.add_argument("--reports", help="reports directory", default="reports")
    p_dash.add_argument("--no-start", action="store_true", help="just print the command to run")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return cmd_init(os.getcwd(), args.input)
        if args.command == "analyze":
            return cmd_analyze(args.input, args.engine, args.json)
        if args.command == "certify":
            opts = CertifyOptions(
                input=args.input_opt or args.input_pos,
                engine=args.engine,
                platforms=args.platforms,
                runner=args.runner,
                tier=args.tier,
                out=args.out,
                seed=args.seed,
                noise=args.noise,
                captures=args.captures,
                quiet=args.quiet,
            )
            return cmd_certify(os.getcwd(), opts)
        if args.command == "report":
            return cmd_report(args.file, args.format, args.out)
        if args.command == "budget":
            return cmd_budget(args.budget_action, getattr(args, "platform", None), args.file)
        if args.command == "fixtures":
            return cmd_fixtures(os.path.abspath(args.out))
        if args.command == "dash":
            return cmd_dash(args.reports, start=not args.no_start)
    except ValueError as err:
        print(err, file=sys.stderr)
        return 1
    except OSError as err:
        print(err, file=sys.stderr)
        return 1
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
