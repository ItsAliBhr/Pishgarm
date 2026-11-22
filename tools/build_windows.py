"""Build PishgarmDocsSetup.exe on Windows: pytest → PyInstaller → Inno Setup.

Usage:  python tools/build_windows.py [--skip-tests]
Needs:  pip install -e .[build]   and Inno Setup 6 (iscc on PATH, or the default install folder).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*cmd: str) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def find_iscc() -> str:
    found = shutil.which("iscc")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.environ.get("LOCALAPPDATA") and str(Path(os.environ["LOCALAPPDATA"]) / "Programs")):
        if base:
            p = Path(base) / "Inno Setup 6" / "ISCC.exe"
            if p.exists():
                return str(p)
    sys.exit("Inno Setup (ISCC.exe) پیدا نشد. نصب: choco install innosetup -y")


def main() -> None:
    # Windows consoles default to cp1252; make Persian messages printable.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if sys.platform != "win32":
        sys.exit("ساخت نصب‌کننده فقط روی ویندوز ممکن است (یا با GitHub Actions).")
    sys.path.insert(0, str(ROOT))
    from app import __version__

    if "--skip-tests" not in sys.argv:
        run(sys.executable, "-m", "pytest", "-q")
    run(sys.executable, "-m", "PyInstaller", "app.spec", "--noconfirm", "--clean")
    run(find_iscc(), f"/DAppVersion={__version__}", str(Path("tools") / "installer.iss"))
    print("\nآماده:", ROOT / "dist" / "PishgarmDocsSetup.exe")


if __name__ == "__main__":
    main()
