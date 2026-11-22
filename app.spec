# PyInstaller spec — one-folder build (doc 07 §7.4). Run on Windows: pyinstaller app.spec --noconfirm
from pathlib import Path

root = Path(SPECPATH)

datas = [
    (str(root / "templates"), "templates"),
    (str(root / "seed"), "seed"),
    (str(root / "assets"), "assets"),
    (str(root / "app" / "resources"), "app/resources"),
]

a = Analysis(
    [str(root / "app" / "__main__.py")],
    pathex=[str(root)],
    datas=datas,
    hiddenimports=["docxtpl", "jdatetime", "pypdf", "pypdfium2", "sqlalchemy.dialects.sqlite"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtMultimedia", "PySide6.QtQuick", "PySide6.QtQml"],
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
