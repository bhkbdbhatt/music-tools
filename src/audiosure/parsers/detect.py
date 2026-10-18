from __future__ import annotations

import os
import re
from typing import Callable, Dict, Optional

from audiosure.core.types import ProjectModel
from audiosure.parsers.fmod import parse_fmod
from audiosure.parsers.unity import parse_unity
from audiosure.parsers.unreal import parse_unreal
from audiosure.parsers.util import path_exists, walk_files
from audiosure.parsers.wwise import parse_wwise


def detect_engine(root: str) -> Optional[str]:
    files = walk_files(root, lambda rel, abs_: True)

    def has(pattern: str) -> bool:
        rx = re.compile(pattern, re.I)
        return any(rx.search(f) for f in files)

    if has(r"\.uproject$") or has(r"AudioInventory\.json$"):
        return "unreal"
    if has(r"\.wproj$") or has(r"\.wwu$") or has(r"SoundBanksInfo\.(xml|json)$"):
        return "wwise"
    if has(r"\.fspro$"):
        return "fmod"
    if has(r"\.mixer$") or has(r"\.unity$") or has(r"\.prefab$"):
        return "unity"

    banks = walk_files(root, lambda rel, _: bool(re.search(r"\.bank$", rel, re.I)))
    for b in banks:
        with open(b, "rb") as f:
            magic = f.read(4)
        if magic == b"FSB5":
            return "fmod"
    if has(r"\.bnk$"):
        return "wwise"

    metas = walk_files(root, lambda rel, _: bool(re.search(r"\.meta$", rel, re.I)))
    rx = re.compile(r"AudioImporter:|AudioClip:")
    for m in metas[:50]:
        try:
            with open(m, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            text = ""
        if rx.search(text):
            return "unity"
    return None


PARSERS: Dict[str, Callable[[str], ProjectModel]] = {
    "wwise": parse_wwise,
    "fmod": parse_fmod,
    "unity": parse_unity,
    "unreal": parse_unreal,
}


def parse_project(root: str, engine: Optional[str] = None) -> ProjectModel:
    if not path_exists(root):
        raise ValueError(f"Input path does not exist: {root}")
    resolved = os.path.abspath(root)
    kind = engine or detect_engine(resolved)
    if not kind:
        raise ValueError(
            f"Could not detect audio engine at {resolved}. Pass --engine wwise|fmod|unity|unreal."
        )
    model = PARSERS[kind](resolved)
    if not model.name or model.name == ".":
        model.name = os.path.basename(resolved)
    return model
