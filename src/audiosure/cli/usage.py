from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

USAGE_DIR = ".audiosure"
USAGE_FILE = "usage.json"


@dataclass
class UsageRecord:
    month: str
    builds: int = 0
    history: List[Dict] = field(default_factory=list)


def _month_key(d: Optional[datetime] = None) -> str:
    d = d or datetime.now(timezone.utc)
    return f"{d.year}-{d.month:02d}"


def _read(cwd: str) -> UsageRecord:
    p = os.path.join(cwd, USAGE_DIR, USAGE_FILE)
    try:
        with open(p, "r", encoding="utf-8") as f:
            rec = json.load(f)
        if rec.get("month") == _month_key():
            return UsageRecord(month=rec["month"], builds=rec.get("builds", 0), history=rec.get("history", []))
        return UsageRecord(month=_month_key(), builds=0, history=rec.get("history", []))
    except (OSError, ValueError, KeyError):
        return UsageRecord(month=_month_key(), builds=0, history=[])


def builds_this_month(cwd: str) -> int:
    return _read(cwd).builds


def record_build(cwd: str, platforms: List[str], input_path: str, passed: bool) -> UsageRecord:
    rec = _read(cwd)
    rec.builds += 1
    rec.history.insert(0, {"at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "platforms": platforms, "input": input_path, "passed": passed})
    rec.history = rec.history[:100]
    directory = os.path.join(cwd, USAGE_DIR)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, USAGE_FILE), "w", encoding="utf-8") as f:
        json.dump({"month": rec.month, "builds": rec.builds, "history": rec.history}, f, indent=2)
        f.write("\n")
    return rec
