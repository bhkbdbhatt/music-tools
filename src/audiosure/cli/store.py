from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from audiosure.cli.reporters import render_html, render_json, render_markdown
from audiosure.core.report import certification_report_from_dict
from audiosure.core.types import CertificationReport


def save_report(out_dir: str, report: CertificationReport) -> Dict[str, str]:
    abs_dir = os.path.abspath(out_dir)
    os.makedirs(abs_dir, exist_ok=True)

    json_path = os.path.join(abs_dir, f"{report.id}.json")
    md_path = os.path.join(abs_dir, f"{report.id}.md")
    html_path = os.path.join(abs_dir, f"{report.id}.html")

    with open(json_path, "w", encoding="utf-8") as f:
        f.write(render_json(report) + "\n")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(report))

    latest_json = os.path.join(abs_dir, "latest.json")
    with open(latest_json, "w", encoding="utf-8") as f:
        f.write(render_json(report) + "\n")
    with open(os.path.join(abs_dir, "latest.md"), "w", encoding="utf-8") as f:
        f.write(render_markdown(report))
    with open(os.path.join(abs_dir, "latest.html"), "w", encoding="utf-8") as f:
        f.write(render_html(report))

    _append_index(abs_dir, report)

    return {"json": json_path, "md": md_path, "html": html_path, "latestJson": latest_json}


def _append_index(abs_dir: str, report: CertificationReport) -> None:
    index_path = os.path.join(abs_dir, "index.json")
    entries: List[Dict[str, Any]] = []
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, ValueError):
        entries = []
    entry: Dict[str, Any] = {
        "id": report.id,
        "createdAt": report.created_at,
        "project": report.project.name,
        "engine": report.project.engine,
        "runner": report.runner.name,
        "overallPass": report.overall_pass,
        "platforms": [
            {
                "platform": p.platform,
                "passed": p.passed,
                "score": p.score,
                "fails": p.fail_count,
                "warns": p.warn_count,
            }
            for p in report.platforms
        ],
    }
    entries = [entry] + [e for e in entries if e.get("id") != entry["id"]]
    entries = entries[:200]
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
        f.write("\n")


def list_reports(out_dir: str) -> List[Dict[str, Any]]:
    try:
        with open(os.path.join(os.path.abspath(out_dir), "index.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def load_report(file: str) -> CertificationReport:
    abs_path = os.path.abspath(file)
    target = os.path.join(abs_path, "latest.json") if os.path.isdir(abs_path) else abs_path
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
    return certification_report_from_dict(data)
