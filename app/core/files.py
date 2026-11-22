"""Output folder and file names (doc 05 §5.5)."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from app.core import jalali
from app.core.draft import KIND_FA

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_PATH = 200


def safe_name(text: str, fallback: str = "بدون‌نام") -> str:
    s = _BAD.sub(" ", text or "")
    s = re.sub(r"\s+", " ", s).strip().rstrip(".")
    return s or fallback


def document_folder(root: Path, party_short_name: str, project_title: str | None) -> Path:
    return Path(root) / safe_name(party_short_name) / safe_name(project_title or "عمومی")


def base_file_name(kind: str, party_short_name: str, number: str, d: date, subject: str = "") -> str:
    label = KIND_FA.get(kind, kind)
    if kind == "letter" and subject:
        label = f"نامه {subject[:40]}"
    parts = [label, party_short_name, (number or "").replace("/", "-"), jalali.compact(d)]
    return safe_name(" ".join(p for p in parts if p))


def versioned_path(folder: Path, base: str, ext: str, version: int = 1) -> tuple[Path, int]:
    """First free path at or above `version`: «base.docx», «base -v2.docx», … Never an existing file."""
    folder = Path(folder)
    v = max(int(version), 1)
    while True:
        name = base if v == 1 else f"{base} -v{v}"
        room = MAX_PATH - len(str(folder)) - len(ext) - 8
        if room < len(name):
            name = name[:max(room, 20)].rstrip()
        p = folder / f"{name}{ext}"
        if not p.exists():
            return p, v
        v += 1
