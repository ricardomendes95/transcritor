# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

datas = [
    ("assets/icone.ico", "assets"),
    ("assets/icone.png", "assets"),
]
binaries = []
hiddenimports = []

for pacote in ("customtkinter", "tkinterdnd2", "faster_whisper", "ctranslate2", "onnxruntime", "av"):
    d, b, h = collect_all(pacote)
    datas += d
    binaries += b
    hiddenimports += h

# As DLLs de CUDA (cuBLAS/cuDNN) ficam em nvidia/*/bin, que não é um pacote importável,
# então collect_all não as encontra e precisam ser adicionadas manualmente.
nvidia_dir = Path(SPECPATH) / "venv" / "Lib" / "site-packages" / "nvidia"
for dll in nvidia_dir.glob("*/bin/*.dll"):
    binaries.append((str(dll), f"nvidia/{dll.parent.parent.name}/bin"))

a = Analysis(
    ["transcrever_gui.py"],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Transcritor",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/icone.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Transcritor",
)
