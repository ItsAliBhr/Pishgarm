# PyInstaller spec — one-folder build (doc 07 §7.4). Run on Windows: pyinstaller app.spec --noconfirm
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

root = Path(SPECPATH)
extra_datas, extra_binaries, extra_hidden = [], [], []
for pkg in ("pypdfium2", "pypdfium2_raw", "docxtpl"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    extra_datas += d
    extra_binaries += b
    extra_hidden += h
extra_datas += collect_data_files("docx")

datas = [
    (str(root / "templates"), "templates"),
    (str(root / "seed"), "seed"),
    (str(root / "assets"), "assets"),
    (str(root / "app" / "resources"), "app/resources"),
]

a = Analysis(
    [str(root / "app" / "__main__.py")],
    pathex=[str(root)],
    datas=datas + extra_datas,
    binaries=extra_binaries,
    hiddenimports=["docxtpl", "jdatetime", "pypdf", "pypdfium2", "sqlalchemy.dialects.sqlite",
                   "win32com.client", "pythoncom", "pywintypes"] + extra_hidden,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtMultimedia", "PySide6.QtQuick", "PySide6.QtQml", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="PishgarmDocs",
    console=False,
    icon=str(root / "app" / "resources" / "icons" / "app.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="PishgarmDocs")
